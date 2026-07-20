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
