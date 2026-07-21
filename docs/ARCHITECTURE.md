# Sanjiv Architecture

## System context

Sanjiv is a human-in-the-loop decision-intelligence system for national energy-supply resilience. Analysts observe sourced signals, compile a disruption, compare the no-action consequence with deterministic response plans, inspect evidence, and explicitly approve or reject a plan. External sources never call operational systems through Sanjiv, and Sanjiv does not place orders or release reserves.

```text
Official/public sources + user inputs
                 |
          adapters and validation
                 v
     evidence ledger + operational stores
                 |
 live twin -> scenario -> simulation -> procurement/reserve solvers
                 |                         |
                 +------ evidence audit ---+
                              |
                    command-center UI
                              |
                    human approval record
```

## Containers and components

- **Web:** Next.js UI, MapLibre/deck.gl map, ECharts, REST queries, WebSocket updates, evidence drawer, and approval UI. It never holds source or LLM secrets.
- **API modular monolith:** FastAPI modules for contracts, sources, evidence, maritime, twin, scenarios, simulation, procurement, reserves, risk, audit, replay, approvals, and exports. Modules communicate through typed application services, not internal HTTP.
- **Workers:** `ingestion` for streaming sources, `refresh` for scheduled sources, and `compute` for simulation/optimisation jobs. All import the same domain modules as the API.
- **PostgreSQL:** authoritative relational state. PostGIS stores geometry; TimescaleDB hypertables store vessel positions and time series.
- **Redis:** cache, rate coordination, WebSocket fan-out, job progress, and short leases. It is not authoritative evidence storage.
- **MinIO/S3:** immutable raw captures, replay segments, exported briefings, and large source artifacts. PostgreSQL stores hashes and metadata.

## Data and execution flows

### Ingestion and evidence ledger

1. Scheduler or streaming worker checks adapter capability and circuit state.
2. Adapter retrieves a payload with server-side credentials and records fetch metadata.
3. Raw bytes are hashed and written immutably to object storage when licensing permits.
4. Schema validation, normalization, deduplication, coordinate/time checks, and source-ID mapping run deterministically.
5. One or more evidence records link the source record, raw hash, transformation, effective/fetch times, license, and truth class.
6. Valid observations are committed with an outbox event; rejects are quarantined with a non-secret reason.
7. The outbox publishes normalized updates to Redis after commit.

### Live WebSocket

The Phase 1 browser obtains a snapshot cursor over read-only REST and opens `/ws/v1/operations?after=<cursor>`. The in-process broker emits versioned envelopes with monotonically increasing sequence IDs and bounded per-subscriber queues. Retained deltas are replayed on reconnect. An expired cursor or queue overflow emits `RESYNC_REQUIRED`, causing a snapshot refetch. Heartbeats carry cursor, mode, connection state, and freshness; the client reconnects with exponential backoff capped at 30 seconds. Redis fan-out and authenticated multi-user operations remain later deployment work.

### Live Maritime Watch vertical slice

`AISSourceAdapter` isolates providers from normalization. `AISStreamAdapter` connects only from the backend, applies bounded retries/timeouts and a bounded WebSocket queue, and never exists when its feature flag or credential is absent. `ReplayAISAdapter` verifies a manifest checksum and emits the identical `RawAISMessage` contract. The normalizer validates coordinates, identifiers, and ordered UTC timestamps; creates immutable evidence; and either persists canonical positions or writes only a reason code and payload hash to quarantine. PostgreSQL stores vessel identity, Timescale position history, PostGIS tracks/geofences/events, replay metadata, and audited mode transitions. Current map state is cached in-process for presentation latency; PostgreSQL remains authoritative.

### Digital twin

Versioned suppliers, ports, chokepoints, routes, refineries, reserve sites, grades, and baseline flows form a directed NetworkX graph. A snapshot builder resolves one effective time, records every evidence/assumption dependency, validates units and connectivity, and produces a content-addressed immutable `TwinSnapshot`. Simulation and optimisation consume only a snapshot ID, never mutable “latest” tables.

Phase 2 implements this boundary in `sanjiv/twin`. PPAC-, ISPRL-, UN Comtrade-, and repository-shaped importers validate typed offline reference batches without making network calls. Canonical UUIDv5 identifiers are derived from stable domain IDs. A deterministic `MultiDiGraph` validates endpoints, supplier/reserve-to-refinery reachability, weak connectivity, route capacity, grade compatibility, and node/global mass balance before snapshot construction. The snapshot fingerprint covers ordered content, evidence, assumptions, compatibility, and the mass-balance report; the database migration rejects `UPDATE` and `DELETE` on stored snapshots. The current committed twin is an assumption-driven fixture except for cited ISPRL public capacity metadata and is never presented as live operational state.

### Scenario execution

1. The structured form, bounded deterministic parser, or optional provider produces the same typed scenario candidate. Optional provider output is untrusted.
2. Deterministic validation resolves canonical asset IDs, units, ranges, defaults, visible assumptions, and the selected immutable snapshot.
3. The user confirms the validated candidate; the API writes an audit event and freezes scenario and twin fingerprints.
4. The Phase 3 application service executes the deterministic daily baseline/disrupted model. Its persisted job contract is worker-ready, while this checkpoint deliberately uses documented immediate in-process execution.
5. Clients poll persisted progress events and results. Cancellation and typed failure use the same REST transport; no redundant event framework is introduced.
6. Results are persisted as metric envelopes and preserve evidence, assumption, truth, freshness, transformation, unit, timestamp, and model provenance.

PostgreSQL stores candidates, validation reports, immutable confirmations, runs, results, and progress payloads. Complete simulation fingerprints provide idempotent reuse and restart-safe result access. The engine only reads the content-addressed Phase 2 snapshot and never mutates it.

### Procurement optimisation

The simulator produces time-indexed demand, arrivals, inventory, and affected capacities. Pyomo constructs the selected plan profile—lowest cost, balanced, or highest resilience—with the same hard constraints and different versioned objective weights. HiGHS returns status, variables, objective components, violations, and diagnostics. An independent checker recalculates feasibility and landed cost before persistence. Phase 4 treats reserve availability as a fixed policy input.

### Reserve optimisation

Phase 5 implements site/refinery dispatch, transit, receipt, remaining-inventory, and residual-shortage decisions in `sanjiv/reserve`. The input builder binds one exact independently checked Phase 4 plan and the same scenario/result/twin identities. Public storage capacity stays `OBSERVED`; opening fill is accepted only as verified input or an unexpired visible `ASSUMPTION`, and unknown sites are blocked. Procurement and reserve models coordinate through exact committed receipts and shared refinery capacity. Policy modes alter calibrated objective weights and floors, never physical conservation or capacity constraints. Replenishment is absent unless supplied by verified input.

### Risk intelligence

Phase 6 remains a domain module in the FastAPI modular monolith. Provider-neutral adapters emit normalized raw risk signals and typed failures; the deterministic feature engine owns baselines, missingness, contributions, corroboration, severity, confidence, and completeness. The alert evaluator consumes only a complete fingerprinted result and produces analyst-only append-only alerts. PostgreSQL stores baselines, features, contributions, calculations, failures, alerts, timelines, lifecycle transitions, and replay backtests. The Next.js `/risk-intelligence` route reads only the typed risk APIs and holds no provider credential.

The primary demo and CI select a checksummed offline replay adapter. Optional GDELT, PortWatch, EIA/FRED, FIRMS, sanctions-boundary, and Phase 1 AIS fetchers are injected server-side behind bounded timeout/retry/rate-limit policies; they cannot silently switch a record from live to fixture mode.

### Audit and explanation

The evidence auditor verifies schema completeness, allowed truth transitions, evidence existence, freshness policy, assumption visibility, model versions, claim policy, and metric recomputation hashes. Failed metrics are blocked, not silently omitted. Narrative generation receives only audited structured results and evidence summaries. Every run, mode transition, edit, approval, export, and failure creates an append-only audit event.

Phase 7 implements this boundary in `sanjiv/audit`. Coverage walks every `MetricEnvelope` in the
immutable procurement or reserve plan. Policies validate evidence hashes and parent links,
approved/unexpired/scenario-scoped assumptions, freshness, truth transitions, source and
transformation fields, versions, exact fingerprints, solver state, independent-check results,
sanctions/compatibility exclusions, and objective/fingerprint recomputation. The deterministic
explanation builder reads only a passed or explicitly blocked structured audit. Lifecycle state is
derived from append-only records rather than mutating the optimizer plan. PostgreSQL advisory
locking serializes concurrent actions; database triggers reject updates and deletes.

Development identities are an explicit configured map. Production governance has no default
identity: API keys map server-side to actor and role, and absent configuration fails closed. An
approval is a human decision record only; there is no adapter for purchasing, chartering, reserve
release, pipeline control, or other operational execution.

### Replay and fallback

Phase 1 replay datasets have checksummed manifests, classification, source attribution, original source interval, transformation, and license/redistribution metadata. If the live adapter is absent or exhausts bounded retries, the service automatically records an audit-linked `DEGRADED→REPLAY` transition so the demonstration remains available. This is never silent: REST, WebSocket, source-health UI, and the persistent banner identify replay and explain the reason. Original source timestamps are preserved and fixture positions are `ASSUMPTION` with `REPLAY` freshness. A future authenticated operator-control phase may add manual replay sessions; Phase 1 exposes no administrative mutation endpoint.

## Security boundaries

- Browser: untrusted input; no infrastructure, source, solver, or LLM credentials.
- API: authentication, authorization, validation, rate limits, CSRF/origin policy, and approval enforcement.
- Workers: least-privilege source and storage credentials; no interactive user session.
- Data stores: private network only, separate roles, encrypted transport, restricted object buckets, backups, and retention policy.
- External/user data: SSRF-safe adapters, size/type limits, malware scanning for uploads, license enforcement, and log redaction.
- Solver/LLM: bounded resources and strict typed input/output; neither receives secrets or unnecessary raw private data.

## Deployment topology

Local and demo deployment uses Docker Compose: `web`, `api`, three worker processes, PostgreSQL with PostGIS/TimescaleDB, Redis, MinIO, and an optional reverse proxy/telemetry profile. Production begins with the same containers on a single managed host or small container service, managed databases/object storage where available, TLS termination, backups, and OpenTelemetry export. Scaling is vertical first, then worker replicas by measured queue latency. Kubernetes and domain microservices require an ADR backed by workload measurements.

Phase 4 remains inside the FastAPI modular monolith: thin procurement routes call a typed application service, which builds immutable domain inputs, invokes bounded in-process Pyomo/HiGHS, runs a separate arithmetic checker, and writes content-addressed terminal JSONB plus normalized actions/rejections. A worker move is deferred until measured solve concurrency requires it; the public contract and fingerprints do not depend on execution placement.
