# Sanjiv Test Strategy

Tests must prove truth handling and physical/solver invariants, not only endpoint success. Fixed inputs use fixed seeds, frozen clocks, canonical units, and versioned golden files.

## Test layers

- Unit/property tests: Pydantic validation, normalization, geometry, freshness, formulas, claim rules, and solver invariants.
- Contract tests: source payload fixtures, OpenAPI snapshots, generated TypeScript drift, error shapes, and WebSocket schemas.
- Integration tests: PostgreSQL/PostGIS/TimescaleDB, Redis, MinIO, migrations, worker outbox, replay, API, and HiGHS.
- End-to-end tests: browser workflow from map mode through scenario confirmation, plans, evidence, and approval.

## Phase 3 coverage

Offline tests cover contract/unit validation, supported and refused compiler patterns, provider-neutral adapter behavior, no-provider/timeout/invalid-output fallback, prompt-injection attempts, snapshot/asset resolution, duplicate/conflicting effects, expired assumptions, fingerprint stability/invalidation, server-side confirmation/audit/idempotency, and the complete API lifecycle.

Golden/invariant tests cover baseline and per-step mass conservation; non-negative flow/inventory; closed/reduced routes; supplier/refinery constraints; crude compatibility; cumulative aggregation; baseline/snapshot immutability; deterministic replay, uncertainty, and reuse; cancellation/failure/runtime; persistent PostgreSQL readback; and reversible migration cycles. Frontend tests assert the structured fallback, provider state, validation/default/assumption review, explicit confirmation, progress/terminal states, inventory truth label, and absence of procurement recommendations.

CI needs no LLM or source credential. Provider tests use deterministic fakes; live OpenAI operation is not part of the Phase 3 gate.
- Non-functional tests: latency, vessel/map load, source failures, security, recovery, and reproducibility.

## Required cases

| Area | Minimum assertions |
|---|---|
| Coordinates | Accept boundary values; reject NaN, latitude outside ±90, longitude outside ±180; preserve WGS84 order. |
| Timestamp ordering | Reject effective after fetched or fetched after computed; handle equal times and timezone normalization. |
| AIS deduplication | Duplicate provider ID and duplicate vessel/time/position are idempotent; legitimate same-time corrections are versioned. |
| Geofence intersection | Crossing, tangent, boundary, dateline, and no-intersection cases; known chokepoint fixtures. |
| Source freshness | Cadence-specific boundary, stale transition, unavailable health, cache age, and replay status. |
| Sanctions matching | Exact IMO/MMSI, aliases, normalized names, fuzzy review threshold, false positives, and source version. |
| Inventory mass balance | Residual within tolerance for every site/time; no hidden creation, loss, or negative stock. |
| Closed route | 100% capacity loss forces zero flow; alternative edge must be explicit. |
| Refinery capacity | Throughput never exceeds effective capacity; outages and interval conversion respected. |
| Reserve floor | Draw never exceeds stock/rate or breaches policy floor; transit delay conserved. |
| Optimiser feasibility | Independent checker reports zero hard violations; infeasible inputs return diagnostics and no plan. |
| Reproducibility | Same canonical inputs, versions, and seed yield the same allocations/objective within tolerance. |
| Grade exclusion | Hard-incompatible or sanctioned grades have zero allocation despite lower cost. |
| Claim blocking | Cargo ownership, charter availability, private inventory/contract/fill, and exact price claims are blocked without supplied evidence. |
| Replay fallback | Mode switch is visible, explained, audited, and uses original timestamps; automatic failure fallback and replay are never `LIVE`. |
| API failure | Timeouts, 429, malformed payloads, unavailable stores, duplicate idempotency keys, and partial commit rollback. |
| LLM fallback | Invalid JSON, unknown asset, timeout, prompt injection, and no credential produce the structured form without running. |
| Performance | Measure ingest-to-map p95, compile, simulation, optimisation, end-to-end latency, WebSocket loss, and map FPS under declared load. |

Additional model properties: increasing a disruption cannot improve the paired no-action case absent an explicitly modeled side effect; initial inventory plus inflow equals processing plus ending inventory plus declared loss; landed-cost components reconcile; supplier/corridor concentration limits hold; uncertainty outputs retain seed and distributions; stability is invariant to action ordering.

Phase 2 additionally fixes the snapshot twice and requires identical fingerprints/UUIDs; checks all graph endpoints and canonical-ID uniqueness; proves supplier, transit-node, refinery, and global mass balance; rejects route over-capacity and incompatible allocations; verifies all entity evidence/assumption links; asserts assumptions expire; keeps reserve fill unknown; contract-tests all four import boundaries; cycles migration `0002 -> 0003 -> 0002 -> 0003`; and asserts the UI exposes snapshot, truth, evidence, assumptions, compatibility, and non-live fixture labels.

## Gates

- Phase gate: all phase unit, integration, failure, and contract tests pass; no skipped critical invariant.
- Decision release: zero unsupported definitive claims, zero hard solver violations, 100% evidence coverage for decision KPIs, and migrations upgrade/downgrade cleanly.
- Performance numbers are labeled targets until produced by a stored benchmark report including hardware, dataset size, run ID, percentile, and timestamp.
- Security gate: dependency and image scan, secret scan, authorization tests, upload limits, log-redaction test, and no browser-visible server keys.

## Phase 4 coverage

Focused tests cover commercial-fixture classification/expiry, canonical units and non-finite rejection, option/input/plan fingerprints, deterministic profile ordering, real Pyomo/HiGHS solves, every hard-constraint family, objective reconstruction, checker forgery, closed routes, infeasible/error contracts, exact-fingerprint reuse, PostgreSQL restart readback, production mutation security, idempotency, reversible `0005` migration, generated OpenAPI/TypeScript, and Response Planner truth/no-execution labels. The full gate retains credential-free operation and exercises Compose PostgreSQL, Redis, and MinIO.

## Phase 5 coverage

Focused tests cover all four policy profiles, public-capacity/opening-fill separation, unknown and expired inventory, policy floors, draw/route/transit/receipt limits, stock conservation, `NO_RESERVE_USE`, exact procurement coordination, shortage/objective reconstruction, checker forgery, deterministic fingerprints and reuse, PostgreSQL restart readback, API idempotency and production security, reversible `0006` migration, generated contracts, and Strategic Reserve truth/no-execution labels.
# Phase 6 risk gate

The focused Phase 6 suite covers deterministic baseline/scoring fingerprints, finite-value validation, explicit missingness, stale source degradation, severity/confidence/completeness separation, false-news and thermal ambiguity suppression, source disagreement, source outage/rate-limit failures, lifecycle validation, alert corroboration, replay checksums and ten required cases, fixture-only metrics, API schemas, PostgreSQL restart readback, migration reversibility/immutability, and UI truth/freshness/no-execution wording. The release gate then runs the full repository lint, strict typing, tests, generated-contract drift, production build, Docker config, migration cycle, dependency/license, secret, skipped-test, and focused security/data/model reviews.

## Phase 7 evidence and approval gate

Focused tests cover procurement and reserve plans at 100% decision-metric provenance; missing,
tampered, stale, expired, and superseded inputs; truth transitions; objective and fingerprint
recomputation; solver/checker/auditor failure; sanctions and compatibility exclusions; unsupported
claim and unaudited-figure blocking; caller-forged actor/role/status; production fail-closed identity;
stale plan/assumption/audit hashes; lifecycle ordering, concurrency and idempotency abuse; immutable
approval records; PostgreSQL restart readback; migration downgrade/re-upgrade; canonical APIs;
generated-contract drift; and every evidence/assumption/audit/review UI path. A failed metric must
remain in the API and UI with its reason and cannot be approved or exported.

## Phase 8 validation gate

- Validate at least 20 independently named replay cases, manifest/payload checksums, classification,
  license, redistribution status, assumptions, invariants, expected outcomes, and restart readback.
- Execute every case, including stale evidence and solver infeasibility, and assert blocked status is
  explicit rather than omitted.
- Verify LPG unit consistency, mass conservation, supplier/route/terminal capacity, sanctions and
  compatibility exclusions, three response profiles, and `NOT_APPLICABLE` reserve handling without
  weakening crude tests.
- Prove fast/deep sensitivity reproducibility, stored seed/design/ranges/correlations, quantiles,
  drivers, stability version, and explicit non-probability language.
- Assert every JSON/PDF export value equals audited API context, failed audits block plan exports,
  content checksums survive readback, comments are immutable/idempotent/server-attributed, and
  monitoring exposes deviations/staleness without execution controls.
- Exercise the Historical Replay UI's replay, crude/LPG, sensitivity, export, comment, monitoring,
  truth-label, keyboard, responsive, empty/loading/error, and no-autonomous-execution paths.

## Phase 9 release gate

- Clean locked npm/uv installs; Compose infrastructure, `app`, and credential-free `offline`
  profiles; migration downgrade/re-upgrade; all Python/web/contract tests; Ruff; strict mypy;
  ESLint; TypeScript; contract drift; and production Next.js/Docker builds.
- Playwright drives the real 1920x1080 Observe-to-Monitor journey, risk, reserve, evidence,
  replay, LPG and audited export, captures actual screenshots and forbids focused-only tests.
- Stored benchmarks cover ingest-to-map, WebSocket resync, browser FPS/interaction, all decision
  engines, audit/export, end-to-end flow and declared concurrent load; measurements are not SLAs.
- Security covers fail-closed auth/roles, origin/rate/size/type, idempotency, SSRF, redaction,
  bounded solver/LLM behavior, injection review, secrets, dependencies, licenses and both images.
- Recovery covers database/Redis/MinIO interruption, worker staleness, API restart, backup/restore,
  corrupted artifacts, migration cycles and offline preflight.
