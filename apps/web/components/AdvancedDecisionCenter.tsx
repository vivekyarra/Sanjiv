"use client";

import type { components } from "@sanjiv/contracts";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type Catalogue = components["schemas"]["ReplayCatalogue"];
type ReplayCase = components["schemas"]["ReplayCase"];
type ReplayRun = components["schemas"]["ReplayRun"];
type LpgNetwork = components["schemas"]["LpgNetwork"];
type LpgPlan = components["schemas"]["LpgPlan"];
type Sensitivity = components["schemas"]["SensitivityResult"];
type Export = components["schemas"]["BriefingExport"];
type Monitoring = components["schemas"]["PlanMonitoringRecord"];
type PlanComment = components["schemas"]["PlanComment"];

const API_URL = process.env.NEXT_PUBLIC_SANJIV_API_URL ?? "http://localhost:8000";

export function AdvancedDecisionCenter() {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [network, setNetwork] = useState<LpgNetwork | null>(null);
  const [commodity, setCommodity] = useState<"CRUDE_OIL" | "LPG">("CRUDE_OIL");
  const [caseId, setCaseId] = useState("");
  const [run, setRun] = useState<ReplayRun | null>(null);
  const [lpgPlans, setLpgPlans] = useState<LpgPlan[]>([]);
  const [planId, setPlanId] = useState("");
  const [sensitivityMode, setSensitivityMode] = useState<"FAST" | "DEEP">("FAST");
  const [sensitivity, setSensitivity] = useState<Sensitivity | null>(null);
  const [createdExport, setCreatedExport] = useState<Export | null>(null);
  const [monitoring, setMonitoring] = useState<Monitoring | null>(null);
  const [comment, setComment] = useState("Reviewed as decision support; no execution requested.");
  const [comments, setComments] = useState<PlanComment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      requestJson<Catalogue>("/api/v1/replay-catalogue"),
      requestJson<LpgNetwork>("/api/v1/lpg/network"),
    ]).then(([nextCatalogue, nextNetwork]) => {
      setCatalogue(nextCatalogue);
      setNetwork(nextNetwork);
      const firstCrude = nextCatalogue.cases.find((item) => item.commodity === "CRUDE_OIL");
      setCaseId(firstCrude?.case_id ?? "");
    }).catch((reason: unknown) => setError(message(reason)));
  }, []);

  const cases = useMemo(
    () => catalogue?.cases.filter((item) => item.commodity === commodity) ?? [],
    [catalogue, commodity],
  );
  const selected = cases.find((item) => item.case_id === caseId) ?? cases[0];

  function changeCommodity(next: "CRUDE_OIL" | "LPG") {
    setCommodity(next);
    setCaseId(catalogue?.cases.find((item) => item.commodity === next)?.case_id ?? "");
    setRun(null); setLpgPlans([]); setError("");
  }

  async function executeReplay() {
    if (!selected) return;
    setBusy(true); setError(""); setRun(null); setLpgPlans([]);
    try {
      const nextRun = await requestJson<ReplayRun>(`/api/v1/replay-cases/${selected.case_id}/runs`, post());
      setRun(nextRun);
      if (nextRun.commodity === "LPG") {
        setLpgPlans(await requestJson<LpgPlan[]>(`/api/v1/replay-runs/${nextRun.run_id}/lpg-plans`));
      }
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  async function analyseSensitivity() {
    if (!planId) return;
    setBusy(true); setError("");
    try {
      setSensitivity(await requestJson<Sensitivity>(`/api/v1/plans/${planId}/sensitivity-runs`, post({ mode: sensitivityMode, seed: 20260721, ranges: [], correlations: [] })));
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  async function createExport(kind: "MACHINE_READABLE_JSON" | "PDF_BRIEFING") {
    if (!planId) return;
    setBusy(true); setError("");
    try { setCreatedExport(await requestJson<Export>(`/api/v1/plans/${planId}/exports`, post({ kind }))); }
    catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  async function createLpgExport(subjectId: string) {
    setBusy(true); setError("");
    try { setCreatedExport(await requestJson<Export>(`/api/v1/lpg-plans/${subjectId}/exports`, post({ kind: "MACHINE_READABLE_JSON" }))); }
    catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  async function monitorPlan() {
    if (!planId || !run) return;
    setBusy(true); setError("");
    try { setMonitoring(await requestJson<Monitoring>(`/api/v1/plans/${planId}/monitoring`, post({ replay_run_id: run.run_id }))); }
    catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  async function addComment() {
    if (!planId || !comment.trim()) return;
    setBusy(true); setError("");
    try {
      await requestJson<PlanComment>(`/api/v1/plans/${planId}/comments`, {
        ...post({ comment }),
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
          "X-Sanjiv-Demo-Identity": "local-demo-reviewer",
        },
      });
      setComments(await requestJson<PlanComment[]>(`/api/v1/plans/${planId}/comments`));
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  return <main className="command-shell advanced-center">
    <header className="command-header">
      <div><p className="eyebrow">India&apos;s Energy Resilience Command Center</p><h1>Historical Replay &amp; Advanced Decisions</h1><p>Validate disruption behavior, crude/LPG generality, stability, audited exports, and monitored outcomes.</p></div>
      <span className="mode-badge">REPLAY · SYNTHETIC FIXTURE · NOT LIVE</span>
    </header>
    <nav className="product-nav" aria-label="Product modules">
      <Link href="/">Live Maritime Watch</Link><Link href="/digital-twin">Digital Twin</Link><Link href="/scenario-lab">Scenario Lab</Link><Link href="/response-planner">Response Planner</Link><Link href="/strategic-reserve">Strategic Reserve</Link><Link href="/risk-intelligence">Risk Intelligence</Link><Link href="/evidence-approval">Evidence &amp; Approval</Link><Link className="active" href="/historical-replay">Historical Replay</Link>
    </nav>
    {error && <section className="scenario-card degraded-state" role="alert"><h2>Explicit degraded state</h2><p>{error}</p><p>No missing result has been replaced with zero or presented as usable.</p></section>}
    {!catalogue && !error && <section className="scenario-card" aria-live="polite"><p>Loading checksummed replay catalogue and LPG fixture…</p></section>}
    {catalogue && <>
      <section className="scenario-card replay-control-card">
        <div className="governance-heading"><div><p className="eyebrow">Validation catalogue</p><h2>{catalogue.cases.length} versioned replay cases</h2></div><span className="audit-badge passed">{catalogue.manifest.classification} · {catalogue.manifest.license}</span></div>
        <p className="truth-note">{catalogue.manifest.warning}</p>
        <div className="mode-switch" aria-label="Commodity selector">
          <button className={commodity === "CRUDE_OIL" ? "selected" : ""} onClick={() => changeCommodity("CRUDE_OIL")} type="button">Crude oil</button>
          <button className={commodity === "LPG" ? "selected" : ""} onClick={() => changeCommodity("LPG")} type="button">LPG</button>
        </div>
        <div className="planner-form"><label>Replay case<select value={selected?.case_id ?? ""} onChange={(event) => setCaseId(event.target.value)}>{cases.map((item) => <option key={item.case_id} value={item.case_id}>{item.name}</option>)}</select></label><button disabled={busy || !selected} onClick={() => void executeReplay()} type="button">{busy ? "Running…" : "Run deterministic replay"}</button></div>
        {selected && <ReplayCaseSummary value={selected} />}
      </section>
      {run ? <ReplayResult run={run} /> : <section className="scenario-card empty-state"><h2>No replay selected</h2><p>Choose a declared fixture case and run it to compare modeled action with the no-action baseline.</p></section>}
        {run?.commodity === "LPG" && <section className="scenario-card"><div className="governance-heading"><div><p className="eyebrow">Typed second commodity</p><h2>LPG candidate allocations</h2></div><span className="audit-badge passed">RESERVE · NOT APPLICABLE</span></div><p>{network?.assumption_notice}</p><div className="profile-grid">{lpgPlans.map((plan) => <article className="profile-card" key={plan.plan_id}><h3>{plan.profile.replaceAll("_", " ")}</h3><dl><Fact label="Delivered" value={metric(plan.delivered_volume)} /><Fact label="Residual shortage" value={metric(plan.residual_shortage)} /><Fact label="Landed cost" value={metric(plan.total_landed_cost)} /><Fact label="Supplier concentration" value={percent(plan.supplier_concentration.value)} /></dl><p>{plan.solver_status} · independent checker {plan.checker_passed ? "PASSED" : "FAILED"} · audit {plan.audit_status}</p><button className="primary-action" disabled={busy || plan.audit_status !== "PASSED"} onClick={() => void createLpgExport(plan.plan_id)} type="button">Create audited LPG package</button><details><summary>Routes, compatibility and evidence</summary>{plan.allocations.map((item) => <p key={item.route_id}>{item.supplier_id} → {item.terminal_id}: {metric(item.volume)} · arrival {metric(item.arrival_days)}</p>)}<p className="fingerprint">{plan.fingerprint}</p></details></article>)}</div></section>}
      <section className="scenario-card"><p className="eyebrow">Plan stability, briefing, collaboration &amp; monitoring</p><h2>Audited plan workspace</h2><p>Paste a real procurement or reserve plan ID from Response Planner or Strategic Reserve. Exports are server-blocked whenever its current Evidence Auditor result fails.</p><div className="planner-form"><label>Audited plan ID<input value={planId} onChange={(event) => setPlanId(event.target.value)} placeholder="UUID" /></label><label>Analysis mode<select value={sensitivityMode} onChange={(event) => setSensitivityMode(event.target.value as "FAST" | "DEEP")}><option value="FAST">Fast · 40 seeded samples</option><option value="DEEP">Deep · 500 seeded samples</option></select></label><button disabled={busy || !planId} onClick={() => void analyseSensitivity()} type="button">Run sensitivity</button></div>
        {sensitivity && <div className="planner-two-column"><article><h3>Deterministic sensitivity · not probability</h3><p>Median {metric(sensitivity.median)} · P10 {metric(sensitivity.p10)} · P90 {metric(sensitivity.p90)}</p><p>Best {metric(sensitivity.best_case)} · worst {metric(sensitivity.worst_case)}</p><p>{sensitivity.sample_count} samples · seed {sensitivity.seed} · {sensitivity.sampling_method}</p></article><article><h3>Plan stability</h3><strong className="stability-score">{percent(sensitivity.plan_stability.value)}</strong><p>Method {sensitivity.stability_method_version}. This is sampled plan stability, not calibrated disruption probability.</p>{sensitivity.drivers.map((item) => <p key={item.name}>#{item.rank} {item.name}: {percent(item.normalized_effect.value)}</p>)}</article></div>}
        <div className="workflow-actions"><button disabled={busy || !planId} onClick={() => void createExport("MACHINE_READABLE_JSON")} type="button">Create audited JSON package</button><button disabled={busy || !planId} onClick={() => void createExport("PDF_BRIEFING")} type="button">Create audited PDF briefing</button><button disabled={busy || !planId || !run} onClick={() => void monitorPlan()} type="button">Compare with replay outcome</button></div>
        <div className="review-workflow"><label>Immutable reviewer comment<textarea value={comment} onChange={(event) => setComment(event.target.value)} /></label><button className="primary-action" disabled={busy || !planId || !comment.trim()} onClick={() => void addComment()} type="button">Add review comment</button>{comments.map((item) => <p className="immutable-record" key={item.comment_id}>{item.actor_id} ({item.actor_role}) · {new Date(item.created_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} · {item.comment} · immutable</p>)}</div>
        {createdExport && <div className="evidence-card"><strong>{createdExport.kind} ready</strong><span>{createdExport.truth_label} · {createdExport.byte_count} bytes</span><span>SHA-256 {createdExport.sha256}</span><a href={`${API_URL}/api/v1/exports/${createdExport.export_id}/download`}>Download verified artifact</a></div>}
        {monitoring && <div className="evidence-card"><strong>Monitored outcome · REPLAY</strong><span>Expected {metric(monitoring.expected_shortage)} · replayed {metric(monitoring.replayed_shortage)}</span><span>Deviation {metric(monitoring.deviation)}</span>{monitoring.stale_input_warnings.map((item) => <span key={item}>{item}</span>)}<span>No order-placement or reserve-execution integration.</span></div>}
      </section>
    </>}
  </main>;
}

function ReplayCaseSummary({ value }: { value: ReplayCase }) {
  return <div className="planner-two-column"><article><h3>{value.name}</h3><p>{value.event_type.replaceAll("_", " ")} · {value.duration_days} days · disruption {value.disruption_percent}%</p><p>Original interval {new Date(value.original_interval.starts_at).toLocaleDateString("en-IN")} to {new Date(value.original_interval.ends_at).toLocaleDateString("en-IN")}</p></article><article><h3>Declared evidence boundary</h3><p>{value.classification} · {value.source_or_generator}</p><p>{value.license} · {value.redistribution_status}</p><p>{value.assumptions.join(" ")}</p></article></div>;
}

function ReplayResult({ run }: { run: ReplayRun }) {
  const maximum = Math.max(...run.timeline.map((item) => item.no_action_shortage.value), 1);
  return <section className="scenario-card"><div className="governance-heading"><div><p className="eyebrow">Observe → Detect → Simulate → Optimise → Monitor</p><h2>{run.case_id}</h2></div><span className={`audit-badge ${run.audit_status.toLowerCase()}`}>{run.truth_label} · AUDIT {run.audit_status}</span></div>{!run.export_allowed && <p className="blocked-claim">This result remains visible but is blocked from usable export: audit or independent checker did not pass.</p>}<div className="metric-strip"><Metric label="No action" value={metric(run.no_action_shortage)} /><Metric label="Modeled response" value={metric(run.recommended_shortage)} /><Metric label="Shortfall reduction" value={metric(run.shortfall_reduction)} /><Metric label="Evidence coverage" value={metric(run.evidence_coverage)} /></div><div className="replay-timeline" aria-label="No-action and recommendation timeline">{run.timeline.map((item) => <div key={item.day} title={`Day ${item.day + 1}: ${metric(item.no_action_shortage)} no action; ${metric(item.recommended_shortage)} response`}><i style={{ height: `${Math.max(2, item.no_action_shortage.value / maximum * 100)}%` }} /><b style={{ height: `${Math.max(2, item.recommended_shortage.value / maximum * 100)}%` }} /><span>{item.day + 1}</span></div>)}</div><div className="planner-two-column"><article><h3>Validation metrics</h3><p>Detection lead {metric(run.detection_lead_time)} · recommendation runtime {metric(run.recommendation_runtime)}</p><p>Cost increase {metric(run.cost_increase)} · checker {run.checker_passed ? "PASSED" : "FAILED"}</p><p>{run.detection_outcome} · {run.plan_outcome}</p></article><article><h3>Invariants, evidence &amp; assumptions</h3>{Object.entries(run.invariant_results).map(([name, passed]) => <p key={name}>{passed ? "✓" : "✕"} {name.replaceAll("_", " ")}</p>)}<details><summary>Evidence and assumption drawer</summary>{run.evidence_records.map((item) => <p key={item.id}>{item.dataset} · {item.mode} · hash {item.raw_payload_hash}</p>)}{run.assumptions.map((item) => <p key={item.id}>{item.status} · {item.rationale}</p>)}</details></article></div><p className="fingerprint">Run {run.run_id} · fixture {run.library_checksum} · result {run.fingerprint}</p></section>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><p>{label}</p><strong>{value}</strong></div>; }
function metric(value: { value: number; unit: string }) { return `${value.value.toLocaleString("en-IN", { maximumFractionDigits: 2 })} ${value.unit}`; }
function percent(value: number) { return `${(value * 100).toFixed(1)}%`; }
function message(reason: unknown) { return reason instanceof Error ? reason.message : "Phase 8 service is unavailable"; }
function post(body?: object): RequestInit { return { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }, body: body ? JSON.stringify(body) : undefined }; }
async function requestJson<T>(path: string, init?: RequestInit): Promise<T> { const response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init }); if (!response.ok) { const body = await response.json().catch(() => ({})) as { message?: string; detail?: string }; throw new Error(body.message ?? body.detail ?? `Request failed (${response.status})`); } return await response.json() as T; }
