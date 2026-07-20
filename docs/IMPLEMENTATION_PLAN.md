# Sanjiv Implementation Plan

Phases are dependency ordered. Complexity is relative: S/M/L/XL. A phase closes only after its measurable gate and tests pass; demo appearance alone is insufficient.

## Phase 0 — Repository foundation and truth/data contracts (M)

- **Goal:** reproducible workspace and enforceable provenance foundation.
- **Deliverables/modules:** npm/uv workspaces; Next.js and FastAPI shells; Compose for PostgreSQL/PostGIS/TimescaleDB, Redis, MinIO; `contracts`, `evidence`, `sources`, `assumptions`, `audit`, migrations, OpenAPI-to-TypeScript generation, CI-ready commands.
- **Dependencies/order:** toolchain → containers → canonical Pydantic contracts → migration → TS generation → health/readiness → tests/docs.
- **Acceptance/gate:** clean locked install; reversible migration; all sample metrics have complete envelopes/evidence or assumptions; no secret committed; lint/type/test/contract/build pass.
- **Tests:** unit—truth transitions, timestamps, confidence, metric envelope; integration—DB constraints, object hash metadata, OpenAPI generation; failure—missing evidence/credential/store and generated-contract drift.
- **Demo result:** health/source-capability page and inspectable sample evidence metric, explicitly fixture-labeled.
- **Risks:** over-designing schema, local extension compatibility. Keep contracts minimal and test migrations against the Compose image.
- **Parallel:** web shell, container setup, and contract examples after naming conventions are fixed.

## Phase 1 — Live maritime twin and replay system (XL)

- **Goal:** honest live/replayed tanker operations with chokepoint detection.
- **Deliverables/modules:** `ingestion/aisstream`, vessel normalization/dedup, Timescale positions, PostGIS chokepoints, exact/fuzzy OFAC matching, India-bound inference, raw recording/manifests, replay sessions, operational WebSocket, `web/map` deck.gl layers and source/mode UI.
- **Dependencies/order:** source/evidence contracts → adapter/recording → normalization/storage → geofences/inference/sanctions → snapshot/WebSocket → map → replay transition.
- **Acceptance/gate:** a recorded and a live-if-credentialed vessel crossing are detected and visible; gaps/staleness/mode are correct; no cargo/charter claim.
- **Tests:** unit—coordinates, ordering, dedup, destination normalization, confidence contributions, sanctions; integration—adapter→DB→outbox→WS→map and replay checksum; failure—disconnect, malformed AIS, rate/backpressure, Redis/MinIO interruption, missing key.
- **Demo result:** moving tankers, observed/inferred separation, tracks, chokepoints, freshness, live/replay banner.
- **Risks:** coverage, licensing, message volume, browser FPS. Use viewport queries, retention/aggregation, and recorded-real fallback.
- **Parallel:** map rendering, OFAC adapter, and replay UI after normalized event schema freezes.

## Phase 2 — India energy network digital twin (L)

- **Goal:** versioned, mass-conserving crude-supply graph.
- **Deliverables/modules:** `twin/{assets,graph,snapshots}`, PPAC/ISPRL/Comtrade/reference importers, suppliers, ports, refineries, reserve sites, routes, 12–20 sourced crude grades, compatibility matrix, baseline flows, network UI.
- **Dependencies/order:** reference adapter imports → canonical IDs → graph/connectivity → compatibility assumptions → baseline calibration → immutable snapshot.
- **Acceptance/gate:** every node/edge/input has evidence or assumption; baseline supply/demand and unit conversions conserve within tolerance.
- **Tests:** unit—IDs, units, grade scoring, route restrictions; integration—source import→snapshot→NetworkX graph; failure—unknown links, duplicate assets, incompatible grade, missing/private inventory.
- **Demo result:** selectable Indian infrastructure and supply corridors with evidence-backed baseline flows.
- **Risks:** sparse public refinery constraints and current inventories. Use visible, expiring assumptions and aggregate where evidence is weak.
- **Parallel:** grade curation, geospatial asset curation, and graph UI after schemas stabilize.

## Phase 3 — Scenario compiler and impact simulator (XL)

- **Goal:** turn natural language into confirmed scenarios and simulate the paired no-action consequence.
- **Deliverables/modules:** `scenarios/{interpreter,validator,resolver}`, provider-neutral LLM adapter, structured-form fallback, `simulation/{timeline,mass_balance,uncertainty}`, progress events, Scenario Lab UI.
- **Dependencies/order:** twin snapshot → deterministic scenario form/validator → optional LLM interpreter → baseline/disruption engine → uncertainty → audited outputs.
- **Acceptance/gate:** main and supported compound scenarios validate; all physical invariants pass; unsupported assets are refused; fast simulation target measured, not claimed.
- **Tests:** unit—duration/ranges/assets/defaults, mass balance, route zero flow, throughput; integration—compile→confirm→worker→results; failure—LLM timeout/invalid JSON/injection, unknown asset, stale snapshot, job cancellation.
- **Demo result:** validated Hormuz object, animated disruption, no-action shortfall/inventory/refinery metrics.
- **Risks:** hidden defaults, dimensional errors, latency. Freeze snapshots and expose all defaults/units.
- **Parallel:** form/UI and simulator internals after Scenario schema freezes.

## Phase 4 — Procurement optimiser (XL)

- **Goal:** three feasible, reproducible, costed procurement alternatives.
- **Deliverables/modules:** `optimisation/{inputs,procurement,profiles,checker,explanations}`, Pyomo model, HiGHS runner, landed-cost service, rejected-option diagnostics, Response Planner UI. Reserve policy is fixed input in this phase.
- **Dependencies/order:** simulation outputs/cost inputs → variables/hard constraints → lowest-cost profile → checker → balanced/resilience profiles → explanations/UI.
- **Acceptance/gate:** zero independently checked hard violations across the scenario library; same fingerprint reproduces allocation/objective; infeasibility never yields a plan.
- **Tests:** unit—cost terms, constraints, incompatible/sanctioned exclusion, concentration; integration—run→three plans→evidence audit; failure—infeasible budget/capacity, timeout, solver error, stale cached fingerprint.
- **Demo result:** three comparable plans, reroutes/procurement, cost-risk trade-off, reasons for rejected options.
- **Risks:** assumed spot availability/cost, poorly scaled penalties. Label assumptions and calibrate profiles with sensitivity tests.
- **Parallel:** model, explanation views, and benchmark library after input/output contract freezes.

## Phase 5 — Strategic-reserve optimiser (L)

- **Goal:** site-level drawdown/replenishment guidance coordinated with procurement.
- **Deliverables/modules:** `optimisation/reserves`, joint input builder, site logistics/floors, policy profiles, independent checker, Strategic Reserve UI.
- **Dependencies/order:** reserve evidence/assumptions → site mass balance/logistics → standalone model → coordinated solve → explanations/UI.
- **Acceptance/gate:** every short and extended test preserves stock, floor, draw, receipt, and connectivity constraints; current fill is never assumed observed.
- **Tests:** unit—floor/draw rate/transit/replenishment; integration—procurement+reserve paired run; failure—unknown fill, disconnected site, infeasible floor, extended disruption.
- **Demo result:** site/date/quantity/refinery schedule, remaining cover, policy-mode trade-off.
- **Risks:** confidential fill and operational limits. Require verified user input or visible assumptions and avoid execution claims.
- **Parallel:** reserve UI and model after the reserve contract is fixed.

## Phase 6 — Risk intelligence and alerting (XL)

- **Goal:** evidence-backed corridor risk signals without presenting severity as probability.
- **Deliverables/modules:** GDELT, PortWatch, EIA/FRED, FIRMS adapters; `risk/{features,severity,confidence,alerts}`; anomaly baselines; sanctions changes; alert/timeline UI.
- **Dependencies/order:** adapters/history → feature normalization → severity/confidence/completeness → corroboration/alert rules → backtest → UI.
- **Acceptance/gate:** versioned backtests report lead time, precision/false positives, completeness, and source failures; risk and confidence remain separate.
- **Tests:** unit—feature scaling/contributions/freshness; integration—multi-source evidence→alert; failure—false news spike, thermal ambiguity, source disagreement/outage/rate limit.
- **Demo result:** ranked corridors with contribution/evidence drawer and timeline.
- **Risks:** false certainty, changing schemas, sparse ground truth. Require corroboration and calibrated language.
- **Parallel:** independent source adapters and historical-label curation after feature contracts.

## Phase 7 — Evidence Auditor and explainability (L)

- **Goal:** make unsupported decision outputs structurally impossible to present as approved.
- **Deliverables/modules:** `audit/{coverage,claims,recompute,policies}`, formula/version registry, audit trail, explanation input builder, Evidence/Assumptions UI.
- **Dependencies/order:** all decision contracts → coverage/truth validation → claim policy → recomputation/hash → narrative guard → approval enforcement.
- **Acceptance/gate:** 100% decision-KPI provenance and zero unsupported definitive claims across tests; failed audit blocks display/approval/export.
- **Tests:** unit—truth transitions, evidence graph, claim phrases, model version; integration—plan→audit→explanation→approval; failure—missing/stale evidence, tampered hash, LLM embellishment, superseded assumption.
- **Demo result:** “Why this plan?”, metric evidence drawer, rejected alternatives, immutable approval audit.
- **Risks:** rules bypassed in UI/export. Enforce in server application services and test every presentation path.
- **Parallel:** claim policy and evidence UI after audit-result contract freezes.

## Phase 8 — Historical replay, LPG, briefing export, and advanced UX (XL)

- **Goal:** prove generality, historical behavior, and decision-package usability.
- **Deliverables/modules:** curated replay catalogue/backtests, LPG assets/models, FIRMS layer, sensitivity controls, stability calculation, collaboration/approval UX, briefing/PDF export, plan monitoring.
- **Dependencies/order:** replay foundation/model audit → historical cases → LPG extensions → advanced analysis → export/monitoring.
- **Acceptance/gate:** at least 20 checksumed replay cases with stored metrics; LPG case passes commodity invariants; exported values match audited API results exactly.
- **Tests:** unit—LPG units/stability/export transforms; integration—replay→detection→plan→briefing; failure—corrupt manifest, unsupported commodity conversion, export evidence gap, concurrent review.
- **Demo result:** historical validation, LPG scenario, sensitivity/stability, downloadable briefing and tracked approval.
- **Risks:** scope dilution and licensing. Crude gates remain mandatory; ship only licensed/redacted replay data.
- **Parallel:** replay curation, LPG reference data, and export design after Phase 7 contracts.

## Phase 9 — Integration, performance, security, failure testing, and demo hardening (L)

- **Goal:** demonstrate reliable behavior under realistic load and failure.
- **Deliverables/modules:** full Compose profiles, observability, benchmark harness/reports, browser suite, security/secret/image scans, backup/restore, failure injection, offline demo package, rehearsed runbook.
- **Dependencies/order:** production build → end-to-end dataset → performance profile → bottleneck fixes → security/failure/recovery → offline package → rehearsal.
- **Acceptance/gate:** stored measurements for all latency/FPS targets; zero critical security issues/hard model violations/unsupported claims; full live and replay rehearsals; restore and rollback tested.
- **Tests:** integration/end-to-end all phases; failure—API/rate/network/store/worker/solver/LLM/browser interruption; security—authz, upload, SSRF, secrets, dependency/image; performance—declared vessel/sample/concurrency loads.
- **Demo result:** repeatable primary and judge-selected scenarios with honest degradation and measured signal-to-recommendation latency.
- **Risks:** demo network/hardware variance and late integration. Freeze a release candidate and retain explicit recorded-real replay.
- **Parallel:** security, performance, browser automation, and runbook rehearsal on the same release candidate.

## Immediate implementation task

Implement only Phase 0’s repository foundation and canonical truth-contract vertical slice: workspace/manifests, service shells, Compose dependencies, truth/freshness/metric/evidence/source-health/assumption/audit contracts, first migration, generated TypeScript copy with drift check, health/readiness, and tests. Do not add AIS, maps, scenario execution, simulation, optimisation, or other Phase 1+ behavior.
