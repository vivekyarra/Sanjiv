# Operations runbook

## Supported commands

Run from the repository root. On Windows use `npm run ...` or
`powershell -File scripts/sanjiv.ps1 <command>`; on macOS/Linux use
`./scripts/sanjiv.sh <command>`.

| Outcome | Command |
|---|---|
| Locked clean install | `npm run sanjiv -- install` |
| Infrastructure services | `npm run sanjiv -- services` |
| Upgrade to migration head | `npm run sanjiv -- migrate` |
| Seed deterministic demo fixtures | `npm run sanjiv -- seed` |
| Build/start API, web and three workers | `npm run sanjiv -- start` |
| Development web/API path | `npm run sanjiv -- dev` or the documented `dev:web` / `dev:api` commands |
| Focused repository verification | `npm run verify` |
| Complete Phase 9 gate | `npm run release:verify` |
| Primary credential-free demo | `npm run demo` |
| Existing-image offline demo | `npm run demo:offline` |
| Demo preflight | `npm run demo:preflight` |
| Stop without deleting volumes | `npm run sanjiv -- stop` |
| Destructive local cleanup | `npm run sanjiv -- cleanup` |

`cleanup` deletes only this Compose project's named local volumes. Back up any local development
data first. It is not a production command.

The default E2E gate is read-only with respect to committed evidence. Set
`SANJIV_UPDATE_EVIDENCE=1` only when intentionally regenerating reviewed screenshots and browser
benchmark evidence for a new release checkpoint.

## Health and observability

- Liveness: `GET http://localhost:8000/health/live`
- Readiness: `GET http://localhost:8000/health/ready`
- Component/worker/runtime status: `GET http://localhost:8000/api/v1/operations/status`
- Web: `http://localhost:3000`

Readiness is degraded when PostgreSQL, Redis, or MinIO is unreachable. Operations status exposes
the maritime source mode/freshness, all three worker heartbeats, dependencies, request runtime
aggregates, the environment and commit. Request logs are structured JSON and carry correlation,
causation and W3C-compatible trace identifiers. Never log API keys, authorization headers, private
payloads, or URLs containing secrets.

## Production boundary

Set `SANJIV_ENV=production`, configure allowed origins and server-side API-key-to-identity/role
maps, terminate TLS outside the app, isolate data stores on private networks, configure encrypted
backups, and connect the trace/log stream to the operator's collector. Production fails closed for
unconfigured API authentication and governance identities. Sanjiv has no order, charter, reserve
release, pipeline, refinery-control, or other operational execution adapter.
