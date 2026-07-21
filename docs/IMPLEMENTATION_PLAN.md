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

- **Status (2026-07-20):** Phase 1 vertical slice implemented. Optional AISStream live operation remains credential-dependent and was contract-tested with mocks; the committed demo dataset is explicitly synthetic, not recorded-real AIS.
- **Goal:** honest live/replayed tanker operations with chokepoint detection.
- **Completed deliverables/modules:** provider-neutral `maritime/adapters`; configured AISStream WebSocket adapter; deterministic replay adapter and checksummed manifest; validation/quarantine; vessel normalization/dedup; Timescale positions; PostGIS tracks/geofences/events; exact-identifier and fuzzy-name sanctions matcher with `DERIVED`/`INFERRED` separation; India-bound inference; secret-free raw recording spool; audited operating-mode transitions; snapshot/history/source-health REST; cursor-based operational WebSocket; MapLibre map, tracks, selected-vessel provenance, connection/freshness states, and persistent replay banner.
- **Deliberately incomplete/optional:** no OFAC download is bundled, so default status is `NOT_SCREENED`; no live AIS claim is made without a configured credential; the committed dataset is a CC0 synthetic fixture because restricted AIS data must not be redistributed. MapLibre native layers are used at current fixture volume; deck.gl remains an evidence-based scale-up option.
- **Dependencies/order:** source/evidence contracts → adapter/recording → normalization/storage → geofences/inference/sanctions → snapshot/WebSocket → map → replay transition.
- **Acceptance/gate:** deterministic replay crossings are detected and visible; the mocked live-provider path uses the same canonical schema; gaps/staleness/mode are explicit; no cargo/charter claim; migration upgrades, downgrades, and re-upgrades. A real live crossing is not claimed or required in CI.
- **Tests:** unit—coordinates, timestamp ordering, dedup, normalization, freshness, inference, exact/fuzzy sanctions labels, geofence entry/exit; integration—replay→normalization→repository→WebSocket/map contracts and migration cycle; failure—disconnect/fallback, malformed AIS quarantine, bounded subscriber backpressure/resync, missing key, replay checksum tamper.
- **Demo result:** moving vessels, observed/inferred separation, tracks, chokepoints, freshness, live/replay banner.
- **Measurable completion gate:** backend and frontend tests pass; OpenAPI generation is clean; production build passes; replay emits eight messages in deterministic order; seven non-authoritative geofences load; CI uses no credentials or network data; actual `0001→0002→0001→0002` migration cycle passes.
- **Risks:** AISStream is beta with no SLA; coverage and licensing vary; browser basemap tiles need connectivity; the in-process broker is single-instance. Use viewport queries/aggregation and Redis fan-out only after measured need.
- **Parallel:** map rendering, OFAC source acquisition, and replay UI after normalized event schema freezes.

## Phase 2 — India energy network digital twin (L)

- **Status (2026-07-20):** Implemented on `feature/phases-2-9-overnight-integration`; phase gate results and checkpoint are recorded in `OVERNIGHT_EXECUTION_LOG.md`.
- **Goal:** versioned, mass-conserving crude-supply graph.
- **Deliverables/modules:** `twin/{assets,graph,snapshots}`, PPAC/ISPRL/Comtrade/reference importers, suppliers, ports, refineries, reserve sites, routes, 12–20 sourced crude grades, compatibility matrix, baseline flows, network UI.
- **Dependencies/order:** reference adapter imports → canonical IDs → graph/connectivity → compatibility assumptions → baseline calibration → immutable snapshot.
- **Acceptance/gate:** every node/edge/input has evidence or assumption; baseline supply/demand and unit conversions conserve within tolerance.
- **Tests:** unit—IDs, units, grade scoring, route restrictions; integration—source import→snapshot→NetworkX graph; failure—unknown links, duplicate assets, incompatible grade, missing/private inventory.
- **Demo result:** selectable Indian infrastructure and supply corridors with evidence-backed baseline flows.
- **Risks:** sparse public refinery constraints and current inventories. Use visible, expiring assumptions and aggregate where evidence is weak.
- **Parallel:** grade curation, geospatial asset curation, and graph UI after schemas stabilize.

## Phase 3 — Scenario compiler and impact simulator (XL)

- **Status:** complete on the Phase 3 integration checkpoint; Phase 4 has not started.
- **Goal:** turn natural language into confirmed scenarios and simulate the paired no-action consequence.
- **Deliverables/modules:** `scenarios/{interpreter,validator,resolver}`, provider-neutral LLM adapter, structured-form fallback, `simulation/{timeline,mass_balance,uncertainty}`, progress events, Scenario Lab UI.
- **Dependencies/order:** twin snapshot → deterministic scenario form/validator → optional LLM interpreter → baseline/disruption engine → uncertainty → audited outputs.
- **Acceptance/gate:** main and supported compound scenarios validate; all physical invariants pass; unsupported assets are refused; fast simulation target measured, not claimed.
- **Tests:** unit—duration/ranges/assets/defaults, mass balance, route zero flow, throughput; integration—compile→confirm→worker→results; failure—LLM timeout/invalid JSON/injection, unknown asset, stale snapshot, job cancellation.
- **Demo result:** validated Hormuz object, animated disruption, no-action shortfall/inventory/refinery metrics.
- **Risks:** hidden defaults, dimensional errors, latency. Freeze snapshots and expose all defaults/units.
- **Parallel:** form/UI and simulator internals after Scenario schema freezes.
- **Implemented result:** canonical generated contracts; structured and bounded-text compilers; optional provider-neutral/OpenAI boundary; snapshot-aware deterministic validation; audited confirmation; persistent jobs with polling progress, cancellation, typed failure, and fingerprint reuse; a daily mass-conserving no-action engine; deterministic bounded sensitivity; and the operational Scenario Lab.
- **Demo result:** a confirmed 14-day Hormuz closure uses the immutable Phase 2 snapshot and shows unchanged baseline, zero disrupted flow on affected route segments, refinery throughput loss, daily/cumulative shortfall, deterministic bounds, measured runtime, and provenance without procurement or reserve recommendations.

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

### Phase 5 completion: checked strategic-reserve guidance

Status: complete. Canonical contracts, an expiring offline operational-input fixture, exact Phase 4 coordination, versioned four-policy Pyomo/HiGHS solves, independent conservation/objective/fingerprint checks, immutable PostgreSQL persistence and reuse, POST/GET APIs, generated contracts, and `/strategic-reserve` are implemented. Capacity remains sourced separately from assumption-backed opening fill; no release authority or execution path exists.

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

Status: complete. The server audits every procurement
and reserve decision metric, evidence/assumption integrity and freshness, truth transitions,
versions, exact fingerprints, recomputation, solver/checker state, sanctions/compatibility
exclusions, and claim language. Failed metrics remain visible and block usable presentation,
approval, export, and definitive narrative. Deterministic explanations, server-owned roles,
append-only review/approval/rejection/supersession, migration `20260721_0008`, restart-readable
APIs, and the `/evidence-approval` UI are implemented without any operational execution path.
The Phase 7 gate passed with 100% provenance on the seeded procurement and reserve plans,
reversible migration `0008 -> 0007 -> 0008`, 166 Python tests, 19 web tests, the generated-contract
test, strict lint/type checks, production build, dependency audits, persistence readback, and
immutable-record enforcement.

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

## Current implementation program

Phase 0 and Phase 1 are merged. The active program implements Phases 2-9 in dependency order with a hard full-repository gate and pushed checkpoint after every phase. No later phase may start while the preceding gate is failing.
### Phase 4 completion: deterministic procurement optimiser

Status: complete. The deterministic input and landed-cost boundary now feeds a bounded Pyomo/HiGHS model for all three profiles, an independent constraint/objective/fingerprint checker, immutable PostgreSQL persistence and exact-fingerprint reuse, documented POST/GET APIs, and the Response Planner. Commercial values remain expiring assumptions from a credential-free `SYNTHETIC_FIXTURE`; no order, tanker, commercial availability, or reserve action is claimed.
# Phase 6 completion note

Phase 6 implements provider-neutral risk adapters, deterministic effective-dated baselines, six-component structural scoring, separate severity/confidence/completeness, corroborated analyst-only alerts, immutable PostgreSQL persistence, read-only risk APIs, a checksummed ten-case synthetic replay/backtest library, and `/risk-intelligence`. It deliberately does not implement Phase 7 audit/approval behavior.
