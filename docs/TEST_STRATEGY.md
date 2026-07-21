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
