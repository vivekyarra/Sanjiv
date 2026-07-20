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

## Integrations

| Source | Primary class | Use | Credential placeholder | Setup and truth treatment |
|---|---|---|---|---|
| AISStream | live | AIS positions/messages | `AISSTREAM_API_KEY` | Backend WebSocket only. Register with provider; verify current subscription schema. Raw message is observed; route/destination conclusions are inferred. |
| IMF PortWatch | periodic | Daily/historical port and passage baselines | none documented in repo | Verify official IMF download/API access and terms before adapter code. Treat published estimates as observed source estimates, not live AIS. |
| GDELT | near-real-time | News/event signals | none documented in repo | Use documented GDELT datasets only. An event record is an observed media signal, not proof that a physical disruption occurred. |
| OFAC | periodic | Sanctions lists | none | Consume the official Sanctions List Service files with publication metadata. Source entry is observed; exact match is derived; fuzzy match is inferred and reviewable. |
| PPAC | periodic | Indian imports, demand, refinery capacity/throughput | none documented in repo | Prefer official machine-readable publications; otherwise use a versioned, checksum-recorded import. Do not infer private inventories. |
| ISPRL | static reference | Public reserve-site capacity and connectivity statements | none | Store publication date and URL. Capacity is observed; current fill is user-supplied/assumption unless explicitly verified. |
| EIA | periodic | Energy prices, supply, inventory series | `EIA_API_KEY` | Register through official EIA Open Data setup. Cadence and units are series-specific. |
| FRED | periodic | Exchange-rate and macroeconomic series | `FRED_API_KEY` | Register through official FRED API setup. Macro outputs remain modeled sensitivities, not forecasts. |
| UN Comtrade | periodic | Historical supplier trade flows | `UN_COMTRADE_API_KEY` | Use current official API terms and quota. Historical trade is a baseline, not live cargo tracking. |
| NASA FIRMS | near-real-time | Thermal anomalies near infrastructure | `FIRMS_MAP_KEY` | Obtain a MAP_KEY through official FIRMS setup. A hotspot is a supporting observed signal, not proof of cause or damage. |
| Operator upload | user-supplied | Inventory, contracts, quotes, verified private values | none | Validate schema, record uploader and timestamp, encrypt private objects, classify direct values as observed user-supplied or explicit assumptions. |
| Recorded replay | replay | Resilient demo and historical validation | none | Manifest must include original source, capture window, checksum, license, redaction, and evidence IDs. Never label live. |

## Freshness policy

Each dataset defines its expected update interval and stale-after threshold in configuration rather than a universal cadence. Presentation states are `LIVE`, `RECENT`, `CURRENT`, `STALE`, `REPLAY`, and `UNAVAILABLE`; adapter health and data freshness remain separate. Cached data retains its original effective and fetch times.

## Environment placeholders

The authoritative non-secret list is `.env.example`. Absence of a credential disables only that adapter. `OPENAI_API_KEY` configures the optional first scenario-interpreter provider; no LLM credential is required for structured-form operation.
