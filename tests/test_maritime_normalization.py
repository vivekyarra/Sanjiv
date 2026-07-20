from datetime import UTC, datetime, timedelta

import pytest
from maritime_helpers import raw_position
from pydantic import ValidationError
from sanjiv.contracts import DataMode, FreshnessStatus, TruthClass
from sanjiv.maritime.contracts import RawAISMessage
from sanjiv.maritime.normalization import classify_freshness, normalize_ais_position


def test_normalizes_position_with_evidence_and_preserves_zero_speed() -> None:
    raw = raw_position()
    result = normalize_ais_position(raw, computed_at=raw.fetched_at)

    assert result.position.speed_knots == 0
    assert result.position.truth_class is TruthClass.OBSERVED
    assert result.position.evidence_ids == [result.evidence.id]
    assert result.evidence.source_record_id == raw.source_record_id
    assert result.evidence.raw_payload_hash
    assert result.position.source_timestamp.tzinfo is UTC
    assert result.position.source_timestamp <= result.position.fetched_at


def test_normalization_uses_stable_ids_for_replay_and_deduplication() -> None:
    raw = raw_position()
    first = normalize_ais_position(raw, computed_at=raw.fetched_at)
    second = normalize_ais_position(raw, computed_at=raw.fetched_at)
    assert first.position.id == second.position.id
    assert first.evidence.id == second.evidence.id


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 70), (-91, 70), (20, 181), (20, -181), (float("nan"), 70)],
)
def test_rejects_invalid_coordinates(latitude: float, longitude: float) -> None:
    raw = raw_position(latitude=latitude, longitude=longitude)
    with pytest.raises((ValueError, ValidationError), match="coordinate|latitude|longitude"):
        normalize_ais_position(raw, computed_at=raw.fetched_at)


def test_rejects_malformed_payload() -> None:
    raw = raw_position(payload_override={"unexpected": "shape"})
    with pytest.raises(ValueError, match="unsupported AIS payload shape"):
        normalize_ais_position(raw, computed_at=raw.fetched_at)


def test_requires_ordered_timezone_aware_external_timestamps() -> None:
    now = datetime.now(UTC)
    payload = raw_position().payload
    with pytest.raises(ValidationError, match="source_timestamp"):
        RawAISMessage(
            source_id="TEST",
            source_record_id="future",
            source_timestamp=now + timedelta(seconds=1),
            fetched_at=now,
            mode=DataMode.LIVE,
            payload=payload,
            dataset="test",
            dataset_version="1",
            license="test",
        )


def test_freshness_classification_distinguishes_live_stale_and_replay() -> None:
    now = datetime.now(UTC)
    assert classify_freshness(now, now, DataMode.LIVE) is FreshnessStatus.LIVE
    assert (
        classify_freshness(now - timedelta(minutes=10), now, DataMode.LIVE) is FreshnessStatus.STALE
    )
    assert classify_freshness(now, now, DataMode.REPLAY) is FreshnessStatus.REPLAY


def test_replay_fixture_is_never_observed() -> None:
    raw = raw_position(mode=DataMode.REPLAY)
    result = normalize_ais_position(raw, computed_at=raw.fetched_at)
    assert result.position.truth_class is TruthClass.ASSUMPTION
    assert result.evidence.truth_class is TruthClass.ASSUMPTION
    assert result.position.freshness_status is FreshnessStatus.REPLAY
