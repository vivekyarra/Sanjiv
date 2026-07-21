from __future__ import annotations

from sanjiv.procurement.contracts import (
    ObjectiveWeight,
    ObjectiveWeights,
    ProcurementProfile,
)

PROFILE_VERSION = "procurement-objectives-v1"

_CALIBRATION: dict[ProcurementProfile, dict[str, float]] = {
    ProcurementProfile.LOWEST_COST: {
        "landed_cost": 1.0,
        "shortfall": 1_000.0,
        "delay": 0.05,
        "route_risk": 0.02,
        "supplier_concentration": 2.0,
        "corridor_concentration": 2.0,
        "compatibility_penalty": 0.1,
        "emissions": 0.02,
    },
    ProcurementProfile.BALANCED: {
        "landed_cost": 0.8,
        "shortfall": 1_000.0,
        "delay": 0.2,
        "route_risk": 0.15,
        "supplier_concentration": 20.0,
        "corridor_concentration": 20.0,
        "compatibility_penalty": 0.5,
        "emissions": 0.1,
    },
    ProcurementProfile.HIGHEST_RESILIENCE: {
        "landed_cost": 0.3,
        "shortfall": 1_000.0,
        "delay": 0.5,
        "route_risk": 0.5,
        "supplier_concentration": 80.0,
        "corridor_concentration": 80.0,
        "compatibility_penalty": 1.0,
        "emissions": 0.2,
    },
}


def objective_weights(profile: ProcurementProfile) -> ObjectiveWeights:
    values = _CALIBRATION[profile]
    return ObjectiveWeights(
        profile=profile,
        version=f"{PROFILE_VERSION}:{profile.value.lower()}",
        **{key: ObjectiveWeight(value=value) for key, value in values.items()},
    )


def all_objective_weights() -> list[ObjectiveWeights]:
    return [objective_weights(profile) for profile in ProcurementProfile]
