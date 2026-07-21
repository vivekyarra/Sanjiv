# Production monitoring and alert thresholds

Sanjiv emits structured request logs, stable correlation/causation IDs, W3C-compatible trace
headers, readiness, source/worker component health, failure counts and min/median/p95/max request
runtimes. The deployment owns log/trace export and paging integration.

| Signal | Warning | Critical / action |
|---|---|---|
| API readiness | one 503 | 3 consecutive 503s or 60 seconds; page platform operator |
| PostgreSQL/Redis/MinIO | one `UNAVAILABLE` sample | 60 seconds unavailable; stop approval/export traffic and recover dependency |
| Worker heartbeat | older than 20 seconds | older than 30 seconds (`DEGRADED`); restart role and inspect last correlation ID |
| Source freshness | enters `STALE` or `DEGRADED` | source unavailable beyond its registered threshold; expose replay/degraded state |
| Request failures | >1% over 5 minutes | >5% over 5 minutes; inspect canonical error codes and dependency state |
| API p95 | >2x stored local baseline for 10 minutes | >4x baseline or timeout growth; reduce concurrency and profile bottleneck |
| Solver timeout/error | any | 3 in 15 minutes; block affected plan and inspect bounded model inputs |
| Audit/checker failure | any | immediate product alert; approval/export must remain blocked |
| WebSocket resync | >1 per client/hour | repeated overflow; inspect subscriber load and retain snapshot fallback |
| Backup | no successful daily run | two missed runs or restore verification failure; page data owner |

Stored Phase 9 benchmark values are release evidence, not production SLAs. Tune thresholds only
with representative deployment traffic and retain the changed policy version.
