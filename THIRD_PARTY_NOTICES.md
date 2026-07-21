# Third-party notices

Sanjiv depends on open-source software distributed under its own licenses. The authoritative,
version-pinned inventories are `package-lock.json` and `uv.lock`; container bases are pinned in
`docker-compose.yml` and `infra/Dockerfile.*`. Preserve upstream copyright and license notices when
redistributing source, binaries or container images.

The release license scan explicitly reviewed packages reported under LGPL-3.0-or-later and
MPL-2.0, including compound SPDX expressions. These are compliance obligations, not security
vulnerabilities. LGPL libraries are dynamically used through the Python/runtime environment and
are not copied into Sanjiv source; MPL-covered files remain governed by MPL terms. The complete
machine-readable scan is `reports/security/trivy-licenses.json`.

Key upstream projects include Next.js/React, FastAPI/Starlette/Pydantic, PostgreSQL/PostGIS/
TimescaleDB, Redis, MinIO, NetworkX, Pyomo, HiGHS, Playwright, Alembic and OpenTelemetry-compatible
standards. Source/data attribution is separately maintained in `docs/SOURCE_REGISTRY.md` and every
replay manifest. OpenStreetMap attribution remains visible on the map.

This notice does not replace the license texts shipped by upstream packages or images. Before any
external binary/image distribution, export the locked dependency inventory, retain upstream
licenses, and have the distributor confirm its obligations for the chosen distribution form.
