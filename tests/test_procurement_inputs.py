from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sanjiv.procurement.costs import CostConfiguration, reconcile_landed_cost


def test_landed_cost_reconciles_structural_components() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    evidence = [uuid4()]
    result = reconcile_landed_cost(
        {
            "commodity_price": 70,
            "quality_differential": 2,
            "freight": 5,
            "insurance_and_risk_premium": 1,
            "port_and_handling": 1,
            "route_fees": 0,
            "financing": 1,
            "emissions": 0,
            "compatibility_penalty": 0,
        },
        configuration=CostConfiguration(
            version="cost-v1",
            tolerance=1e-9,
            emissions_disabled_rationale="Phase 4 emissions data disabled",
        ),
        evidence_ids=evidence,
        assumption_ids=[],
        at=now,
    )
    assert result.total.value == 80
    assert result.total.unit == "USD_per_tonne"


def test_landed_cost_rejects_non_finite_and_missing_components() -> None:
    config = CostConfiguration(
        version="cost-v1",
        tolerance=1e-6,
        emissions_disabled_rationale="disabled",
    )
    with pytest.raises(ValueError, match="all structural"):
        reconcile_landed_cost(
            {},
            configuration=config,
            evidence_ids=[uuid4()],
            assumption_ids=[],
            at=datetime.now(UTC),
        )
    values = {
        name: 1.0
        for name in (
            "commodity_price",
            "quality_differential",
            "freight",
            "insurance_and_risk_premium",
            "port_and_handling",
            "route_fees",
            "financing",
            "emissions",
            "compatibility_penalty",
        )
    }
    values["freight"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        reconcile_landed_cost(
            values,
            configuration=config,
            evidence_ids=[uuid4()],
            assumption_ids=[],
            at=datetime.now(UTC),
        )
