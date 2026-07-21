# Sanjiv Architecture Decisions

## ADR-001: Modular monolith

**Decision:** One FastAPI application organized by domain, one Next.js application, and separate processes only for ingestion, scheduled refresh, and compute jobs.

**Why:** It preserves clear boundaries and independent worker scaling without distributed transactions or hackathon-time operational overhead. **Rejected:** Kubernetes and service-per-domain microservices; no measured workload justifies them.

## ADR-002: Deterministic optimisation

**Decision:** Procurement and reserve recommendations are produced by versioned Pyomo models solved with HiGHS. Fixed inputs, model version, solver version, and seed produce reproducible results.

**Why:** Constraints, feasibility, objective contributions, and rejected options remain testable. **Rejected:** LLM-generated operational advice and a dual-solver abstraction in v1.

## ADR-003: Structured model orchestration

**Decision:** A provider-neutral LLM adapter may translate natural language into a typed scenario and explain audited results. Deterministic validators, simulators, and solvers do all calculations.

**Why:** Natural-language flexibility is useful, but free-form agent handoffs are not reliable operational interfaces. If the LLM fails, the editable structured form remains available. **Rejected:** decorative multi-agent personas and provider-coupled domain logic.

## ADR-004: Evidence ledger and explicit truth classes

**Decision:** Immutable source evidence and transformations are linked to every decision metric. All metrics use `OBSERVED`, `DERIVED`, `INFERRED`, `MODELED`, or `ASSUMPTION`.

**Why:** Users can distinguish source facts from calculations and assumptions, reproduce results, and block unsupported claims. **Rejected:** citations attached only to narrative text or a single dashboard-wide “live” badge.

## ADR-005: Recorded-real replay

**Decision:** Replay datasets retain source, capture interval, checksum, license, and redaction metadata. Fixtures remain separate and visibly labeled.

**Why:** Demonstrations survive connectivity failures without pretending synthetic or historical values are live. **Rejected:** silent fallback and seeded data labeled as recorded.

## ADR-006: Human approval gates

**Decision:** Plans move through `RECOMMENDED`, `UNDER_REVIEW`, `APPROVED`, `REJECTED`, and `SUPERSEDED`. Approval records actor, time, plan hash, assumptions hash, and comment. Sanjiv does not place orders or release reserves.

**Why:** Recommendations depend on incomplete public data and material policy choices. **Rejected:** autonomous execution or UI-only approval state.

## ADR-007: Workspace and contracts

**Decision:** npm workspaces manage TypeScript, uv manages Python, and Pydantic/OpenAPI generates TypeScript contracts. PostgreSQL/PostGIS/TimescaleDB is authoritative; Redis handles ephemeral state; MinIO stores raw/replay objects.

**Why:** This matches the selected stack while keeping contract ownership singular. **Rejected:** duplicated hand-written schemas and event-stream infrastructure before load measurements.

## ADR-008: Automatic, explicit Phase 1 replay fallback

**Decision:** Missing AIS credentials or exhausted bounded provider retries automatically move Live Maritime Watch to replay. The transition and reason are audit-linked, source health reports `REPLAY`, original timestamps remain unchanged, and the UI shows a persistent `REPLAY — NOT LIVE DATA` banner.

**Why:** The Phase 1 completion gate requires the product to remain demonstrable when live AIS fails. Requiring an acknowledgement before the read-only map can recover conflicts with that gate. **Rejected:** silent fallback, rewriting replay timestamps to look current, and unauthenticated mode-control endpoints.

## ADR-009: MapLibre-native Phase 1 layers

**Decision:** Phase 1 renders its bounded vessel, track, and polygon fixture set with MapLibre-native GeoJSON layers. deck.gl is reserved for a measured scale threshold.

**Why:** Native layers meet the current operational slice with fewer runtime dependencies. **Rejected:** paid map SDKs and adding a second renderer before browser profiling shows a need.

## ADR-010: Phases 2-9 supersede the stale Phase 0 immediate-task note

**Decision:** The dependency-ordered Phase 2 through Phase 9 sections of `IMPLEMENTATION_PLAN.md` control the current integration program. The old final sentence limiting work to Phase 0 is historical drift: Phase 0 and Phase 1 are already merged into `main`, and the explicitly authorized Phases 2-9 program supersedes that sentence.

**Why:** Continuing to apply an already-completed Phase 0-only instruction would contradict repository history, the merged Phase 1 status, and the current task without improving safety. All existing truth, evidence, approval, testing, licensing, and failure gates remain binding. **Rejected:** silently deleting the conflict or weakening later phase gates.

## ADR-011: Phase 2 offline reference twin and assumption boundary

**Decision:** Phase 2 ships a deterministic, content-addressed reference twin through provider-neutral PPAC, ISPRL, UN Comtrade, and repository-fixture import interfaces. ISPRL public site capacity is represented as sourced `OBSERVED` factual metadata; current reserve fill remains absent and `UNKNOWN`. Supplier flows, operating capacities, routes, refinery limits, grade properties, and baseline allocations in the committed demo are expiring `ASSUMPTION` records from CC0 project fixtures. No upstream raw publication is redistributed.

**Why:** CI and the primary demo must be credential-free and legally safe, while sparse or non-public operational values must not be fabricated as observations. The fixture exercises the same typed import boundary as future verified source payloads, preserves provenance, and makes replacement explicit. **Rejected:** scraping undocumented endpoints, bundling data with unclear redistribution rights, treating public reserve capacity as fill, or labelling calibrated demo values live.

## ADR-012: Phase 3 confirmed deterministic execution boundary

**Decision:** Structured entry is canonical and always available. A deliberately bounded text parser and optional provider-neutral OpenAI Responses adapter produce the same untrusted `ScenarioCandidate`; deterministic validation against one immutable twin snapshot is authoritative. Server-side confirmation freezes the scenario/snapshot fingerprints before documented immediate in-process simulation. PostgreSQL persists candidates, validation, confirmation, progress, results, and audit linkage; clients use REST polling. Exact complete simulation fingerprints may reuse a result. Inventory stays unknown without an explicit, unexpired assumption.

**Why:** The primary demo and CI must remain credential-free, provider output must not acquire authority, and the no-action comparison must be reproducible and restart-readable. Polling matches the existing transport needs and avoids a second event framework before measured scale requires it. **Rejected:** arbitrary-language claims, provider-side simulation, automatic execution, mutable latest snapshots, inferred private reserve fill, probabilistic labels for bounded sensitivity, and Phase 4 procurement logic in Phase 3.

## ADR-013: Phase 4 checked procurement boundary

**Decision:** Phase 4 uses only Pyomo and in-process HiGHS with bounded model size/time, one deterministic continuous delivered-volume model, identical hard constraints for all profiles, and versioned objective weights. Every usable result is independently reconstructed from the immutable input before content-addressed PostgreSQL persistence. The offline commercial fixture is expiring `ASSUMPTION` data and cannot establish availability. Reserve release remains fixed outside the model.

**Why:** A solver status alone cannot establish physical or provenance validity, while a credential-free demo still needs multiple inspectable alternatives. Independent checks and exact-fingerprint reuse keep recommendations reproducible without inventing quotes or execution authority. **Rejected:** generated-prose recommendations, autonomous purchasing, reserve variables, silent default commercial values, unchecked timeout incumbents, and mutable terminal plans.
