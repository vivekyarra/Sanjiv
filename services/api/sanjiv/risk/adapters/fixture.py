from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field

from sanjiv.contracts import FreshnessStatus, SourceState, TruthClass
from sanjiv.risk.adapters.base import AdapterPolicy, RawRiskSignal, RiskAdapterResult
from sanjiv.risk.contracts import (
    RiskFeatureType,
    RiskSourceFailure,
    RiskSourceFailureCode,
)
from sanjiv.twin.contracts import canonical_uuid

MANIFEST_PATH = Path("data/replay/risk-intelligence-v1/manifest.json")
FEATURE_SOURCES = {
    RiskFeatureType.TRANSIT_ANOMALY: "IMF_PORTWATCH",
    RiskFeatureType.GEOPOLITICAL_SEVERITY: "GDELT",
    RiskFeatureType.AIS_BEHAVIORAL_ANOMALY: "AIS_PHASE_1",
    RiskFeatureType.MARKET_STRESS: "EIA_FRED",
    RiskFeatureType.SANCTIONS_EXPOSURE: "SANCTIONS_BOUNDARY",
    RiskFeatureType.INFRASTRUCTURE_PHYSICAL_SIGNAL: "NASA_FIRMS",
}


class RiskReplayCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str
    label: str
    corridor: str
    expected_alert: bool
    lead_hours: float = Field(ge=0, allow_inf_nan=False)
    features: dict[str, float | None]
    stale_features: list[str] = []


class RiskReplayPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["risk-replay-v1"]
    classification: Literal["SYNTHETIC_FIXTURE"]
    redistribution_rights: str
    baseline: list[float] = Field(min_length=3)
    cases: list[RiskReplayCase] = Field(min_length=1)


class RiskReplayManifest(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    dataset_id: str
    classification: Literal["SYNTHETIC_FIXTURE", "RECORDED_REAL_DATA"]
    data_file: str
    checksum_sha256: str
    case_count: int = Field(gt=0)


class FixtureRiskAdapter:
    def __init__(self, manifest_path: Path = MANIFEST_PATH) -> None:
        self.manifest_path = manifest_path
        self.manifest, self.payload = _load(manifest_path)

    @property
    def source_id(self) -> str:
        return "SANJIV_RISK_REPLAY"

    @property
    def policy(self) -> AdapterPolicy:
        return AdapterPolicy(
            timeout_seconds=2,
            max_retries=0,
            backoff_seconds=0,
            expected_cadence_seconds=3600,
            stale_after_seconds=7200,
            rate_limit_per_minute=60,
        )

    async def fetch(self, case_id: str) -> RiskAdapterResult:
        case = next((item for item in self.payload.cases if item.case_id == case_id), None)
        if case is None:
            return RiskAdapterResult(
                source_id=self.source_id,
                signals=[],
                failures=[
                    RiskSourceFailure(
                        source_id=self.source_id,
                        code=RiskSourceFailureCode.INVALID_PAYLOAD,
                        message="Requested replay case is not present.",
                        retryable=False,
                        occurred_at=datetime.now(UTC),
                    )
                ],
            )
        at = datetime(2026, 7, 21, 12, tzinfo=UTC)
        stale = set(case.stale_features)
        corridor_id = canonical_uuid(case.corridor)
        signals = []
        failures = []
        for feature in RiskFeatureType:
            value = case.features.get(feature.value)
            source_id = FEATURE_SOURCES[feature]
            is_stale = feature.value in stale
            missing = value is None
            state = (
                SourceState.UNAVAILABLE
                if missing
                else SourceState.DEGRADED
                if is_stale
                else SourceState.READY
            )
            freshness = (
                FreshnessStatus.UNAVAILABLE
                if missing
                else FreshnessStatus.STALE
                if is_stale
                else FreshnessStatus.REPLAY
            )
            evidence_id = uuid5(
                NAMESPACE_URL, f"urn:sanjiv:risk-evidence:{case_id}:{feature.value}"
            )
            effective = at - timedelta(days=7) if is_stale else at
            signals.append(
                RawRiskSignal(
                    corridor_id=corridor_id,
                    feature_type=feature,
                    raw_value=value,
                    unit="fixture_signal_point",
                    source_id=source_id,
                    source_state=state,
                    freshness=freshness,
                    truth_class=TruthClass.ASSUMPTION,
                    confidence=0.0 if missing else 0.35 if is_stale else 0.75,
                    effective_at=effective.isoformat(),
                    fetched_at=at.isoformat(),
                    evidence_ids=[] if missing else [evidence_id],
                )
            )
            if missing or is_stale:
                failures.append(
                    RiskSourceFailure(
                        source_id=source_id,
                        code=RiskSourceFailureCode.UNAVAILABLE
                        if missing
                        else RiskSourceFailureCode.STALE,
                        message="Replay source is unavailable."
                        if missing
                        else "Replay source exceeds its freshness threshold.",
                        retryable=missing,
                        occurred_at=at,
                    )
                )
        return RiskAdapterResult(source_id=self.source_id, signals=signals, failures=failures)

    def cases(self) -> list[RiskReplayCase]:
        return list(self.payload.cases)

    def baseline(self) -> list[float]:
        return list(self.payload.baseline)


def _load(manifest_path: Path) -> tuple[RiskReplayManifest, RiskReplayPayload]:
    manifest = RiskReplayManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if manifest.classification != "SYNTHETIC_FIXTURE":
        raise ValueError("risk replay must be explicitly classified")
    data_path = manifest_path.parent / manifest.data_file
    content = data_path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    if checksum != manifest.checksum_sha256:
        raise ValueError("risk replay checksum mismatch")
    payload = RiskReplayPayload.model_validate(json.loads(content))
    if len(payload.cases) != manifest.case_count:
        raise ValueError("risk replay case count mismatch")
    return manifest, payload
