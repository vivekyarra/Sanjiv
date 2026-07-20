import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from websockets.asyncio.client import connect

from sanjiv.contracts import DataMode, FreshnessStatus, SourceHealthRecord, SourceState
from sanjiv.maritime.contracts import AdapterHealth, ConnectionState, RawAISMessage

AISSTREAM_ADAPTER_VERSION = "aisstream-adapter-1.0.0"
AISSTREAM_SOURCE_URL = "https://aisstream.io/documentation.html"


class AISStreamAdapter:
    def __init__(
        self,
        *,
        api_key: str,
        url: str,
        bounding_boxes: list[list[list[float]]],
        connect_timeout_seconds: float = 10.0,
        subscription_timeout_seconds: float = 3.0,
        max_retries: int = 3,
        reconnect_base_seconds: float = 1.0,
        reconnect_max_seconds: float = 30.0,
        queue_size: int = 1000,
    ) -> None:
        if not api_key:
            raise ValueError("AISStream API key is required for the live adapter")
        self._api_key = api_key
        self._url = url
        self._bounding_boxes = bounding_boxes
        self._connect_timeout = connect_timeout_seconds
        self._subscription_timeout = subscription_timeout_seconds
        self._max_retries = max_retries
        self._reconnect_base = reconnect_base_seconds
        self._reconnect_max = reconnect_max_seconds
        self._queue_size = queue_size
        self._last_success: datetime | None = None
        self._messages = 0
        self._errors = 0
        self._state = ConnectionState.DISCONNECTED

    @property
    def source_id(self) -> str:
        return "AISSTREAM"

    @property
    def mode(self) -> DataMode:
        return DataMode.LIVE

    async def health(self) -> AdapterHealth:
        now = datetime.now(UTC)
        state = (
            SourceState.READY if self._state is ConnectionState.CONNECTED else SourceState.DEGRADED
        )
        freshness = (
            FreshnessStatus.LIVE
            if self._last_success and (now - self._last_success).total_seconds() < 60
            else FreshnessStatus.UNAVAILABLE
        )
        return AdapterHealth(
            source_health=SourceHealthRecord(
                source_id=self.source_id,
                state=state,
                checked_at=now,
                last_success_at=self._last_success,
                expected_cadence_seconds=60,
                stale_after_seconds=300,
                message_count=self._messages,
                error_count=self._errors,
                circuit_open=False,
                mode=self.mode,
                freshness_status=freshness,
            ),
            connection_state=self._state,
            detail="Backend AISStream WebSocket; provider is beta and has no SLA",
        )

    def stream(self) -> AsyncIterator[RawAISMessage]:
        return self._stream()

    async def _stream(self) -> AsyncIterator[RawAISMessage]:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                self._state = ConnectionState.CONNECTING
                async with connect(
                    self._url,
                    open_timeout=self._connect_timeout,
                    max_queue=self._queue_size,
                    ping_interval=20,
                    ping_timeout=20,
                ) as websocket:
                    subscription = {
                        "APIKey": self._api_key,
                        "BoundingBoxes": self._bounding_boxes,
                        "FilterMessageTypes": [
                            "PositionReport",
                            "StandardClassBPositionReport",
                            "ExtendedClassBPositionReport",
                        ],
                    }
                    await asyncio.wait_for(
                        websocket.send(json.dumps(subscription)),
                        timeout=self._subscription_timeout,
                    )
                    self._state = ConnectionState.CONNECTED
                    async for encoded in websocket:
                        fetched_at = datetime.now(UTC)
                        payload = json.loads(encoded)
                        if not isinstance(payload, dict):
                            raise ValueError("AISStream message must be a JSON object")
                        source_timestamp = self._extract_source_timestamp(payload)
                        record_id = self._record_id(payload)
                        self._last_success = fetched_at
                        self._messages += 1
                        yield RawAISMessage(
                            source_id=self.source_id,
                            source_record_id=record_id,
                            source_timestamp=source_timestamp,
                            fetched_at=fetched_at,
                            mode=DataMode.LIVE,
                            payload=payload,
                            dataset="AISStream WebSocket",
                            dataset_version=AISSTREAM_ADAPTER_VERSION,
                            license=(
                                "Subject to AISStream terms; redistribution not granted by Sanjiv"
                            ),
                            source_url=AISSTREAM_SOURCE_URL,
                        )
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._errors += 1
                self._state = ConnectionState.DEGRADED
                last_error = exc
                if attempt >= self._max_retries:
                    break
                delay = min(self._reconnect_base * (2**attempt), self._reconnect_max)
                await asyncio.sleep(delay)
        self._state = ConnectionState.DISCONNECTED
        raise ConnectionError("AISStream unavailable after bounded retries") from last_error

    @staticmethod
    def _extract_source_timestamp(payload: dict[str, Any]) -> datetime:
        metadata = payload.get("Metadata")
        if not isinstance(metadata, dict):
            raise ValueError("AISStream Metadata object is required")
        raw = metadata.get("time_utc") or metadata.get("TimeUTC") or metadata.get("timestamp")
        if not isinstance(raw, str):
            raise ValueError("AISStream source timestamp is required")
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("AISStream source timestamp must include a timezone")
        return parsed.astimezone(UTC)

    @staticmethod
    def _record_id(payload: dict[str, Any]) -> str:
        metadata = payload.get("Metadata", {})
        explicit = metadata.get("MessageID") if isinstance(metadata, dict) else None
        if explicit:
            return str(explicit)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
