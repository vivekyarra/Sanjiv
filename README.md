# Sanjiv

**India’s Energy Resilience Command Center**<br>
*Keep India’s energy moving.*

Sanjiv is a decision-intelligence system for observing threats to India’s energy-supply corridors, compiling validated disruption scenarios, simulating no-action consequences, and producing deterministic, evidence-backed procurement and strategic-reserve response plans.

The repository includes the Phase 0 truth foundation, Phase 1 Live Maritime Watch, the Phase 2 India energy-network digital twin, Phase 3 Scenario Lab, the Phase 4 Response Planner, and the Phase 5 Strategic Reserve planner. All operational screens work without credentials. Phase 5 coordinates four checked reserve-policy results with one exact immutable Phase 4 plan while keeping public site capacity separate from assumption-backed opening fill.

## Phase 4 Response Planner

Open `http://localhost:3000/response-planner` and supply a completed scenario-run UUID. Sanjiv sequentially generates `LOWEST_COST`, `BALANCED`, and `HIGHEST_RESILIENCE` plans with identical hard constraints, persists exact-fingerprint results, and exposes solver/checker state, allocations, shortage, costs, objective contributions, constraints, rejected options, provenance, and fingerprints. The commercial fixture is `SYNTHETIC_FIXTURE`; it is not a quote or confirmation, and the UI has no purchasing, tanker-booking, approval, or reserve-release action.

## Phase 5 Strategic Reserve

Open `http://localhost:3000/strategic-reserve` and supply a completed scenario-run UUID plus one checked Phase 4 plan UUID. Sanjiv generates `CONSERVATIVE`, `BALANCED`, `AGGRESSIVE_CONTINUITY`, and `NO_RESERVE_USE` guidance, checks site stock conservation, floors, draw/route/receipt capacities, transit, procurement coordination, shortage, objectives, and fingerprints, and persists immutable exact-fingerprint results. Opening fill remains an expiring `ASSUMPTION`; public capacity does not imply fill. Sanjiv recommends and does not release reserves.

## Phase 3 Scenario Lab

Open `http://localhost:3000/scenario-lab`. The always-available structured form and bounded deterministic parser support Hormuz closure/capacity reduction, maritime-route capacity reduction, supplier availability reduction, port disruption, refinery throughput disruption, delayed starts, and supported compound effects. A server-side confirmation freezes the scenario and snapshot fingerprints before a run can start. Results show baseline versus no-action flow, refinery throughput, shortfall, deterministic sensitivity bounds, runtime, evidence, and assumption provenance. Inventory remains `UNKNOWN` unless an explicit, unexpired starting-inventory assumption is supplied.

Natural-language LLM interpretation is optional. Set `SANJIV_LLM_PROVIDER=openai` and `OPENAI_API_KEY` to enable the reference adapter. If it is absent, unavailable, invalid, or times out, compilation returns a typed provider state and the structured/deterministic paths continue normally. Provider output is untrusted, schema constrained, deterministically validated, and never confirms or executes a scenario.

## Principles

- Observed, derived, inferred, modeled, and assumed information are never conflated.
- Decision metrics carry source, timestamps, freshness, confidence, evidence, transformation, and model version.
- Operational recommendations come from deterministic optimisation, not generated prose.
- Replay and fixtures are always visible; no source mode changes silently.
- A human must approve a response plan. Sanjiv does not place orders or release reserves.

## Stack

- Next.js, React, TypeScript, Tailwind CSS
- FastAPI, Pydantic, Pyomo, HiGHS, Python 3.11
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

The Scenario Lab is available at `http://localhost:3000/scenario-lab`.

The Live Maritime Watch runs at `http://localhost:3000`, the Digital Twin at `http://localhost:3000/digital-twin`, and API documentation at `http://localhost:8000/docs`. With no `AISSTREAM_API_KEY`, the service automatically records an audited transition to `REPLAY`, and the UI displays a persistent `REPLAY — NOT LIVE DATA` banner. The Digital Twin separately displays `ASSUMPTION-DRIVEN REFERENCE TWIN — NOT LIVE OPERATIONAL DATA` and exposes every source/assumption.

For optional live operation, create an AISStream account, set `AISSTREAM_API_KEY` only in `.env`, and leave `SANJIV_AIS_ENABLED=true`. Never place the key in browser variables or committed files. See [the Phase 1 operator guide](docs/PHASE_1_LIVE_MARITIME_WATCH.md) for replay controls, database validation, troubleshooting, and data-use limits.

## Verification

```powershell
npm ci
uv sync --all-groups --locked
docker compose config
docker compose up -d postgres redis minio
npm run db:upgrade
uv run ruff check .
uv run mypy services/api
uv run pytest
npm run contracts:check
npm run lint
npm run typecheck
npm test
npm run build
git diff --check
```

See [the implementation plan](docs/IMPLEMENTATION_PLAN.md), [architecture](docs/ARCHITECTURE.md), and [engineering guide](AGENTS.md) before making changes. Never commit `.env` or credentials.
