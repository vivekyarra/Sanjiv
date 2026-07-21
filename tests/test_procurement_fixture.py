from datetime import UTC, datetime

import pytest
from sanjiv.contracts import AssumptionStatus, TruthClass
from sanjiv.procurement.fixture import load_commercial_fixture
from sanjiv.twin.service import build_default_twin_service


def test_commercial_fixture_is_synthetic_expiring_and_assumption_backed() -> None:
    bundle = load_commercial_fixture(
        build_default_twin_service().current(), at=datetime(2026, 7, 21, tzinfo=UTC)
    )
    assert bundle.classification == "SYNTHETIC_FIXTURE"
    assert len(bundle.commercial_inputs) >= 3
    assert all(item.status is AssumptionStatus.APPROVED for item in bundle.assumptions.values())
    assert all(item.truth_class is TruthClass.ASSUMPTION for item in bundle.assumptions.values())
    assert all(
        item.owner and item.rationale and item.unit and item.expires_at
        for item in bundle.assumptions.values()
    )
    assert all(item.assumption_ids for item in bundle.commercial_inputs.values())


def test_expired_commercial_fixture_is_blocked() -> None:
    with pytest.raises(ValueError, match="expired"):
        load_commercial_fixture(
            build_default_twin_service().current(), at=datetime(2028, 1, 1, tzinfo=UTC)
        )
