from datetime import timedelta

from maritime_helpers import GEOFENCES, raw_position
from sanjiv.contracts import TruthClass
from sanjiv.maritime.contracts import GeofenceEventType
from sanjiv.maritime.geofences import GeofenceEngine, load_geofences
from sanjiv.maritime.normalization import normalize_ais_position


def test_reference_geofences_are_explicit_non_authoritative_assumptions() -> None:
    geofences = load_geofences(GEOFENCES)
    assert {item.slug for item in geofences} >= {
        "strait-of-hormuz",
        "bab-el-mandeb",
        "suez-canal",
        "strait-of-malacca",
        "jamnagar-energy-port",
    }
    assert all(item.truth_class is TruthClass.ASSUMPTION for item in geofences)
    assert not any(item.authoritative for item in geofences)


def test_geofence_entry_exit_and_duplicate_prevention() -> None:
    geofences = load_geofences(GEOFENCES)
    engine = GeofenceEngine([item for item in geofences if item.slug == "strait-of-hormuz"])
    outside = raw_position(record_id="outside", latitude=25.1, longitude=54.9)
    inside = raw_position(
        record_id="inside",
        latitude=26.4,
        longitude=56.3,
        source_timestamp=outside.source_timestamp + timedelta(minutes=1),
        fetched_at=outside.fetched_at + timedelta(minutes=1),
    )
    outside_again = raw_position(
        record_id="outside-again",
        latitude=25.1,
        longitude=54.9,
        source_timestamp=outside.source_timestamp + timedelta(minutes=2),
        fetched_at=outside.fetched_at + timedelta(minutes=2),
    )

    first = normalize_ais_position(outside, computed_at=outside.fetched_at).position
    second = normalize_ais_position(inside, computed_at=inside.fetched_at).position
    third = normalize_ais_position(outside_again, computed_at=outside_again.fetched_at).position
    assert engine.evaluate(first) == []
    entry = engine.evaluate(second)
    assert [item.event_type for item in entry] == [GeofenceEventType.ENTRY]
    assert len(entry[0].evidence_ids) == 2
    assert engine.evaluate(second) == []
    exit_events = engine.evaluate(third)
    assert [item.event_type for item in exit_events] == [GeofenceEventType.EXIT]
    assert engine.evaluate(third) == []
