# Sanjiv Risk Register

| Risk | Likelihood | Impact | Mitigation and trigger | Contingency | Owner |
|---|---|---|---|---|---|
| API outage | High | High | Per-source timeout, health state, circuit breaker; trigger on consecutive failures | Explicit cached/replay mode or unavailable state | Data lead |
| Rate limit | High | Medium | Cadence budgets, conditional requests, backoff; trigger on 429/quota signal | Serve marked cache and delay refresh | Data lead |
| Missing credentials | High | High | Startup capability report and optional adapters | Fixture/replay only with visible mode; disable source | Platform lead |
| AIS coverage gaps | High | High | Coverage/staleness indicators and gap metrics | Preserve last observation; never interpolate as observed | Maritime lead |
| Stale data | High | High | Source-specific expected cadence and freshness computation | Block or downgrade dependent decision metrics | Evidence lead |
| Malformed AIS destination | High | Medium | Preserve raw text, normalized candidate, confidence contributions | Mark unknown; do not assert destination/cargo | Maritime lead |
| Solver infeasibility | Medium | High | Pre-solve validation and named slack diagnostics | Return infeasibility report and safe manual review | Modelling lead |
| Solver timeout | Medium | High | Time limits, warm starts, model-size budgets | Reuse only exact-fingerprint result; otherwise no plan | Modelling lead |
| LLM parsing failure | Medium | Medium | Strict schema, bounded repair, deterministic validation | Editable structured scenario form | Platform lead |
| Map performance | Medium | Medium | deck.gl aggregation, viewport queries, load tests | Reduce track history/detail with visible indication | Frontend lead |
| Unsupported assumptions | High | High | Assumption registry, expiry, owner, approval, claim blocker | Block dependent metric or require operator input | Evidence lead |
| Data licensing | Medium | High | Record terms, redistribution, retention, attribution | Disable redistribution and use licensed fixtures | Product lead |
| Demo connectivity | High | High | Preflight and recorded-real replay package | Operator-confirmed replay with persistent banner | Demo lead |
| Secret exposure | Medium | Critical | Server-side keys, `.env` ignore, redaction tests, secret scanning | Revoke/rotate, purge artifact, incident review | Security lead |
| Supply-chain dependency compromise | Low | High | Locks, audit, minimal dependencies, image scanning | Pin/replace package and rebuild artifacts | Platform lead |
| Unauthorized approval | Low | Critical | Server-enforced roles and immutable audit record | Revoke approval and supersede plan | Security lead |

Risks are reviewed at each phase gate. A demo may proceed with degraded sources only when the mode, timestamp, and consequences are visible to the operator and audience.
