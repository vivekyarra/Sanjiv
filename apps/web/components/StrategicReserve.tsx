"use client";

import type { components } from "@sanjiv/contracts";
import Link from "next/link";
import { FormEvent, useState } from "react";

type Response = components["schemas"]["ReservePlanResponse"];
type Result = components["schemas"]["ReserveSolverResult"];

const API_URL = process.env.NEXT_PUBLIC_SANJIV_API_URL ?? "http://localhost:8000";
const profiles = ["CONSERVATIVE", "BALANCED", "AGGRESSIVE_CONTINUITY", "NO_RESERVE_USE"] as const;

export function StrategicReserve() {
  const [runId, setRunId] = useState("");
  const [procurementPlanId, setProcurementPlanId] = useState("");
  const [response, setResponse] = useState<Response | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function generate(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const request = await fetch(`${API_URL}/api/v1/scenario-runs/${runId}/reserve-plans`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ procurement_plan_id: procurementPlanId, profiles, time_limit_seconds: 10 }),
      });
      if (!request.ok) throw new Error(`Reserve planner request failed (${request.status})`);
      setResponse(await request.json() as Response);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Strategic Reserve request failed");
    } finally {
      setLoading(false);
    }
  }

  return <main className="command-shell response-planner">
    <header className="command-header">
      <div><p className="eyebrow">India&apos;s Energy Resilience Command Center</p><h1>Strategic Reserve</h1><p>Site-level continuity guidance coordinated with one exact checked procurement plan.</p></div>
      <span className="mode-badge">MODELED · ASSUMPTION-DEPENDENT OPENING FILL</span>
    </header>
    <nav className="product-nav" aria-label="Product modules">
      <Link href="/">Live Maritime Watch</Link><Link href="/digital-twin">Digital Twin</Link><Link href="/scenario-lab">Scenario Lab</Link><Link href="/response-planner">Response Planner</Link><Link className="active" href="/strategic-reserve">Strategic Reserve</Link>
    </nav>
    <section className="scenario-card">
      <h2>Generate policy guidance</h2>
      <form className="planner-form" onSubmit={generate}>
        <label>Completed scenario run ID<input required value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="UUID" /></label>
        <label>Checked procurement plan ID<input required value={procurementPlanId} onChange={(event) => setProcurementPlanId(event.target.value)} placeholder="UUID" /></label>
        <button disabled={loading}>{loading ? "Solving and checking…" : "Generate modeled guidance"}</button>
      </form>
      <p className="truth-note">Sanjiv recommends guidance only. It does not release reserves, purchase cargo, operate pipelines, or execute replenishment.</p>
      {error && <p role="alert" className="error-text">{error}</p>}
      {response?.reused && <p className="mode-badge">Exact-fingerprint cached result reused</p>}
    </section>
    <section className="profile-grid" aria-label="Reserve policy profiles">
      {profiles.map((profile) => <Profile key={profile} profile={profile} result={response?.results.find((item) => item.profile === profile)} />)}
    </section>
    {response && <Details response={response} />}
  </main>;
}

function Profile({ profile, result }: { profile: string; result?: Result }) {
  return <article className="scenario-card profile-card"><p className="eyebrow">MODELED recommendation</p><h2>{profile.replaceAll("_", " ")}</h2><dl><Fact label="Solver" value={result?.status ?? "NOT_RUN"} /><Fact label="Checker" value={result?.checker?.passed ? "PASSED" : result ? "FAILED" : "NOT_RUN"} /><Fact label="Runtime" value={result?.metadata.runtime ? `${result.metadata.runtime.value.toFixed(4)} second` : "—"} /><Fact label="Residual shortage" value={metric(result?.residual_shortage)} /></dl></article>;
}

function Details({ response }: { response: Response }) {
  return <>
    <section className="scenario-card"><h2>Three reserve sites: capacity and opening-fill truth</h2>{response.plans.map((plan) => <div key={plan.plan_id} className="allocation-group"><h3>{plan.profile}</h3>{plan.input.sites.map((site) => <p key={site.site_id}>{site.site_name}: capacity {metric(site.capacity)} ({site.capacity.truth_class}) · opening {metric(site.opening_inventory)} ({site.opening_inventory_status}) · floor {metric(site.minimum_policy_floor)}</p>)}</div>)}</section>
    <section className="planner-two-column"><article className="scenario-card"><h2>Release schedule, path and receiving refinery</h2>{response.plans.flatMap((plan) => (plan.result.actions ?? []).map((action) => <p key={`${plan.plan_id}-${action.action_id}`}>{plan.profile}: {metric(action.dispatch)} guidance · site {action.site_id.slice(0, 8)} → route {action.route_id.slice(0, 8)} → refinery {action.refinery_id.slice(0, 8)} · receipt {new Date(action.receipt_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}</p>))}</article><article className="scenario-card"><h2>Remaining inventory and cover</h2>{response.plans.flatMap((plan) => (plan.result.timeline ?? []).map((point) => <p key={`${plan.plan_id}-${point.site_id}`}>{plan.profile}: {metric(point.inventory)} · {metric(point.cover)}</p>))}</article></section>
    <section className="planner-two-column"><article className="scenario-card"><h2>Procurement coordination</h2>{response.plans.map((plan) => <p key={plan.plan_id}>{plan.profile}: procurement {plan.input.provenance.procurement_plan_fingerprint} · shared capacities independently checked</p>)}</article><article className="scenario-card"><h2>Replenishment guidance</h2><p>No replenishment input was supplied, so the model creates no hidden replenishment. Any future guidance requires verified input and a new fingerprint.</p></article></section>
    <section className="scenario-card"><h2>Evidence, assumptions and immutable fingerprints</h2>{response.plans.map((plan) => <div key={plan.plan_id}><h3>{plan.profile}</h3><p>Input {plan.input_fingerprint}</p><p>Plan {plan.plan_fingerprint}</p><p>{plan.input.provenance.evidence.length} evidence records · {plan.input.provenance.assumptions.length} expiring assumptions</p></div>)}</section>
  </>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function metric(value?: { value: number; unit: string } | null) { return value ? `${value.value.toFixed(3)} ${value.unit}` : "UNKNOWN"; }
