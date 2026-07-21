# Sanjiv Source Registry

No adapter may use an endpoint until it is verified against current official documentation. Credentials remain optional capabilities: startup reports `READY`, `DEGRADED`, `UNAVAILABLE`, `RATE_LIMITED`, or `DISABLED` without exposing values.

## Adapter contract

```text
SourceAdapter[TSource, TNormalized]
  descriptor() -> SourceDescriptor
  health(now) -> SourceHealthRecord
  fetch(cursor, window) -> ObservationBatch[TNormalized]
  decode(raw) -> TSource
  normalize(source_record) -> TNormalized
  evidence(source_record, normalized) -> EvidenceRecord
```

`ObservationBatch` carries source ID, mode, records, cursor, effective/fetch interval, license metadata, raw-object checksum, and warnings. Adapters implement timeouts, bounded exponential backoff with jitter, rate-limit handling, a circuit breaker, schema validation, raw capture, and deterministic normalization. Fixture and replay readers implement the same output contract but distinct modes.

Phase 1 streaming AIS uses the narrower asynchronous interface `source_id`, `mode`, `health() -> AdapterHealth`, and `stream() -> AsyncIterator[RawAISMessage]`. Both AISStream and replay implement it; normalization, evidence creation, persistence, and transport do not import provider-specific payload types.

## Integrations

| Source | Primary class | Use | Credential placeholder | Setup and truth treatment |
|---|---|---|---|---|
| AISStream | live | AIS positions/messages | `AISSTREAM_API_KEY` | Implemented behind `SANJIV_AIS_ENABLED`. Backend WebSocket only at the documented `/v0/stream` endpoint; key is sent in the initial subscription and never logged. Raw validated live position is `OBSERVED`; reported destination remains observed text, while India-bound conclusions are `INFERRED`. Provider is beta/no-SLA, so bounded retry falls back visibly to replay. |
| IMF PortWatch | periodic | Daily/historical port and passage baselines | none | Phase 6 records the official [API definitions](https://portwatch.imf.org/api/search/definition/), [methodology](https://portwatch.imf.org/pages/data-and-methodology/), and [IMF reuse terms](https://www.imf.org/en/about/copyright-and-terms). Published estimates are source observations, not live AIS; attribution, integrity, and third-party-rights checks apply. |
| GDELT | near-real-time | News/event signals | none | Phase 6 records the official [DOC API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) and [GDELT terms](https://www.gdeltproject.org/about.html). Citation is required. A record is a media signal, not proof that a physical disruption occurred. |
| OFAC | periodic | Sanctions lists | none | Consume the official Sanctions List Service files with publication metadata. Source entry is observed; exact match is derived; fuzzy match is inferred and reviewable. |
| PPAC | periodic | Indian imports, demand, refinery capacity/throughput | none documented in repo | Phase 2 implements the typed import boundary using a CC0 PPAC-shaped offline fixture. Its operating values are `ASSUMPTION`; no PPAC payload is bundled. A future source batch must verify the official endpoint/terms before it can be `OBSERVED`. Do not infer private inventories. |
| ISPRL | static reference | Public reserve-site capacity and connectivity statements | none | Phase 2 imports cited public site-capacity factual metadata without bundling source publication content. Capacity is observed; current fill is absent/unknown unless a verified user value or explicit assumption is supplied. |
| EIA | periodic | Energy prices, supply, inventory series | `EIA_API_KEY` | Use the official [API v2 documentation](https://www.eia.gov/opendata/documentation.php) under [EIA reuse guidance](https://www.eia.gov/about/copyrights_reuse.php). Cadence, units, and attribution are series-specific. |
| FRED | periodic | Exchange-rate and macroeconomic series | `FRED_API_KEY` | Use the official [FRED API](https://fred.stlouisfed.org/docs/api/fred/overview.html) and [terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html); series-specific third-party rights still apply. Macro signals are not forecasts. |
| UN Comtrade | periodic | Historical supplier trade flows | `UN_COMTRADE_API_KEY` | Phase 2 implements the typed import boundary with a CC0 Comtrade-shaped supplier fixture. It is `ASSUMPTION`, not an observed trade record. Live/API use must verify current official terms and quota; historical trade is never live cargo tracking. |
| NASA FIRMS | near-real-time | Thermal anomalies near infrastructure | `FIRMS_MAP_KEY` | Use the official [Area API](https://firms.modaps.eosdis.nasa.gov/api/area/) and [NASA Earthdata use/citation policy](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy). MAP_KEY and transaction bounds apply. A hotspot is a signal, not proof of cause or damage. |
| Operator upload | user-supplied | Inventory, contracts, quotes, verified private values | none | Validate schema, record uploader and timestamp, encrypt private objects, classify direct values as observed user-supplied or explicit assumptions. |
| Replay dataset | replay | Resilient demo and historical validation | none | Manifest declares recorded-real or synthetic-fixture classification, source/generator, interval, checksum, license, redistribution, and transformation. Never label live. |
| OpenAI Responses API | optional interpretation | Schema-constrained natural-language scenario candidate only | `OPENAI_API_KEY` | Phase 3 reference adapter is enabled only by `SANJIV_LLM_PROVIDER=openai`; provider/model/timeout are recorded. Output is untrusted, cannot confirm/run/simulate/optimise, and must pass snapshot resolution and deterministic validation. No credential is required for install, CI, replay, structured entry, deterministic parsing, or the primary demo. Live credential operation was not exercised by the repository gate. |
| Phase 4 commercial demo | fixture | Supplier/grade availability, costs, delivery and concentration/budget policy | none | `data/fixtures/procurement/commercial-inputs-v1.json` is `SYNTHETIC_FIXTURE` with repository redistribution rights. Every bundle/policy is an approved, expiring `ASSUMPTION` with stable ID, owner, rationale, unit, effective time, and expiry. It is never live, quoted, observed, commercially confirmed, secured, or charterable. |
| Phase 5 reserve demo | fixture | Opening fill, policy floor/draw rate and logistics cost for three reserve sites | none | `data/fixtures/reserve/reserve-inputs-v1.json` is a CC0 `SYNTHETIC_FIXTURE`. Values are approved, expiring `ASSUMPTION` bundles and are not confidential inventory, release authority, scheduled movement, or a claim about current government stock. ISPRL capacity remains separately sourced `OBSERVED` metadata. |
| Phase 6 risk replay | replay | Six structural risk features and ten backtest cases | none | `data/replay/risk-intelligence-v1` is a checksummed CC0 `SYNTHETIC_FIXTURE`, not recorded history. It covers escalation, chokepoint anomaly, media spike, false news, thermal ambiguity, outage, staleness, disagreement, sanctions change, and uncorroborated AIS. Measurements are fixture evidence only. |

## Freshness policy

Each dataset defines its expected update interval and stale-after threshold in configuration rather than a universal cadence. Presentation states are `LIVE`, `RECENT`, `CURRENT`, `STALE`, `REPLAY`, and `UNAVAILABLE`; adapter health and data freshness remain separate. Cached data retains its original effective and fetch times.

## Environment placeholders

The authoritative non-secret list is `.env.example`. Phase 1 uses `AISSTREAM_API_KEY`, `SANJIV_AIS_ENABLED`, `SANJIV_AISSTREAM_URL`, `SANJIV_AIS_BOUNDING_BOXES`, bounded timeout/retry/backoff/queue settings, `SANJIV_REPLAY_DATASET`, `SANJIV_REPLAY_SPEED`, `SANJIV_REPLAY_LOOP`, and storage/geofence/freshness/heartbeat settings. Absence of a credential disables only that adapter and activates visibly labeled replay. Phase 3 uses `SANJIV_SCENARIO_STORAGE`, `SANJIV_SCENARIO_OPERATOR_IDENTITY`, optional production-only `SANJIV_SCENARIO_API_KEY`, `SANJIV_LLM_PROVIDER`, `SANJIV_LLM_MODEL`, `SANJIV_LLM_TIMEOUT_SECONDS`, and optional `OPENAI_API_KEY`. Phase 6 adds `SANJIV_RISK_STORAGE` and `SANJIV_RISK_REPLAY_MANIFEST`; optional EIA, FRED, and FIRMS credentials remain server-side. CI and the primary demo use only the checksum-verified replay.
