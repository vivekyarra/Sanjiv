# Sanjiv Demo Runbook

## Preflight

1. Run the full verification suite and record the commit, model versions, hardware, and benchmark report.
2. Confirm source credentials without displaying them; inspect every source’s health, cadence, and latest evidence time.
3. Validate the recorded-real replay manifest and checksum. Keep fixtures clearly separate.
4. Confirm the main Hormuz scenario and two alternate supported scenarios are feasible with current data/assumptions.
5. Open the command center with no stale approval or scenario state. Never prewrite a latency result.

## Exact demonstration path

1. Open directly on the live tanker map. State “Sanjiv — India’s Energy Resilience Command Center” and “Keep India’s energy moving.”
2. Point to the global `LIVE`/`REPLAY` mode and individual source freshness. If live data is unavailable, acknowledge and enter recorded-real replay before continuing.
3. Enter exactly: **“The Strait of Hormuz loses 100% capacity for 72 hours.”**
4. Show the validated, editable scenario object: canonical asset, 100% loss, 72 hours, start, horizon, reserve policy, uncertainty, and visible assumptions. Confirm it.
5. On the map, show observed vessel positions separately from inferred India-bound candidates; open one confidence breakdown and state that cargo ownership and charter availability are unknown.
6. Show the paired no-action impact: shortfall, arrivals/delay, refinery utilization, inventory cover, and uncertainty, each with truth labels.
7. Generate **Lowest cost**, **Balanced**, and **Highest resilience** through the deterministic optimiser; show solver state and actual runtime.
8. Select **Balanced** without approving it.
9. Show modeled procurement allocations, rerouting, reserve actions, shortfall avoided, landed-cost change, residual risk, and remaining reserve; call candidate transport capacity unverified commercially.
10. Open **Why this plan?** Show hard constraints, objective contributions, trade-off weights, assumptions, and at least one rejected alternative.
11. Open the evidence drawer for one major metric. Show source references, effective/fetch/compute times, freshness, truth class, transformation, confidence, evidence IDs, and model version.
12. Show the measured signal-to-recommendation latency from the run record. If it exceeds 10 seconds, show the actual value and call 10 seconds a target.
13. Ask for and run a second supported scenario. Unsupported assets produce a controlled refusal and supported choices, never invented data.

## Failure branches

- AIS fails: show interruption and age, request/confirm replay, show recorded capture interval, then continue.
- LLM fails: open the pre-populated structured form, validate it, and continue.
- Market/source data is stale: show stale inputs and their effect; use an explicit assumption only with operator confirmation.
- Solver is infeasible: show diagnostics, adjust a visible policy assumption, create a new run, and preserve the failed run.
- Solver times out: show no plan unless an exact-fingerprint cached plan exists; label that plan cached and stale.
- Evidence audit fails: show the blocked metric/claim and do not approve the plan.

End by explaining the human checkpoint: Sanjiv recommends and records approval; it does not place orders or release reserves.
