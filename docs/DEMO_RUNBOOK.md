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

## Phase 2 Digital Twin path

1. Open `http://localhost:3000/digital-twin` and read the persistent assumption-driven, non-live banner before interpreting the graph.
2. Show snapshot version and fingerprint, then the mass-balance card. The committed reference result is 250.0 ktonne/day supply, 250.0 ktonne/day demand, and 0.0 residual at `1e-6` tolerance.
3. Select a supplier, load port, chokepoint, Indian port, refinery, and reserve site. For each, show its canonical ID, unit, truth class, confidence, evidence, and any expiring assumption.
4. On a reserve site, show public capacity as `OBSERVED` and current fill as `UNKNOWN`. Do not infer available drawdown.
5. Select a maritime/logistics edge and show capacity, transit time, distance, endpoints, and input provenance.
6. Select a crude grade and compare its deterministic refinery-compatibility classes and component explanation. State that the committed grade properties and refinery operating limits are fixture assumptions.
7. Open `/api/v1/twin/snapshots/current` and verify the UI version/fingerprint exactly match the API response.

## Phase 3 Scenario Lab path

1. Start the credential-free stack, open `http://localhost:3000/scenario-lab`, and show that the active interpreter is `deterministic` while the optional LLM is unavailable.
2. Select the immutable Phase 2 snapshot. Enter `Close the Strait of Hormuz for 14 days.` or use the equivalent structured chokepoint-closure form.
3. Compile and show the typed candidate, resolved Hormuz asset, explicit UTC start and day unit, visible defaults/assumptions, validation warnings, input fingerprint, and frozen snapshot fingerprint. Explain that the bounded parser does not understand arbitrary language.
4. Confirm as the local demo identity. Show that confirmation is a separate server-side action with an audit timestamp and scenario fingerprint; compilation alone cannot execute.
5. Start the no-action run and show persisted polling progress. Cancellation may be demonstrated before starting a fresh run.
6. On completion, show measured runtime, unchanged baseline versus disrupted result, zero affected Hormuz route flow, refinery-throughput impact, daily and cumulative shortfall, affected assets/routes, and invariant status.
7. Show the deterministic lower/central/upper sensitivity range and state that it is bounded sensitivity, not probability.
8. Show evidence and assumption references. Inventory must say `UNKNOWN` unless an explicit, expiring starting-inventory assumption was entered; an assumption-dependent trajectory is not observed stock.
9. Re-run the exact confirmed scenario to show fingerprint result reuse. Change any scenario field to show that a new fingerprint and confirmation are required.
10. End Phase 3 without generating procurement, rerouting, or reserve recommendations; those are future-response planning outside this phase.

## Failure branches

- AIS fails: show interruption and age, then show the automatic audited replay transition, dataset classification, original interval, and persistent non-live banner.
- LLM fails or is not configured: show the typed provider state, open the structured form or bounded deterministic parser, validate it, and continue without a credential.
- Market/source data is stale: show stale inputs and their effect; use an explicit assumption only with operator confirmation.
- Solver is infeasible: show diagnostics, adjust a visible policy assumption, create a new run, and preserve the failed run.
- Solver times out: show no plan unless an exact-fingerprint cached plan exists; label that plan cached and stale.
- Evidence audit fails: show the blocked metric/claim and do not approve the plan.

End by explaining the human checkpoint: Sanjiv recommends and records approval; it does not place orders or release reserves.
