import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sanjiv.contracts import DataMode, EvidenceRecord, FreshnessStatus, TruthClass
from sanjiv.maritime.contracts import NormalizedObservation, RawAISMessage, VesselPosition

NORMALIZER_VERSION = "ais-position-normalizer-1.0.0"


def classify_freshness(
    source_timestamp: datetime,
    computed_at: datetime,
    mode: DataMode,
    *,
    stale_after_seconds: int = 300,
) -> FreshnessStatus:
    if mode is DataMode.REPLAY or mode is DataMode.FIXTURE:
        return FreshnessStatus.REPLAY
    age = (computed_at - source_timestamp).total_seconds()
    if age < 0:
        raise ValueError("source timestamp cannot be in the future")
    if age < 60:
        return FreshnessStatus.LIVE
    if age < stale_after_seconds:
        return FreshnessStatus.RECENT
    return FreshnessStatus.STALE


def normalize_ais_position(
    raw: RawAISMessage,
    *,
    computed_at: datetime | None = None,
    stale_after_seconds: int = 300,
) -> NormalizedObservation:
    now = (computed_at or datetime.now(UTC)).astimezone(UTC)
    fields = _position_fields(raw.payload)
    mmsi = _mmsi(fields, raw.payload)
    latitude = _number(fields, "Latitude", "latitude")
    longitude = _number(fields, "Longitude", "longitude")
    _finite_coordinate(latitude, longitude)

    vessel_id = uuid5(NAMESPACE_URL, f"urn:sanjiv:vessel:mmsi:{mmsi}")
    position_id = uuid5(
        NAMESPACE_URL,
        f"urn:sanjiv:position:{raw.source_id}:{raw.source_record_id}:{raw.source_timestamp.isoformat()}",
    )
    payload_bytes = json.dumps(raw.payload, sort_keys=True, separators=(",", ":")).encode()
    evidence = EvidenceRecord(
        id=uuid5(
            NAMESPACE_URL,
            (f"urn:sanjiv:evidence:{raw.source_id}:{raw.source_record_id}:{raw.dataset_version}"),
        ),
        source_id=raw.source_id,
        source_record_id=raw.source_record_id,
        source_url=raw.source_url,
        dataset=raw.dataset,
        dataset_version=raw.dataset_version,
        effective_at=raw.source_timestamp,
        fetched_at=raw.fetched_at,
        mode=raw.mode,
        truth_class=(TruthClass.OBSERVED if raw.mode is DataMode.LIVE else TruthClass.ASSUMPTION),
        raw_payload_hash=hashlib.sha256(payload_bytes).hexdigest(),
        transformation=NORMALIZER_VERSION,
        confidence=1.0,
        license=raw.license,
    )
    metadata = raw.payload.get("Metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    truth_class = TruthClass.OBSERVED if raw.mode is DataMode.LIVE else TruthClass.ASSUMPTION
    position = VesselPosition(
        id=position_id,
        vessel_id=vessel_id,
        mmsi=mmsi,
        imo=_optional_identifier(_first_present(metadata.get("IMO"), fields.get("IMO")), 7),
        vessel_name=_optional_text(_first_present(metadata.get("ShipName"), fields.get("Name"))),
        ship_type=_optional_int(
            _first_present(metadata.get("ShipType"), fields.get("Type")), minimum=0, maximum=99
        ),
        latitude=latitude,
        longitude=longitude,
        speed_knots=_optional_float(
            _first_present(fields.get("Sog"), fields.get("SpeedOverGround")), 0.0, 102.3
        ),
        course_degrees=_optional_float(
            _first_present(fields.get("Cog"), fields.get("CourseOverGround")), 0.0, 359.999
        ),
        heading_degrees=_optional_float(fields.get("TrueHeading"), 0.0, 359.0),
        navigation_status=_optional_int(fields.get("NavigationalStatus"), minimum=0, maximum=15),
        destination_raw=_optional_text(
            _first_present(metadata.get("Destination"), fields.get("Destination"))
        ),
        source_timestamp=raw.source_timestamp.astimezone(UTC),
        fetched_at=raw.fetched_at.astimezone(UTC),
        computed_at=now,
        source_id=raw.source_id,
        source_record_id=raw.source_record_id,
        mode=raw.mode,
        truth_class=truth_class,
        freshness_status=classify_freshness(
            raw.source_timestamp, now, raw.mode, stale_after_seconds=stale_after_seconds
        ),
        confidence=1.0,
        evidence_ids=[evidence.id],
        transformation=NORMALIZER_VERSION,
        adapter_version=raw.dataset_version,
    )
    return NormalizedObservation(position=position, evidence=evidence)


def _position_fields(payload: dict[str, Any]) -> dict[str, Any]:
    if "position" in payload and isinstance(payload["position"], dict):
        return payload["position"]
    message_type = payload.get("MessageType")
    message = payload.get("Message")
    if not isinstance(message_type, str) or not isinstance(message, dict):
        raise ValueError("unsupported AIS payload shape")
    body = message.get(message_type)
    if not isinstance(body, dict):
        raise ValueError("AIS message body is missing")
    return body


def _mmsi(fields: dict[str, Any], payload: dict[str, Any]) -> str:
    metadata = payload.get("Metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    raw = metadata.get("MMSI") or fields.get("UserID") or fields.get("MMSI")
    if isinstance(raw, bool) or raw is None:
        raise ValueError("MMSI is required")
    value = str(raw).strip()
    if not (len(value) == 9 and value.isdigit()):
        raise ValueError("MMSI must contain exactly nine digits")
    return value


def _number(fields: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = fields.get(key)
        if value is not None and not isinstance(value, bool):
            try:
                return float(value)
            except (TypeError, ValueError):
                break
    raise ValueError(f"{keys[0]} is required and must be numeric")


def _finite_coordinate(latitude: float, longitude: float) -> None:
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("coordinates must be finite")
    if not -90 <= latitude <= 90:
        raise ValueError("latitude outside [-90, 90]")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude outside [-180, 180]")


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized[:200] or None


def _first_present(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _optional_identifier(value: Any, length: int) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    normalized = str(value).strip()
    return normalized if normalized.isdigit() and len(normalized) == length else None


def _optional_float(value: Any, minimum: float, maximum: float) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and minimum <= number <= maximum else None


def _optional_int(value: Any, *, minimum: int, maximum: int) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if minimum <= number <= maximum else None
