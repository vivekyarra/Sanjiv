# Sanjiv Demo Runbook

## Preflight

1. Run the full verification suite and record the commit, model versions, hardware, and benchmark report.
2. Confirm source credentials without displaying them; inspect every source’s health, cadence, and latest evidence time.
3. Validate the selected replay manifest and checksum. State whether it is `RECORDED_REAL_DATA` or `SYNTHETIC_FIXTURE`; keep the classifications separate.
4. Confirm the main Hormuz scenario and two alternate supported scenarios are feasible with current data/assumptions.
5. Open the command center with no stale approval or scenario state. Never prewrite a latency result.

## Phase 1 demonstration path

1. Set `SANJIV_REPLAY_SPEED=1`, start PostgreSQL, upgrade migrations, then start the web and API commands from `docs/PHASE_1_LIVE_MARITIME_WATCH.md` close together so the 70-second fixture movement is visible.
2. Open `http://localhost:3000` on Live Maritime Watch.
3. Point to connection state, source health, last update, and freshness before interpreting a marker.
4. With no AISStream key, show the persistent `REPLAY — NOT LIVE DATA` banner and explain `AISSTREAM_NOT_CONFIGURED`. State that the dataset is a synthetic fixture with fictional vessels.
5. Select each vessel and show its recent track, reported destination, position truth class, evidence UUID, source/fetch times, transformation, adapter version, and confidence.
6. Contrast the source position with the `INFERRED` India-bound likelihood and its disclaimer. State that Sanjiv does not know cargo ownership or charter availability.
7. Show the dashed chokepoint and port areas and state that these Phase 1 polygons are non-authoritative `ASSUMPTION` fixtures.
8. Open `/api/v1/operations/mode-transitions` and `/api/v1/sources/health` to show the recorded fallback reason and `REPLAY` freshness.
9. Stop the API, restart it, and confirm the latest vessels and `/history` remain available from PostgreSQL with the same evidence IDs.
10. If an operator supplies an AISStream key, restart and wait for a validated message before showing `LIVE`. Do not claim live operation when no validated live record exists.

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

- AIS fails: show interruption and age, then show the automatic audited replay transition, dataset classification, original interval, and persistent non-live banner.
- LLM fails: open the pre-populated structured form, validate it, and continue.
- Market/source data is stale: show stale inputs and their effect; use an explicit assumption only with operator confirmation.
- Solver is infeasible: show diagnostics, adjust a visible policy assumption, create a new run, and preserve the failed run.
- Solver times out: show no plan unless an exact-fingerprint cached plan exists; label that plan cached and stale.
- Evidence audit fails: show the blocked metric/claim and do not approve the plan.

End by explaining the human checkpoint: Sanjiv recommends and records approval; it does not place orders or release reserves.
