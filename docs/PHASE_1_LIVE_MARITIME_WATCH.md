# Phase 1: Live Maritime Watch

## What is implemented

Phase 1 is a maritime-monitoring vertical slice: provider-neutral AIS ingestion, validation and quarantine, canonical evidence-linked positions, PostGIS/Timescale tracks, geofence entry/exit events, checksummed replay, automatic visible fallback, read-only REST/WebSocket delivery, and a MapLibre operational screen. It does not determine cargo ownership, charter availability, private contracts, or future routing.

## Local replay setup

No credential or internet AIS access is needed. The committed `maritime-watch-v1` dataset is a small CC0 **synthetic fixture**, not recorded AIS. Its MMSIs and vessel names are fictional. The geofence polygons are approximate development fixtures, classified `ASSUMPTION`, low confidence, and non-authoritative.

```powershell
Copy-Item .env.example .env
npm ci
uv sync --all-groups --locked
docker compose up -d postgres
npm run db:upgrade
npm run dev:api
```

In another terminal:

```powershell
npm run dev:web
```

Open `http://localhost:3000`. With `AISSTREAM_API_KEY` empty, the API transitions to replay automatically and the yellow `REPLAY — NOT LIVE DATA` banner must remain visible. `SANJIV_REPLAY_SPEED=20` means twenty times the original fixture interval; use `SANJIV_REPLAY_SPEED=1` for a visible 70-second walkthrough. Replay speed changes delivery timing, never the source timestamps. Loop mode is intended for adapter endurance checks: deterministic record IDs are correctly deduplicated after the first persisted pass, so it does not repeat the visual animation.

## Optional AISStream operation

1. Register with AISStream and review its current terms and beta-service limitations.
2. Put the key in local `.env` as `AISSTREAM_API_KEY=...`; never use a `NEXT_PUBLIC_` variable.
3. Keep `SANJIV_AIS_ENABLED=true` and bound `SANJIV_AIS_BOUNDING_BOXES` to the required coverage. AISStream corner pairs are `[latitude, longitude]`.
4. Restart the API and inspect `/api/v1/sources/health` before interpreting the map.

The adapter uses the provider-documented backend WebSocket, submits the subscription within three seconds, requests position-report message types, applies bounded retries/backoff, and does not log the key. Live messages are still quarantined if their identifiers, coordinates, shape, or timestamp ordering fail canonical validation. Live use was not exercised without a user-supplied credential and is never claimed by the committed fixture.

## Replay and recording format

`data/replay/<dataset>/manifest.json` contains classification, description, source, SHA-256 of the NDJSON file, original interval, count, license, redistribution rule, transformation, and adapter version. Each NDJSON row contains `source_record_id`, UTC `source_timestamp`, and `payload`; the replay adapter validates every row and refuses checksum, count, or ordering mismatches.

Validated live source batches spool as deterministic, secret-free NDJSON under `data/runtime/replay/`, which is gitignored. They are not redistributable replay datasets until an operator reviews license/redaction, creates a manifest, verifies chronological ordering/count, calculates the exact file checksum, and labels the classification truthfully.

## Operating-mode and WebSocket behavior

- Startup without a usable live adapter: `DEGRADED → REPLAY`, audited with reason `AISSTREAM_NOT_CONFIGURED`.
- Provider failure after bounded retries: `DEGRADED → REPLAY`, audited with reason `AUTOMATIC_REPLAY_FALLBACK`.
- Successful first validated live message: transition to `LIVE`.
- `/ws/v1/operations?after=<cursor>` replays retained events, emits heartbeats while idle, and sends `RESYNC_REQUIRED` when the cursor is outside retention or a subscriber queue overflows.
- The browser refetches `/api/v1/operations/snapshot` on updates or resynchronization and reconnects with backoff capped at 30 seconds.

## Database additions

Migration `20260720_0002` adds `vessels`, Timescale `vessel_positions`, PostGIS `vessel_track_segments`, `geofences`, `geofence_events`, `replay_recordings`, `operating_mode_transitions`, and `ais_quarantine`. Recent-vessel B-tree and spatial GiST indexes support the map and crossing queries. Evidence and audit foreign keys continue to use the canonical Phase 0 ledger.

The application uses SQLAlchemy's async `asyncpg` driver, including on Windows. Alembic converts the same configured URL to synchronous Psycopg for migrations.

Verify reversibility on the Compose database:

```powershell
uv run alembic upgrade head
uv run alembic downgrade 20260720_0001
uv run alembic upgrade head
uv run alembic current
```

## Verification

```powershell
npm ci
uv sync --all-groups --locked
npm run contracts:check
npm run lint
npm run typecheck
npm test
npm run build
```

CI uses mocked/local adapters, requires no key, and makes no external source request.

## Troubleshooting and limitations

- Persistent replay is correct when no key exists; confirm the banner and mode explanation rather than trying to relabel it.
- `NOT_SCREENED` means no sanctions dataset was loaded. It does not mean cleared. Exact identifiers are `DERIVED`; fuzzy names are `INFERRED` potential matches only.
- AIS destination is malformed or stale frequently. Sanjiv preserves the reported string but does not treat it as a confirmed voyage or cargo statement.
- AISStream is beta and public AIS coverage is incomplete. A missing vessel is not evidence that it is absent.
- OpenStreetMap raster tiles require network connectivity and attribution. Operational overlays remain visible on the base background if tiles fail; offline tile packaging is not included.
- The Phase 1 broker is in-process. Run one API replica; add Redis fan-out before horizontal API scaling.
- Do not commit captured AIS unless its license explicitly permits redistribution. Never commit `.env`, API keys, raw restricted captures, database volumes, build output, or runtime recordings.
