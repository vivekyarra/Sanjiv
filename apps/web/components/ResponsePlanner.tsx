"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import type { components } from "@sanjiv/contracts";

type Response = components["schemas"]["ProcurementPlanResponse"];
type Result = components["schemas"]["SolverResult"];

const API_URL = process.env.NEXT_PUBLIC_SANJIV_API_URL ?? "http://localhost:8000";
const profiles = ["LOWEST_COST", "BALANCED", "HIGHEST_RESILIENCE"] as const;

export function ResponsePlanner() {
  const [runId, setRunId] = useState("");
  const [response, setResponse] = useState<Response | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function generate(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const request = await fetch(`${API_URL}/api/v1/scenario-runs/${runId}/procurement-plans`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ profiles, time_limit_seconds: 10 }),
      });
      if (!request.ok) throw new Error(`Planner request failed (${request.status})`);
      setResponse(await request.json() as Response);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Response Planner request failed");
    } finally {
      setLoading(false);
    }
  }

  return <main className="command-shell response-planner">
    <header className="command-header">
      <div><p className="eyebrow">India&apos;s Energy Resilience Command Center</p><h1>Response Planner</h1><p>Checked procurement alternatives for modeled shortfall. Commercial availability remains assumption-dependent.</p></div>
      <span className="mode-badge">MODELED · SYNTHETIC COMMERCIAL FIXTURE</span>
    </header>
    <nav className="product-nav" aria-label="Product modules">
      <Link href="/">Live Maritime Watch</Link><Link href="/digital-twin">Digital Twin</Link><Link href="/scenario-lab">Scenario Lab</Link><Link className="active" href="/response-planner">Response Planner</Link><Link href="/strategic-reserve">Strategic Reserve</Link>
    </nav>
    <section className="scenario-card">
      <h2>Generate all three profiles</h2>
      <form className="planner-form" onSubmit={generate}><label>Completed scenario run ID<input required value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="UUID" /></label><button disabled={loading}>{loading ? "Solving and checking…" : "Generate modeled plans"}</button></form>
      <p className="truth-note">Sanjiv recommends planning guidance only. It does not purchase cargo, book tankers, confirm commercial availability, or release reserves.</p>
      {error && <p role="alert" className="error-text">{error}</p>}
      {response?.reused && <p className="mode-badge">Exact-fingerprint cached result reused</p>}
    </section>
    <section className="profile-grid" aria-label="Procurement profiles">
      {profiles.map((profile) => <Profile key={profile} profile={profile} result={response?.results.find((item) => item.profile === profile)} />)}
    </section>
    {response && <Details response={response} />}
  </main>;
}

function Profile({ profile, result }: { profile: string; result?: Result }) {
  const runtime = result?.metadata.runtime?.value;
  return <article className="scenario-card profile-card"><p className="eyebrow">MODELED recommendation</p><h2>{profile.replaceAll("_", " ")}</h2><dl><Fact label="Solver" value={result?.status ?? "NOT_RUN"} /><Fact label="Checker" value={result?.independent_check?.passed ? "PASSED" : result ? "FAILED" : "NOT_RUN"} /><Fact label="Runtime" value={runtime === undefined ? "—" : `${runtime.toFixed(4)} second`} /><Fact label="Delivered" value={metric(result?.delivered_volume)} /><Fact label="Shortage" value={metric(result?.shortage)} /><Fact label="Objective" value={metric(result?.objective?.total)} /></dl><p>Supplier peak {fraction(result?.objective?.raw_metrics?.supplier_concentration)} · corridor peak {fraction(result?.objective?.raw_metrics?.corridor_concentration)}</p></article>;
}

function Details({ response }: { response: Response }) {
  const plans = response.plans ?? [];
  return <>
    <section className="scenario-card"><h2>Supplier, grade, refinery and route allocations</h2>{plans.map((plan) => <div key={plan.plan_id} className="allocation-group"><h3>{plan.profile}</h3>{(plan.solver_result.actions ?? []).map((action) => <p key={action.action_id}>{action.supplier.volume.value} {action.supplier.volume.unit} · supplier {action.supplier.supplier_id.slice(0, 8)} · grade {action.supplier.grade_id.slice(0, 8)} · refinery {action.refinery.refinery_id.slice(0, 8)} · route {action.route.route_id.slice(0, 8)}</p>)}</div>)}</section>
    <section className="planner-two-column"><article className="scenario-card"><h2>Route map and delivery timeline</h2><p>Supplier → load port → corridor → receiving port → refinery</p>{plans.flatMap((plan) => (plan.solver_result.actions ?? []).map((action) => <p key={`${plan.plan_id}-${action.action_id}`}>{new Date(action.delivery_window_start).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} – {new Date(action.delivery_window_end).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}</p>))}</article><article className="scenario-card"><h2>Objective contributions</h2>{plans.map((plan) => <div key={plan.plan_id}><h3>{plan.profile}</h3>{Object.entries(plan.solver_result.objective?.weighted_contributions ?? {}).map(([name, value]) => <p key={name}>{name}: {value.toFixed(4)} objective_point</p>)}</div>)}</article></section>
    <section className="planner-two-column"><article className="scenario-card"><h2>Hard constraints</h2>{plans.map((plan) => <p key={plan.plan_id}>{plan.profile}: {plan.solver_result.constraints?.feasible ? "independently satisfied" : "blocked"} · {plan.solver_result.constraints?.hard_constraint_version}</p>)}</article><article className="scenario-card"><h2>Rejected options</h2>{plans.flatMap((plan) => (plan.solver_result.rejected_options ?? []).map((item) => <p key={`${plan.plan_id}-${item.option_id}`}>{plan.profile}: {item.reason_codes.join(", ")} — {item.explanation}</p>))}</article></section>
    <section className="scenario-card"><h2>Evidence, assumptions and immutable fingerprints</h2>{plans.map((plan) => <div key={plan.plan_id}><h3>{plan.profile}</h3><p>Input {plan.fingerprint_inputs.optimisation_input_fingerprint}</p><p>Plan {plan.plan_fingerprint}</p><p>{plan.fingerprint_inputs.evidence.length} evidence records · {(plan.fingerprint_inputs.assumptions ?? []).length} expiring assumptions</p></div>)}</section>
  </>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function metric(value?: { value: number; unit: string } | null) { return value ? `${value.value.toFixed(3)} ${value.unit}` : "—"; }
function fraction(value?: number) { return value === undefined ? "—" : `${(value * 100).toFixed(1)}%`; }
