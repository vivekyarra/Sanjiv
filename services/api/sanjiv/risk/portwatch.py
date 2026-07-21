from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from sanjiv.contracts import FreshnessStatus, TruthClass
from sanjiv.risk.contracts import PortWatchHormuzObservation

PORTWATCH_LAYER_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
    "Daily_Chokepoints_Data/FeatureServer/0"
)
PORTWATCH_DOCUMENTATION_URL = "https://portwatch.imf.org/pages/data-and-methodology/"

JsonFetcher = Callable[[str, dict[str, str]], Awaitable[dict[str, Any]]]


class PortWatchUnavailable(RuntimeError):
    """The current public PortWatch observation could not be validated."""


class _PortWatchAttributes(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: str
    portid: str
    portname: str
    n_tanker: int = Field(ge=0)
    n_total: int = Field(ge=0)
    capacity_tanker: int = Field(ge=0)
    capacity: int = Field(ge=0)


class _PortWatchFeature(BaseModel):
    model_config = ConfigDict(extra="ignore")
    attributes: _PortWatchAttributes


class _PortWatchQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    features: list[_PortWatchFeature]


class PortWatchService:
    def __init__(self, fetcher: JsonFetcher | None = None) -> None:
        self._fetcher = fetcher or _fetch_json

    async def hormuz_current(self) -> PortWatchHormuzObservation:
        query = await self._fetch_with_retry(
            f"{PORTWATCH_LAYER_URL}/query",
            {
                "where": "portname LIKE '%Hormuz%'",
                "outFields": ("date,portid,portname,n_tanker,n_total,capacity_tanker,capacity"),
                "returnGeometry": "false",
                "orderByFields": "date DESC",
                "resultRecordCount": "1",
                "f": "json",
            },
        )
        metadata = await self._fetch_with_retry(PORTWATCH_LAYER_URL, {"f": "json"})
        parsed = _PortWatchQuery.model_validate(query)
        if not parsed.features:
            raise PortWatchUnavailable("PortWatch returned no Strait of Hormuz observation")

        attributes = parsed.features[0].attributes
        try:
            source_date = datetime.strptime(attributes.date, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError as error:
            raise PortWatchUnavailable("PortWatch returned an invalid source date") from error

        fetched_at = datetime.now(UTC)
        age_hours = max(0.0, (fetched_at - source_date).total_seconds() / 3600)
        freshness = (
            FreshnessStatus.CURRENT
            if age_hours <= 96
            else FreshnessStatus.RECENT
            if age_hours <= 168
            else FreshnessStatus.STALE
        )
        edit_millis = metadata.get("editingInfo", {}).get("dataLastEditDate")
        source_modified_at = (
            datetime.fromtimestamp(float(edit_millis) / 1000, tz=UTC)
            if isinstance(edit_millis, int | float)
            else fetched_at
        )
        evidence_payload = attributes.model_dump(mode="json")
        evidence_id = hashlib.sha256(
            json.dumps(evidence_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        return PortWatchHormuzObservation(
            source_id="IMF_PORTWATCH",
            source_record_id=f"{attributes.portid}:{attributes.date}",
            mode="LIVE",
            freshness_status=freshness,
            truth_class=TruthClass.OBSERVED,
            corridor_name=attributes.portname,
            effective_date=source_date.date(),
            fetched_at=fetched_at,
            source_modified_at=source_modified_at,
            source_age_hours=round(age_hours, 2),
            tanker_transits=attributes.n_tanker,
            total_transits=attributes.n_total,
            estimated_tanker_tonnage=attributes.capacity_tanker,
            estimated_total_tonnage=attributes.capacity,
            evidence_id=evidence_id,
            source_url=PORTWATCH_LAYER_URL,
            documentation_url=PORTWATCH_DOCUMENTATION_URL,
            methodology_note=(
                "IMF PortWatch estimates daily chokepoint transits and carried tonnage from "
                "AIS-derived vessel movements. This is not exact cargo ownership, charter "
                "availability, or confirmation of a physical disruption."
            ),
        )

    async def _fetch_with_retry(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        for attempt in range(2):
            try:
                payload = await asyncio.wait_for(self._fetcher(url, params), timeout=12)
                if "error" in payload:
                    raise PortWatchUnavailable("PortWatch returned an API error")
                return payload
            except (TimeoutError, httpx.HTTPError, ValueError) as error:
                if attempt == 1:
                    raise PortWatchUnavailable("PortWatch is temporarily unavailable") from error
                await asyncio.sleep(0.25)
        raise PortWatchUnavailable("PortWatch is temporarily unavailable")


async def _fetch_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    async with httpx.AsyncClient(
        headers={"User-Agent": "Sanjiv/1.0 (India energy resilience demo)"},
        timeout=10,
        follow_redirects=False,
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("PortWatch response must be a JSON object")
        return payload
