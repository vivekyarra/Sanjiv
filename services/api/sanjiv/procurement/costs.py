from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from sanjiv.contracts import FreshnessStatus, MetricEnvelope, SourceRef, TruthClass
from sanjiv.procurement.contracts import LandedCostBreakdown


class CostConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(min_length=1, max_length=100)
    canonical_unit: str = "USD_per_tonne"
    tolerance: float = Field(gt=0, le=1e-3)
    emissions_enabled: bool = False
    emissions_disabled_rationale: str | None = Field(default=None, max_length=500)


class CostInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    values: Mapping[str, float]
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=2000)
    assumption_ids: list[UUID] = Field(default_factory=list, max_length=2000)
    currency: str = Field(min_length=3, max_length=3)
    basis_unit: str = Field(min_length=1, max_length=50)
    effective_at: datetime
    expires_at: datetime | None = None


class ConversionRate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    from_currency: str = Field(min_length=3, max_length=3)
    to_currency: str = Field(min_length=3, max_length=3)
    rate: float = Field(gt=0)
    effective_at: datetime
    expires_at: datetime | None = None
    evidence_ids: list[UUID] = Field(min_length=1, max_length=100)


def normalize_cost_value(
    value: float,
    *,
    from_currency: str,
    from_unit: str,
    canonical_currency: str = "USD",
    canonical_unit: str = "USD_per_tonne",
    conversion: ConversionRate | None = None,
    at: datetime,
) -> float:
    if not math.isfinite(value) or value < 0:
        raise ValueError("cost value must be finite and non-negative")
    if from_unit != "per_tonne":
        raise ValueError("unsupported cost basis unit")
    if from_currency == canonical_currency:
        return value
    if (
        conversion is None
        or conversion.from_currency != from_currency
        or conversion.to_currency != canonical_currency
    ):
        raise ValueError("an exact currency conversion is required")
    if conversion.effective_at > at or (
        conversion.expires_at is not None and at >= conversion.expires_at
    ):
        raise ValueError("currency conversion is stale or expired")
    if canonical_unit != "USD_per_tonne":
        raise ValueError("unsupported canonical cost unit")
    return value * conversion.rate


def reconcile_landed_cost(
    components: Mapping[str, float],
    *,
    configuration: CostConfiguration,
    evidence_ids: list[UUID],
    assumption_ids: list[UUID],
    at: datetime,
) -> LandedCostBreakdown:
    names = (
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
    if any(name not in components for name in names):
        raise ValueError("all structural landed-cost components are required")
    values = {name: float(components[name]) for name in names}
    if any(not math.isfinite(value) or value < 0 for value in values.values()):
        raise ValueError("landed-cost components must be finite and non-negative")
    if not configuration.emissions_enabled and abs(values["emissions"]) > configuration.tolerance:
        raise ValueError("disabled emissions component must be zero")
    if not configuration.emissions_enabled and not configuration.emissions_disabled_rationale:
        raise ValueError("disabled emissions component requires an explicit rationale")
    total = sum(values.values())
    if not math.isfinite(total) or abs(total - sum(values.values())) > configuration.tolerance:
        raise ValueError("landed-cost components do not reconcile")

    def metric(value: float, name: str) -> MetricEnvelope[float]:
        return MetricEnvelope(
            value=value,
            unit=configuration.canonical_unit,
            truth_class=TruthClass.MODELED,
            confidence=1.0,
            evidence_ids=evidence_ids or [UUID(int=0)],
            source_refs=[SourceRef(source_id="procurement-cost-model", record_id=name)],
            effective_at=at,
            fetched_at=at,
            computed_at=at,
            freshness_status=FreshnessStatus.CURRENT,
            transformation="procurement.landed-cost.v1",
            model_version=configuration.version,
        )

    return LandedCostBreakdown(
        **{name: metric(value, name) for name, value in values.items()},
        total=metric(total, "total"),
    )
