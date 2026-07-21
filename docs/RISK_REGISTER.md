# Sanjiv Risk Register

| Risk | Likelihood | Impact | Mitigation and trigger | Contingency | Owner |
|---|---|---|---|---|---|
| API outage | High | High | Per-source timeout, health state, circuit breaker; trigger on consecutive failures | Explicit cached/replay mode or unavailable state | Data lead |
| Rate limit | High | Medium | Cadence budgets, conditional requests, backoff; trigger on 429/quota signal | Serve marked cache and delay refresh | Data lead |
| Missing credentials | High | High | Startup capability report and optional adapters | Fixture/replay only with visible mode; disable source | Platform lead |
| AIS coverage gaps | High | High | Coverage/staleness indicators and gap metrics | Preserve last observation; never interpolate as observed | Maritime lead |
| Stale data | High | High | Source-specific expected cadence and freshness computation | Block or downgrade dependent decision metrics | Evidence lead |
| Malformed AIS destination | High | Medium | Preserve raw text, normalized candidate, confidence contributions | Mark unknown; do not assert destination/cargo | Maritime lead |
| Reserve opening fill unavailable or stale | Critical | High | Separate capacity from fill; require verified input or expiring assumption; fingerprint every value | Block the site and show UNKNOWN/expired state; never infer fill from capacity | Reserve modelling lead |
| Procurement/reserve shared-capacity drift | High | Medium | Bind exact checked Phase 4 plan and independently reconstruct shared receipt limits | Reject fingerprint mismatch and produce no usable reserve plan | Optimisation lead |
| Solver infeasibility | Medium | High | Pre-solve validation and named slack diagnostics | Return infeasibility report and safe manual review | Modelling lead |
| Solver timeout | Medium | High | Time limits, warm starts, model-size budgets | Reuse only exact-fingerprint result; otherwise no plan | Modelling lead |
| Procurement model or checker drift | Medium | Critical | Shared immutable inputs but independent arithmetic/constraint reconstruction, fingerprint checks, deterministic golden cases | Block the plan and return typed checker failure | Modelling lead |
| Synthetic commercial assumption mistaken for availability | High | Critical | Expiry, owner/rationale, visible `ASSUMPTION` and `SYNTHETIC_FIXTURE` labels, no execution controls or confirmation wording | Exclude missing/expired inputs and require verified operator data | Evidence lead |
| LLM parsing failure | Medium | Medium | Strict schema, bounded repair, deterministic validation | Editable structured scenario form | Platform lead |
| Prompt injection or provider self-approval | Medium | High | Defensive system boundary, constrained schema, injection refusal, deterministic validation, server confirmation | Discard provider output and use structured form | Security lead |
| Local demo mutation exposure | Medium | High | Credential-free only in development/test; production mutations fail closed without configured operator API key and server-owned identity | Place behind authenticated operator gateway before multi-user deployment | Security lead |
| Scenario job lost on API restart | Medium | Medium | Persist every lifecycle/result/progress transition and support exact-fingerprint reuse | Retrieve terminal result or start a newly audited run | Platform lead |
| In-process simulation saturation | Low at fixture scale | Medium | Bounded horizons/effects and measured runtime; persisted worker-ready job contract | Move execution to the existing worker boundary after measured need | Modelling lead |
| Map performance | Medium | Medium | Bounded MapLibre sources, recent tracks, browser profiling | Add viewport queries/aggregation or deck.gl only at measured threshold | Frontend lead |
| Unsupported assumptions | High | High | Assumption registry, expiry, owner, approval, claim blocker | Block dependent metric or require operator input | Evidence lead |
| Data licensing | Medium | High | Record terms, redistribution, retention, attribution | Disable redistribution and use licensed fixtures | Product lead |
| Demo connectivity | High | High | Preflight and checksummed synthetic replay package | Automatic audited replay with persistent non-live banner | Demo lead |
| Basemap tile outage | Medium | Medium | OSM attribution and overlay-first map styling | Vessel/geofence overlays remain usable on dark background; bundle licensed tiles later | Frontend lead |
| In-process WebSocket scope | Medium | Medium | Cursor/resync contract and bounded queues | Add Redis fan-out before running multiple API replicas | Platform lead |
| Secret exposure | Medium | Critical | Server-side keys, `.env` ignore, redaction tests, secret scanning | Revoke/rotate, purge artifact, incident review | Security lead |
| Supply-chain dependency compromise | Low | High | Locks, audit, minimal dependencies, image scanning | Pin/replace package and rebuild artifacts | Platform lead |
| Unauthorized approval | Low | Critical | Server-enforced roles and immutable audit record | Revoke approval and supersede plan | Security lead |

Risks are reviewed at each phase gate. A demo may proceed with degraded sources only when the mode, timestamp, and consequences are visible to the operator and audience.
