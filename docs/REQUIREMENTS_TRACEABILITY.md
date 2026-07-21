# Requirements-to-code and test matrix

This matrix audits the committed Phase 0-8 product plus the Phase 9 release candidate against the
repository specifications. `Implemented; final gate pending` means the behavior and direct tests
exist, but Phase 9 is not declared complete until the complete release gate succeeds.

| Requirement source | Requirement | Implementation evidence | Verification evidence | Status / limitation |
|---|---|---|---|---|
| `PRODUCT_SPEC.md` | Observe maritime movements with honest truth and freshness | `sanjiv/maritime`, `MaritimeWatch.tsx` | `test_maritime_*`, Playwright decision flow | Implemented; fixture/replay is not live data. |
| `PRODUCT_SPEC.md` | Immutable energy digital twin and provenance | `sanjiv/twin`, migration `20260721_0002` | `test_twin*`, Phase 2 migration cycle | Implemented; commercial inputs remain assumptions. |
| `PRODUCT_SPEC.md` | Deterministic scenario compilation and confirmation | `sanjiv/scenarios`, `ScenarioLab.tsx` | `test_scenario_*`, Playwright decision flow | Implemented; bounded parser, not open-ended geopolitical prediction. |
| `MODEL_SPECIFICATION.md` | No-action simulation and physical invariants | `sanjiv/simulation` | `test_simulation.py` | Implemented; sensitivity samples are not probability. |
| `MODEL_SPECIFICATION.md` | Three procurement profiles with independent checker | `sanjiv/procurement` | `test_procurement_*`, benchmark report | Implemented; modeled candidates do not place orders or confirm availability. |
| `MODEL_SPECIFICATION.md` | Reserve policy, capacity/fill separation, checker | `sanjiv/reserve` | `test_reserve_*` | Implemented; opening fill is an expiring assumption, never inferred from capacity. |
| `PRODUCT_SPEC.md` | Risk severity, confidence, completeness and corroboration remain separate | `sanjiv/risk`, `RiskIntelligence.tsx` | `test_risk_*` | Implemented; severity is never calibrated probability. |
| `DATA_CONTRACTS.md` | Metric envelopes and complete provenance | `contracts/truth.py`, generated OpenAPI/TypeScript | contract drift gate; phase domain suites | Implemented; missing mandatory provenance blocks decision use. |
| `API_SPECIFICATION.md` | Canonical errors, idempotency and restart-readable state | thin domain routers plus PostgreSQL repositories | API, idempotency and PostgreSQL readback tests | Implemented for documented APIs. |
| Phase 7 | Evidence/assumption audit, recomputation, claim blocking | `sanjiv/audit` | `test_phase7_audit.py`, `test_phase7_postgres.py` | Implemented; deterministic explanation is the default. |
| Phase 7 | Server-owned review/approve/reject/supersede | audit service/repository and `GovernancePanel.tsx` | Phase 7 auth/concurrency/immutability tests; Playwright | Implemented; production needs configured server-side identity mapping. |
| Phase 8 | At least 20 licensed, checksummed replays | `data/replay/validation-v1`, `sanjiv/phase8` | `test_phase8.py` | 21 CC0 synthetic cases; none is represented as recorded history. |
| Phase 8 | Typed LPG path and commodity invariants | `data/fixtures/lpg`, Phase 8 service/contracts | Phase 8 LPG tests; Playwright | Implemented; strategic reserve is explicitly not applicable to LPG. |
| Phase 8 | Reproducible sensitivity and plan stability | Phase 8 service/contracts | Phase 8 reproducibility tests | Implemented; deterministic sensitivity is not probability. |
| Phase 8 | Audited JSON/PDF packages and monitoring | Phase 8 export/monitoring repository and UI | Phase 8 export blocking/readback tests; Playwright | Implemented; no operational execution integration. |
| `ARCHITECTURE.md` | Modular monolith, thin HTTP, isolated workers | domain services, `workers/runner.py`, Compose profiles | strict mypy, worker health tests, recovery drill | Implemented; API WebSocket fan-out is single-instance. |
| Phase 9 | One-command install/start/verify/demo/offline/cleanup | `scripts/sanjiv.mjs`, `.ps1`, `.sh`, npm scripts | command execution in final gate | Implemented; final gate pending. |
| Phase 9 | Real browser journey and screenshots | `e2e/decision-flow.spec.ts`, `e2e/performance.spec.ts` | Playwright at 1920x1080 | Implemented; final clean rerun pending. |
| Phase 9 | Stored measured performance | `scripts/benchmark_phase9.py`, `reports/performance` | benchmark and browser reports | Implemented; local fixture measurements are not SLAs. |
| Phase 9 | Authentication, origin, size/type, rate, SSRF, redaction and resource limits | `operations/security.py`, settings, bounded adapters/solvers | Phase 9 security tests; security scan report | Implemented; final scanner rerun pending. No upload endpoint exists. |
| Phase 9 | Structured logs, tracing-compatible IDs, readiness and worker/source health | `operations/telemetry.py`, `operations/routes.py` | Phase 9 observability tests | Implemented; exporter/collector is deployment configuration. |
| Phase 9 | Backup, restore and dependency/worker/API recovery | backup and reliability scripts | `reports/recovery` | Implemented; local single-host drill, not multi-region failover. |
| `SOURCE_REGISTRY.md` | Credential isolation, licensing and visible live/replay transitions | typed adapters, settings, manifests | adapter/redaction/replay tests | Implemented for registered sources; live enablement requires credentials and terms review. |
| `DEMO_RUNBOOK.md` | Credential-free repeatable primary demo | seed/preflight scripts and offline Compose profile | preflight, Playwright and offline gate | Implemented; never claim fixture data is live. |
| `RISK_REGISTER.md` | Residual risks remain explicit | risk register and limitations in reports | documentation review | Implemented; production IdP, licensed history and multi-replica fan-out remain deployment work. |

No Phase 10 behavior, operational control integration, order placement, chartering, or reserve
release is included or claimed.
