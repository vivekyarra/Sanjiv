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

Phase 2 calibration uses `0.35 gravity + 0.35 sulfur + 0.15 configuration + 0.15 logistics`. Gravity and sulfur scores fall from one outside the visible assumed refinery range/tolerance; configuration is currently a visible `0.75` fixture assumption and logistics is one only for the connected reference network. Classification thresholds remain `PREFERRED >= 0.80`, `ACCEPTABLE >= 0.60`, `DIFFICULT >= 0.40`, and otherwise `DISALLOWED`. These are model parameters, not observed refinery operating limits.

The baseline graph validator aggregates each supplier-grade allocation over every route in its explicit path. Supplier outflow equals declared baseline supply, every load port/chokepoint/Indian port has inflow equal to outflow, refinery inflow equals declared demand, and global supply equals demand within `1e-6 ktonne_per_day`. A route over capacity, disconnected supplier/reserve site, unknown endpoint, incompatible delivered grade, or non-zero residual blocks snapshot creation.

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

Phase 4 implements the frozen optimiser boundary with Pyomo `procurement-pyomo-highs-v1` and HiGHS. The nonnegative decision is horizon-total delivered `ktonne` per exact supplier/grade/load-port/route-segment/receiving-port/refinery/delivery option; explicit refinery shortage reconciles horizon demand. Segment, port, supplier, refinery, budget, sanctions, compatibility, timing, and concentration constraints are hard. All three profiles share those inputs and constraints and differ only through `procurement-objectives-v1` weights. `procurement-independent-checker-v1` reconstructs quantities, landed cost, objective, mass balance, concentration, timing, capacity, sanctions/compatibility, and fingerprints before a plan is usable.

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

At the Phase 4 contract boundary, the reserve policy is identified by an immutable fingerprint and explicitly sets `decision_variables_enabled=false` and `release_schedule_fixed=true`. No reserve quantity is selected, recommended, or varied by a procurement profile.

## Phase 3 deterministic no-action model

The Phase 3 time step is one UTC day. For baseline path `p` with flow `B_p`, full closure has surviving fraction `0`, and a reduction of `q percent` has surviving fraction `1 - q/100`. Supplier, port, route/chokepoint, and refinery effects apply only to resolved targets. The path flow is:

```text
F[p,t] = min(B[p], supplier_available[p,t], min(disrupted_capacity[r,t]))
```

Every segment on a path receives the same `F[p,t]`, preventing intermediate creation or loss. Refinery receipt is the sum of compatible inbound paths, and throughput is:

```text
T[j,t] = min(baseline_throughput[j], compatible_receipts[j,t], disrupted_refinery_capacity[j,t])
shortfall[j,t] = max(0, baseline_throughput[j] - T[j,t])
```

Cumulative shortfall is the exact timeline sum. The engine enforces non-negative quantities; closed-route zero flow; route, supplier, and refinery caps; crude compatibility; per-step path mass conservation; unchanged baseline; immutable snapshot input; and deterministic fingerprints. Unsafe inputs return a typed failure.

Inventory is calculated only when an explicit, unexpired starting-inventory assumption exists: `I[j,t+1] = max(0, I[j,t] + receipts[j,t] - T[j,t])`. Such trajectories are assumption-dependent and never observed inventory.

Phase 3 uncertainty is bounded deterministic sensitivity, not probability. It varies each active disruption reduction by minus and plus 10 percentage points within `[0,100]`, re-runs the same equations, and reports central/lower/upper cumulative shortfall, parameters varied, method, assumption dependencies, and model version.

## Uncertainty and stability

Fast mode uses a fixed, recorded sample design of 30–50 draws; deep mode uses at least 500. The run stores seed, sampling method, distributions, correlations, and input evidence. Report median, P10/P90, best/worst sampled cases, and ranked sensitivity drivers; do not label these confidence intervals unless statistically justified.

For reference plan `a*`, plan stability is:

```text
stability = count(similarity(a_k, a*) >= τ) / N
```

Similarity is one minus normalized L1 distance over supplier-route allocation shares, with separate action-set agreement for reserve decisions. **Calibration:** similarity threshold `τ`, material-volume cutoff, and qualitative High/Medium/Low bands. The raw fraction and method version are always shown.

## Validation

Every solution is independently checked for mass-balance residual, bound/constraint violation, objective reconstruction, sanctions/compatibility exclusion, and deterministic reproduction tolerance. Failed checks block the plan. Model cards record final equations, calibrated values, training/backtest period where relevant, limitations, and version history.
### Phase 4 deterministic input boundary

The procurement input builder now consumes only an exact completed simulation,
confirmed scenario, and immutable twin snapshot. It emits deterministically
ordered eligible options and structured exclusions; no volume allocation or
solver execution occurs. Landed cost is reconciled in `USD_per_tonne` with a
configured numerical tolerance and the frozen structural component list.
