# Sanjiv Model Specification

All time-indexed volumes use one configured base unit, initially metric tonnes, and all rates are converted to volume per interval before arithmetic. Every model input is an envelope-backed observation, derivation, or assumption. Equations below are final structural forms; coefficients labeled **calibration** are versioned configuration and are not factual constants.

## Inventory and throughput

For refinery `r` and interval `t` of duration `Δt`:

```text
I[r,t+1] = I[r,t] + A[r,t] + Q[r,t] - P[r,t] - L[r,t]
0 <= I[r,t+1] <= storage_capacity[r]
P[r,t] = U[r,t] * Δt
0 <= U[r,t] <= throughput_capacity[r,t]
L[r,t] >= 0
```

`I` is opening inventory, `A` commercial arrivals, `Q` reserve release received, `P` processed volume, and `L` validated physical loss/adjustment. Unserved processing demand is a separate nonnegative `shortage[r,t]`; inventory is never made negative to encode shortage. Throughput capacity combines nameplate capacity, outage multiplier, logistics availability, and compatible feedstock.

## Route disruption and compatibility

```text
effective_capacity[p,t] = nominal_capacity[p,t]
  * product(disruption_multiplier[e,p,t])
0 <= flow[p,t] <= effective_capacity[p,t]
```

A 100% loss gives multiplier zero and therefore zero flow. Alternative routes are independent edges and are never enabled unless present in the frozen twin.

Grade/refinery compatibility is the weighted sum of normalized gravity, sulfur, configuration, and logistics components. **Calibration:** component weights and classification thresholds. A hard `allowed[g,r]` matrix is derived from sourced limits plus visible assumptions; `allowed=0` prevents flow regardless of the soft score.

## India-bound confidence and corridor risk

```text
C_india = 0.30 D + 0.25 R + 0.20 H + 0.15 P + 0.10 V
RiskSeverity = 0.30 T + 0.25 G + 0.15 A + 0.15 M + 0.10 S + 0.05 I
```

These initial weights are **calibration**, not final scientific constants. Components are normalized to `[0,1]`, missing components are not silently zeroed, and output includes contributions and completeness. India-bound is `INFERRED`. Corridor risk is a severity score scaled to 0–100, not disruption probability.

Evidence confidence combines source reliability, freshness, completeness, agreement, and transformation confidence using a documented versioned function. **Calibration:** component weights and source reliability priors. It cannot upgrade stale or assumption-only evidence to observed fact.

## No-action baseline

The no-action run applies the confirmed disruption to the same twin snapshot, demand, initial state, and uncertainty samples as response runs, while disallowing new procurement, rerouting decisions, discretionary reserve release, and demand interventions. Already committed arrivals continue unless the disrupted graph makes them infeasible. This paired design isolates response benefit.

## Landed cost

```text
landed_cost = commodity_price
            + quality_differential
            + freight
            + insurance_and_risk_premium
            + port_and_handling
            + canal_or_route_fees
            + financing_cost
            + emissions_cost_if_enabled
            + compatibility_penalty
```

Currency and unit conversion use effective-dated evidence. Unavailable commercial quotes are assumptions with ranges, never observed spot availability.

## Procurement model

Decision `x[s,g,r,p,t] >= 0` is delivered volume. Auxiliary variables represent shortage, concentration, delay, and soft-policy violations.

```text
minimise landed_cost
       + λ1*shortage + λ2*delay + λ3*route_risk
       + λ4*concentration + λ5*compatibility_penalty
       + λ6*reserve_depletion + λ7*emissions
```

Hard constraints enforce supplier/grade availability, route/chokepoint/port capacity, draught and vessel class, delivery window, budget, refinery throughput, hard grade compatibility, sanctions exclusion, inventory mass balance, reserve floor, and configured supplier/corridor concentration limits. Shortage may be allowed only as an explicit penalized feasibility variable. **Calibration:** plan-profile λ weights, soft penalties, concentration policy, uncertain availability, and budget assumptions. Hard physical and sanctions constraints are final.

## Reserve model

```text
minimise shortage + α*reserve_depletion
                  + β*logistics_cost + γ*future_vulnerability
```

Release variables are bounded by site inventory, draw rate, connection capacity, transit delay, receiving capacity, and policy minimum floor. Remaining stock is conserved by site and interval. Phase 4 holds reserve policy fixed; Phase 5 solves procurement and reserve actions from one shared input snapshot. **Calibration:** α, β, γ, policy floors, replenishment outlook, and extension-risk assumptions.

## Uncertainty and stability

Fast mode uses a fixed, recorded sample design of 30–50 draws; deep mode uses at least 500. The run stores seed, sampling method, distributions, correlations, and input evidence. Report median, P10/P90, best/worst sampled cases, and ranked sensitivity drivers; do not label these confidence intervals unless statistically justified.

For reference plan `a*`, plan stability is:

```text
stability = count(similarity(a_k, a*) >= τ) / N
```

Similarity is one minus normalized L1 distance over supplier-route allocation shares, with separate action-set agreement for reserve decisions. **Calibration:** similarity threshold `τ`, material-volume cutoff, and qualitative High/Medium/Low bands. The raw fraction and method version are always shown.

## Validation

Every solution is independently checked for mass-balance residual, bound/constraint violation, objective reconstruction, sanctions/compatibility exclusion, and deterministic reproduction tolerance. Failed checks block the plan. Model cards record final equations, calibrated values, training/backtest period where relevant, limitations, and version history.
