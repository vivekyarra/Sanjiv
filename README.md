# Sanjiv

**India’s Energy Resilience Command Center**<br>
*Keep India’s energy moving.*

Sanjiv is a decision-intelligence system for observing threats to India’s energy-supply corridors, compiling validated disruption scenarios, simulating no-action consequences, and producing deterministic, evidence-backed procurement and strategic-reserve response plans.

The repository is currently at **Phase 0**: repository foundation and canonical truth/data contracts. Maritime ingestion, maps, simulation, and optimisation are intentionally not implemented yet.

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

The web shell runs at `http://localhost:3000`; API documentation is at `http://localhost:8000/docs`.

## Verification

```powershell
npm run contracts:check
npm run lint
npm run typecheck
npm test
npm run build
```

See [the implementation plan](docs/IMPLEMENTATION_PLAN.md), [architecture](docs/ARCHITECTURE.md), and [engineering guide](AGENTS.md) before making changes. Never commit `.env` or credentials.
