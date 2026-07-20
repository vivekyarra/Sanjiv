# Sanjiv

**India’s Energy Resilience Command Center**<br>
*Keep India’s energy moving.*

Sanjiv is a decision-intelligence system for observing threats to India’s energy-supply corridors, compiling validated disruption scenarios, simulating no-action consequences, and producing deterministic, evidence-backed procurement and strategic-reserve response plans.

The repository includes the Phase 0 truth foundation, Phase 1 Live Maritime Watch, and the Phase 2 India energy-network digital twin. Both operational screens work without credentials: maritime replay is explicitly synthetic, and the energy twin is an assumption-driven, content-addressed reference snapshot with cited ISPRL public capacity metadata. Scenario execution, simulation, and optimisation remain gated behind later phases.

## Principles

- Observed, derived, inferred, modeled, and assumed information are never conflated.
- Decision metrics carry source, timestamps, freshness, confidence, evidence, transformation, and model version.
- Operational recommendations come from deterministic optimisation, not generated prose.
- Replay and fixtures are always visible; no source mode changes silently.
- A human must approve a response plan. Sanjiv does not place orders or release reserves.

## Stack

- Next.js, React, TypeScript, Tailwind CSS
- FastAPI, Pydantic, Python 3.11
- PostgreSQL with PostGIS and TimescaleDB, Redis, MinIO
- npm workspaces and uv

## Quick start

Prerequisites: Node 24+, npm 11+, Python 3.11+, uv, Docker, and Docker Compose.

```powershell
Copy-Item .env.example .env
npm install
uv sync --all-groups
docker compose up -d postgres redis minio
npm run db:upgrade
npm run dev:api
```

In a second terminal:

```powershell
npm run dev:web
```

The Live Maritime Watch runs at `http://localhost:3000`, the Digital Twin at `http://localhost:3000/digital-twin`, and API documentation at `http://localhost:8000/docs`. With no `AISSTREAM_API_KEY`, the service automatically records an audited transition to `REPLAY`, and the UI displays a persistent `REPLAY — NOT LIVE DATA` banner. The Digital Twin separately displays `ASSUMPTION-DRIVEN REFERENCE TWIN — NOT LIVE OPERATIONAL DATA` and exposes every source/assumption.

For optional live operation, create an AISStream account, set `AISSTREAM_API_KEY` only in `.env`, and leave `SANJIV_AIS_ENABLED=true`. Never place the key in browser variables or committed files. See [the Phase 1 operator guide](docs/PHASE_1_LIVE_MARITIME_WATCH.md) for replay controls, database validation, troubleshooting, and data-use limits.

## Verification

```powershell
npm run contracts:check
npm run lint
npm run typecheck
npm test
npm run build
```

See [the implementation plan](docs/IMPLEMENTATION_PLAN.md), [architecture](docs/ARCHITECTURE.md), and [engineering guide](AGENTS.md) before making changes. Never commit `.env` or credentials.
