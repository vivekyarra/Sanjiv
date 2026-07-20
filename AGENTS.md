# Sanjiv Engineering Guide

Sanjiv is India’s Energy Resilience Command Center. Its tagline is “Keep India’s energy moving.” Do not use legacy names, append “AI” or “GPT” to the name, or invent an acronym.

## Repository structure

- `apps/web`: Next.js command-center UI.
- `services/api`: FastAPI modular monolith. Domain modules live under `sanjiv/`; HTTP routing stays thin.
- `workers`: only ingestion, scheduled refresh, and simulation/optimisation workers.
- `packages/contracts`: generated TypeScript contracts. Do not hand-edit generated files.
- `infra`: deployment and service configuration.
- `data/fixtures`: explicitly synthetic test/demo fixtures.
- `data/replay`: recorded-real-data replay manifests and immutable payloads.
- `tests`: cross-module and contract tests.
- `docs`: architecture, model, API, source, test, risk, and demo decisions.

Inspect existing code, tests, contracts, migrations, and nearby documentation before changing anything. Keep changes limited to the requested behavior and preserve unrelated user work.

## Commands

```powershell
npm install
uv sync --all-groups
docker compose up -d postgres redis minio
npm run dev
npm run dev:web
npm run dev:api
npm run lint
npm run typecheck
npm test
npm run contracts:check
npm run db:upgrade
npm run db:downgrade
npm run build
docker compose down
```

Python-only checks are `uv run ruff check .`, `uv run mypy services/api`, and `uv run pytest`. Run the relevant tests after every implementation task. Run the full verification set before handoff when shared contracts, migrations, build configuration, or cross-domain behavior changes.

## Coding and contract standards

- Python 3.11+, fully typed public functions, Pydantic v2 at system boundaries, Ruff formatting/linting, mypy strictness for production modules, and async I/O for network/database work.
- TypeScript strict mode, React server components by default, client components only where interaction requires them, and no untyped API payloads.
- UTC RFC 3339 timestamps on the wire; convert to IST only for display. Use explicit units and stable UUID identifiers.
- Pydantic/OpenAPI is the canonical API schema. Regenerate TypeScript contracts and fail checks on drift.
- Domain logic must not depend on FastAPI route objects, React components, or source-specific payload shapes.

## Truth and evidence rules

Every quantitative decision metric uses the canonical metric envelope and one of: `OBSERVED`, `DERIVED`, `INFERRED`, `MODELED`, or `ASSUMPTION`. It must carry source references, effective/fetch/compute timestamps, freshness, confidence, evidence IDs, transformation, and model version. A missing mandatory evidence field blocks the metric from decision UI and briefing output.

- `OBSERVED`: directly retrieved or explicitly supplied; no interpretation beyond normalization.
- `DERIVED`: deterministic calculation from identified inputs.
- `INFERRED`: heuristic or probabilistic classification.
- `MODELED`: simulator or optimiser output.
- `ASSUMPTION`: visible, editable input used because verified data is unavailable.

Never claim exact cargo ownership, confirmed charter availability, private refinery inventory, private procurement contracts, confidential reserve fill, confirmed crude grade, or exact consumer-price effects unless the user supplied verified data. Fuzzy sanctions matches are `INFERRED`; exact identifier match results are `DERIVED`, while the source list entry is `OBSERVED`.

## Source adapter conventions

- Adapters implement the typed source interface and return normalized observations plus immutable evidence records and source health.
- Keep credentials server-side. Never log secrets, URLs containing keys, authorization headers, or raw private uploads.
- Every adapter defines timeout, bounded retry/backoff, rate-limit handling, cadence, staleness threshold, circuit state, and fixture/replay contract.
- Cache, replay, fixture, and live states are distinct. Never silently change mode. Every transition is visible and audited.
- Do not add undocumented endpoints. Record the official documentation and licensing/usage restrictions in `docs/SOURCE_REGISTRY.md`.

## Tests and definition of done

New logic requires success, boundary, invalid-input, and dependency-failure tests. Models also require invariants and deterministic golden cases. Adapters require recorded payload contract tests and secret-redaction checks. UI changes require accessibility and mode/truth-label assertions.

Work is done only when relevant lint, type checks, tests, migrations, contract-drift checks, and production builds pass; failures and degraded states are explicit; every decision metric has valid provenance; unsupported claims are blocked; no credential or private payload is committed; documentation and acceptance criteria are current; and no unrelated behavior changed.
