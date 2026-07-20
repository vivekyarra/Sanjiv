from uuid import uuid4

from maritime_helpers import raw_position
from sanjiv.contracts import TruthClass
from sanjiv.maritime.contracts import SanctionsMatchStatus
from sanjiv.maritime.normalization import normalize_ais_position
from sanjiv.maritime.sanctions import SanctionsMatcher, SanctionsRecord


def _position():  # type: ignore[no-untyped-def]
    raw = raw_position()
    return normalize_ais_position(raw, computed_at=raw.fetched_at).position


def test_unloaded_sanctions_source_never_claims_clearance() -> None:
    assessment = SanctionsMatcher().assess(_position())
    assert assessment.status is SanctionsMatchStatus.NOT_SCREENED
    assert assessment.truth_class is TruthClass.INFERRED


def test_exact_identifier_is_derived_but_fuzzy_name_is_inferred() -> None:
    position = _position()
    evidence_id = uuid4()
    exact = SanctionsMatcher(
        [SanctionsRecord(name="ANY", mmsi=position.mmsi, evidence_id=evidence_id)]
    ).assess(position)
    fuzzy = SanctionsMatcher(
        [SanctionsRecord(name="SYNTHETIC TEST VESSEL", evidence_id=evidence_id)]
    ).assess(position)
    assert exact.status is SanctionsMatchStatus.EXACT_MATCH
    assert exact.truth_class is TruthClass.DERIVED
    assert fuzzy.status is SanctionsMatchStatus.POTENTIAL_MATCH
    assert fuzzy.truth_class is TruthClass.INFERRED
