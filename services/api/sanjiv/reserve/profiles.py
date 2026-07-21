from sanjiv.reserve.contracts import ReservePolicyProfile, ReservePolicyWeights


def reserve_policy(profile: ReservePolicyProfile) -> ReservePolicyWeights:
    values = {
        ReservePolicyProfile.CONSERVATIVE: (1000.0, 12.0, 1.0, 18.0, 0.70),
        ReservePolicyProfile.BALANCED: (1000.0, 6.0, 1.0, 8.0, 0.55),
        ReservePolicyProfile.AGGRESSIVE_CONTINUITY: (1000.0, 1.0, 1.0, 2.0, 0.35),
        ReservePolicyProfile.NO_RESERVE_USE: (1000.0, 0.0, 0.0, 0.0, 1.0),
    }
    shortage, depletion, logistics, vulnerability, floor = values[profile]
    return ReservePolicyWeights(
        profile=profile,
        version=f"reserve-policy-calibration-v1:{profile.value}",
        shortage=shortage,
        reserve_depletion=depletion,
        logistics_cost=logistics,
        future_vulnerability=vulnerability,
        minimum_floor_fraction=floor,
    )
