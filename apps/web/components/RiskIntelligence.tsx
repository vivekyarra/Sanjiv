"use client";

import type { components } from "@sanjiv/contracts";
import Link from "next/link";
import { useEffect, useState } from "react";

type Overview = components["schemas"]["RiskOverviewResponse"];
type Risk = components["schemas"]["CorridorRiskResult"];
type Alerts = components["schemas"]["RiskAlertResponse"];
type Backtests = components["schemas"]["RiskBacktestResponse"];

const API_URL = process.env.NEXT_PUBLIC_SANJIV_API_URL ?? "http://localhost:8000";

export function RiskIntelligence() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [alerts, setAlerts] = useState<Alerts | null>(null);
  const [backtests, setBacktests] = useState<Backtests | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      fetchJson<Overview>("/api/v1/risk/corridors"),
      fetchJson<Alerts>("/api/v1/risk/alerts"),
      fetchJson<Backtests>("/api/v1/risk/backtests"),
    ]).then(([nextOverview, nextAlerts, nextBacktests]) => {
      setOverview(nextOverview);
      setAlerts(nextAlerts);
      setBacktests(nextBacktests);
    }).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "Risk intelligence is unavailable");
    });
  }, []);

  return <main className="command-shell response-planner">
    <header className="command-header">
      <div><p className="eyebrow">India&apos;s Energy Resilience Command Center</p><h1>Risk Intelligence</h1><p>Evidence-backed structural corridor severity for analyst review.</p></div>
      <span className="mode-badge">{overview?.mode ?? "LOADING"} · SEVERITY IS NOT DISRUPTION PROBABILITY</span>
    </header>
    <nav className="product-nav" aria-label="Product modules">
      <Link href="/">Live Maritime Watch</Link><Link href="/digital-twin">Digital Twin</Link><Link href="/scenario-lab">Scenario Lab</Link><Link href="/response-planner">Response Planner</Link><Link href="/strategic-reserve">Strategic Reserve</Link><Link className="active" href="/risk-intelligence">Risk Intelligence</Link><Link href="/evidence-approval">Evidence &amp; Approval</Link>
    </nav>
    {error && <section className="scenario-card" role="alert"><h2>Unavailable</h2><p>{error}</p><p>Source and model failures remain explicit; missing features never silently become zero.</p></section>}
    {!overview && !error && <section className="scenario-card"><p>Loading ranked corridors, source freshness and replay evidence…</p></section>}
    <section className="profile-grid" aria-label="Ranked corridor risks">
      {overview?.risks.map((risk, rank) => <RiskCard key={risk.risk_id} risk={risk} rank={rank + 1} />)}
    </section>
    <section className="planner-two-column">
      <article className="scenario-card"><h2>Alert status</h2>{alerts?.alerts.map((alert) => <div key={alert.alert_id}><h3>{alert.severity_band} · {alert.status}</h3><p>{alert.explanation}</p><p><strong>Recommended analyst action:</strong> {alert.recommended_analyst_action}</p><p>Autonomous action: {alert.autonomous_action ? "enabled" : "disabled"}</p></div>)}</article>
      <article className="scenario-card"><h2>Historical and replay comparison</h2>{backtests?.results.map((result) => <div key={result.backtest_id}><p className="truth-note">{result.classification} · fixture/replay evidence only</p><p>{result.cases.length} checksummed cases · precision {fraction(result.precision)} · false positives {result.false_positives}</p><p>Detection lead time {result.detection_lead_time_hours.toFixed(1)} hour · completeness {fraction(result.mean_completeness)} · alert stability {fraction(result.alert_stability)}</p><p>Runtime {result.runtime_ms.toFixed(2)} ms · fingerprint {result.fingerprint}</p></div>)}</article>
    </section>
  </main>;
}

function RiskCard({ risk, rank }: { risk: Risk; rank: number }) {
  return <article className="scenario-card profile-card">
    <p className="eyebrow">Rank {rank} · {risk.lifecycle}</p><h2>{risk.corridor_name}</h2>
    <dl><Fact label="Severity" value={`${risk.severity.value.toFixed(1)} / 100`} /><Fact label="Evidence confidence" value={fraction(risk.confidence.value)} /><Fact label="Data completeness" value={fraction(risk.completeness.value)} /></dl>
    <p>{risk.explanation}</p>
    <h3>Map and effective timeline</h3><p>Corridor asset {risk.corridor_id.slice(0, 8)} · effective {formatIst(risk.effective_at)} · calculated {formatIst(risk.calculated_at)}</p>
    <h3>Feature contributions</h3>{risk.contributions.map((item) => <p key={item.feature_type}>{item.feature_type.replaceAll("_", " ")}: {item.present ? item.weighted_contribution.toFixed(2) : "MISSING"} · weight {item.weight.toFixed(2)}</p>)}
    <h3>Source freshness</h3>{risk.features.map((feature) => <p key={feature.feature_id}>{feature.source_id}: {feature.freshness} / {feature.source_state} · {feature.missing ? "UNAVAILABLE" : feature.truth_class}</p>)}
    <details><summary>Evidence drawer</summary><p>Corroboration {risk.corroboration.passed ? "passed" : "not passed"}; {risk.corroboration.independent_source_count} independent elevated sources.</p>{risk.features.map((feature) => <p key={`${feature.feature_id}-evidence`}>{feature.feature_type}: {feature.evidence_ids.length ? feature.evidence_ids.join(", ") : "No usable evidence"}</p>)}{risk.source_failures.map((failure) => <p key={`${failure.source_id}-${failure.code}`}>{failure.source_id}: {failure.code} · {failure.message}</p>)}<p>Model {risk.model_version} · baseline {risk.baseline_version} · fingerprint {risk.fingerprint}</p></details>
  </article>;
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Risk service request failed (${response.status})`);
  return await response.json() as T;
}

function Fact({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function fraction(value: number) { return `${(value * 100).toFixed(1)}%`; }
function formatIst(value: string) { return new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }); }
