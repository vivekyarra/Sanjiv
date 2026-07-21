# Sanjiv Data Contracts

Canonical contracts are Pydantic v2 models exposed through OpenAPI and generated into TypeScript. IDs are UUIDs unless a stable external code is explicitly named. Timestamps are UTC RFC 3339. Geometries use WGS84/EPSG:4326 GeoJSON; longitude is `[-180,180]` and latitude `[-90,90]`.

## Common types

```json
{
  "value": 74.0,
  "unit": "percent",
  "truth_class": "MODELED",
  "confidence": 0.77,
  "evidence_ids": ["018f..."],
  "source_refs": [{"source_id":"PPAC","record_id":"capacity-2025-04"}],
  "effective_at": "2026-07-20T10:00:00Z",
  "fetched_at": "2026-07-20T10:00:02Z",
  "computed_at": "2026-07-20T10:00:04Z",
  "freshness_status": "CURRENT",
  "transformation": "scenario-engine.inventory_cover.v1",
  "model_version": "impact-engine-1.0.0"
}
```

- `TruthClass`: `OBSERVED | DERIVED | INFERRED | MODELED | ASSUMPTION`.
- `FreshnessStatus`: `LIVE | RECENT | CURRENT | STALE | REPLAY | UNAVAILABLE`.
- `DataMode`: `LIVE | CACHED | REPLAY | FIXTURE | USER_SUPPLIED`.
- `Confidence`: decimal in `[0,1]`; it is evidence/model confidence, never probability unless a calibrated field explicitly says so.
- `MetricEnvelope[T]`: fields shown above; timestamps are required and `effective_at <= fetched_at <= computed_at`. For direct observations, `computed_at` is normalization time and `transformation` names the normalizer.

## Reference and operational entities

| Entity | Required fields and constraints |
|---|---|
| `Vessel` | `id`, `mmsi` (9 digits), optional `imo`, names/aliases, ship type, flag, dimensions, sanctions summary, created/updated times. Ownership/cargo fields are absent unless user supplied. |
| `VesselPosition` | `id`, `vessel_id`, source message ID, timestamp, point, SOG, COG, heading, navigation status, optional draught/destination/ETA, mode, evidence ID. Unique source+message ID; duplicate natural key is vessel+time+position. |
| `Port` | `id`, code/name/country, point or polygon, draught metric, supported vessel classes, handling-capacity metric, source version. |
| `Chokepoint` | `id`, name, polygon/crossing line, directional baseline metrics, nominal capacity metric, alternative route IDs. |
| `Refinery` | `id`, name/operator, point, annual-capacity metric, complexity assumption, grade limits, connected port/route IDs, utilization limits. Private inventory is not a base field. |
| `Supplier` | `id`, country/entity, load ports, export-capacity metric, available-grade IDs, sanctions state, availability truth class. |
| `CrudeGrade` | `id`, name, origin, load ports, API gravity metric, sulfur metric, differential metric, vessel classes, sanctions state, version. |
| `Route` | `id`, origin/destination, LineString, distance/travel-time/capacity/cost/risk/emissions metrics, chokepoint IDs, vessel/draught restrictions, availability multiplier. |
| `ReserveSite` | `id`, name, point, public capacity metric, optional current-fill metric, minimum-floor assumption/policy, connected assets, delivery limits. Current fill must never default to observed. |

## Intelligence, scenario, and plan entities

| Entity | Required fields and constraints |
|---|---|
| `GeopoliticalEvent` | `id`, event type, title/summary, locations, effective interval, actor/entity references, source signal IDs, severity metric, confidence, status. Media records do not prove physical closure. |
| `RiskEvent` | `id`, type, affected asset IDs, start/end, severity metric, evidence-confidence metric, completeness metric, contribution list, status, model version. Severity is not probability. |
| `Scenario` | `id`, name, original text, typed event list, asset/commodity IDs, start, duration, horizon, reserve policy, uncertainty ranges, assumption IDs, validation status, creator, content hash. |
| `ScenarioRun` | `id`, scenario/twin snapshot IDs and hashes, mode, model versions, seed, state, start/end/runtime, baseline/simulation IDs, failure, audit IDs. |
| `SimulationOutput` | `id`, run/case, time grid, arrivals, inventory, throughput, shortage, delay, cost/risk/concentration/emissions metrics, uncertainty summary, invariant report. |
| `ProcurementPlan` | `id`, run ID, `LOWEST_COST | BALANCED | HIGHEST_RESILIENCE`, solver metadata/status, objective components, actions, metrics, constraints report, rejected options, input hash, lifecycle state. |
| `ReservePlan` | `id`, run/policy, site-time-refinery actions, remaining inventory/cover, replenishment guidance, objective components, constraints, solver metadata, lifecycle state. |

## Governance entities

| Entity | Required fields and constraints |
|---|---|
| `Assumption` | `id`, key, typed value/unit, rationale, source gap, owner, entered/approved times and actors, effective/expiry times, status, scenario scope, supersedes ID. Always `ASSUMPTION`. |
| `EvidenceRecord` | `id`, source/record IDs, source URL, dataset/version, effective/fetched times, mode, truth class, raw hash/object reference, transformation/version, confidence, license, parent evidence IDs. Immutable. |
| `SourceHealthRecord` | `id`, source ID, capability state, checked/last-success times, expected cadence, stale-after, lag, message/error counts, circuit state, mode, redacted error code. |
| `AuditEvent` | `id`, timestamp, actor/service, action, resource type/ID, before/after hashes, reason, correlation/causation IDs, IP/session metadata policy, outcome. Append-only. |

## Phase 1 maritime transport contracts

- `RawAISMessage` is the provider-neutral boundary: source and record IDs, source timestamp, fetch timestamp, data mode, dataset/version/license/source URL, and an opaque payload. Extra fields and unordered or naive timestamps are rejected.
- `VesselPosition` stores normalized MMSI/IMO/name/type, WGS84 point, SOG/COG/heading/navigation status, reported destination, separate source/fetch/compute timestamps, source and mode, truth/freshness/confidence, evidence IDs, transformation, and adapter version.
- `VesselTrackSegment.distance_nm` uses the canonical `MetricEnvelope[float]`; geofence entry/exit is `DERIVED` from position evidence plus the geofence fixture evidence.
- `Geofence` includes polygon, kind, source reference, effective time, truth, confidence, evidence ID, transformation/version, and `authoritative`. Phase 1 committed polygons are development approximations: `ASSUMPTION`, low confidence, and `authoritative=false`.
- `ReplayManifest` declares `SYNTHETIC_FIXTURE` or `RECORDED_REAL_DATA`, source, checksum, source-time interval, count, license, redistribution rule, transformation, and adapter version. Its NDJSON records contain source record ID, source timestamp, and provider payload.
- `OperationsEvent` uses schema `1.0`, sequence, event type, event time, operating mode, and typed-by-event payload. `OperationsSnapshot` is the resynchronization authority.
- `OperatingModeTransition` records `from_mode`, `to_mode`, time, reason/explanation, whether automatic, and the associated append-only audit event ID.

## Contract rules

- Preserve raw source values separately from normalized values.
- A derived/inferred/modeled metric references all material parent evidence or assumptions.
- Evidence and audit records cannot be updated; corrections append superseding records.
- Scenario and plan hashes use canonical JSON. A changed assumption creates a new run.

## Phase 3 frozen contracts

`ScenarioCandidate` contains the stable scenario ID, source/compile modes, typed parameters, disruption effects, explicit quantity units, visible defaults and assumptions, interpreter result, selected `TwinSnapshotReference`, evidence IDs, lifecycle, and canonical input fingerprint. `ScenarioValidationResult` separates blocking errors, warnings, defaults requiring confirmation, assumptions requiring confirmation, and resolved assets. `ConfirmedScenario` preserves the exact validation and twin fingerprints, confirming identity, UTC confirmation timestamp, and scenario fingerprint; any candidate edit produces a different fingerprint and requires confirmation again.

`SimulationRun` contains scenario/snapshot/input/simulation fingerprints, model version, configuration, lifecycle status, UTC timestamps, measured runtime, typed failure, cancellation, and result reference. `SimulationResult` contains paired `BaselineResult` and `DisruptedResult`, daily timeline points, route-flow and refinery results, shortfall and cumulative shortfall metric envelopes, optional assumption-dependent inventory trajectories, deterministic uncertainty bounds, invariant results, evidence and assumption references, and complete provenance. All timestamps on the wire are UTC RFC 3339 and all quantities carry explicit units.

Phase 3 reuses `MetricEnvelope`, `EvidenceRef`, `Assumption`, `AuditEvent`, freshness, confidence, and truth-class contracts. Baseline facts retain their existing classification; simulator outputs are `MODELED`. Missing private inventory is not converted into a number.
- A plan cannot become `APPROVED` when audit status is failed, evidence is missing, solver status is not feasible/optimal, or the plan hash differs from the reviewed hash.

## Phase 4 procurement contract checkpoint

The first Phase 4 checkpoint freezes contracts only. `ProcurementOptimisationInput` binds one exact `SimulationRunReference`, `SimulationResultReference`, confirmed-scenario fingerprint, and immutable `TwinSnapshotReference`. It also contains one versioned hard-constraint configuration, a fixed reserve-policy fingerprint with `decision_variables_enabled=false`, bounded candidate options, and the exact SHA-256 hashes of every referenced evidence and approved assumption record. Evidence and assumption fingerprint sets must exactly match the input references; commercial availability, supplier capacity, commodity price, freight, route capacity, and refinery receiving capacity cannot be omitted or hidden outside that set.

`ProcurementPlanRequest` selects one or more unique `ProcurementProfile` values and supplies exactly one versioned `ObjectiveWeights` set for each. Profiles are `LOWEST_COST`, `BALANCED`, and `HIGHEST_RESILIENCE`. Profiles can change only objective weights; physical, sanctions, compatibility, policy, budget, concentration, and fixed-reserve constraints stay in the shared immutable input. The contract does not contain a reserve release decision variable.

`SolverResult` distinguishes `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `TIMEOUT`, `ERROR`, and `NOT_RUN`. Only optimal or feasible results may carry actions, allocations, and an objective, and those states require a feasible `ConstraintReport` plus a passed `IndependentCheckResult`. Infeasible, timed-out, errored, not-run, or independently failed output cannot become a `ProcurementPlan`. `RejectedOption` uses bounded reason codes and relevant hard-constraint IDs, including sanctions, incompatibility, unverified commercial availability, and unverified transport availability.

`ProcurementPlanFingerprintInputs` is canonical JSON over the optimiser model version, profile and objective-weight version, exact solver configuration, optimisation-input hash, hard-constraint and fixed-reserve policy versions, evidence and assumption hashes, and immutable simulation/scenario/twin identities. SHA-256 fingerprints are stable under JSON key ordering and change when any material value or version changes. Output quantities and objectives use `MetricEnvelope` with `MODELED` truth; physical and monetary quantities use explicit validated units.

The future POST and GET procurement API request/response schemas are present in generated OpenAPI and TypeScript contracts, but no callable endpoint, solver, storage, plan generation, recommendation, or approval flow exists in this checkpoint.

## Phase 2 digital-twin contracts

- `TwinNode` uses a deterministic UUIDv5 plus a stable canonical ID and one of `SUPPLIER`, `LOAD_PORT`, `CHOKEPOINT`, `INDIAN_PORT`, `REFINERY`, or `RESERVE_SITE`. Coordinates are WGS84. Capacity, baseline supply, and baseline demand are complete metric envelopes when present.
- `TwinRoute` names canonical endpoints, commodity, capacity, transit time, distance, chokepoint dependencies, availability, evidence, and assumptions. Unknown endpoints and duplicate routes are rejected.
- `CrudeGrade` carries 12-20 catalogued grades with load-port IDs, enveloped API gravity and sulfur, sanctions-screening state, evidence, and assumptions.
- `RefineryCompatibility` stores the deterministic component scores, enveloped weighted score, classification, hard `allowed` result, explanation, and complete dependencies.
- `BaselineFlow` links supplier, grade, and route with `ktonne_per_day` volume and full provenance. The Phase 2 fixture conserves 250.0 ktonne/day of supply and demand with zero residual at the configured `1e-6 ktonne_per_day` tolerance.
- `TwinSnapshot` contains the complete ordered graph, catalogue, compatibility matrix, flows, evidence, assumptions, and mass-balance report. Its SHA-256 fingerprint and UUIDv5 snapshot ID are recalculated on validation. A changed input produces a new identity; mutation is rejected in storage.
