"use client";

import type { components } from "@sanjiv/contracts";
import { FormEvent, useMemo, useState } from "react";

type Audit = components["schemas"]["EvidenceAuditResult"];
type Explanation = components["schemas"]["PlanExplanation"];
type Governance = components["schemas"]["PlanGovernanceState"];
type Evidence = components["schemas"]["EvidenceRecord"];
type Assumption = components["schemas"]["Assumption"];

const API_URL = process.env.NEXT_PUBLIC_SANJIV_API_URL ?? "http://localhost:8000";
const identities = {
  operator: "local-demo-operator",
  reviewer: "local-demo-reviewer",
  approver: "local-demo-approver",
  administrator: "local-demo-administrator",
} as const;
type Role = keyof typeof identities;

export function GovernancePanel({ initialPlanId = "", compact = false }: { initialPlanId?: string; compact?: boolean }) {
  const [planId, setPlanId] = useState(initialPlanId);
  const [audit, setAudit] = useState<Audit | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [governance, setGovernance] = useState<Governance | null>(null);
  const [assumptions, setAssumptions] = useState<Assumption[]>([]);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [role, setRole] = useState<Role>("approver");
  const [comment, setComment] = useState("Reviewed as decision support; no operational execution authorized.");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function inspect(event?: FormEvent) {
    event?.preventDefault();
    if (!planId) return;
    setBusy(true); setError(""); setEvidence(null);
    try {
      const nextAudit = await getJson<Audit>(`/api/v1/plans/${planId}/audit`);
      const [nextExplanation, nextGovernance, nextAssumptions] = await Promise.all([
        getJson<Explanation>(`/api/v1/plans/${planId}/explanation`),
        getJson<Governance>(`/api/v1/plans/${planId}/governance`),
        getJson<Assumption[]>(`/api/v1/plans/${planId}/assumptions`),
      ]);
      setAudit(nextAudit); setExplanation(nextExplanation); setGovernance(nextGovernance); setAssumptions(nextAssumptions);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Evidence audit failed"); }
    finally { setBusy(false); }
  }

  async function act(action: "SUBMIT_FOR_REVIEW" | "REVIEW" | "APPROVE" | "REJECT") {
    if (!audit) return;
    setBusy(true); setError("");
    const endpoint = action === "APPROVE" ? "approvals" : action === "REJECT" ? "rejections" : "reviews";
    const body = {
      ...(endpoint === "reviews" ? { action } : {}),
      plan_fingerprint: audit.fingerprints.plan,
      assumption_fingerprint: audit.fingerprints.assumptions,
      audit_fingerprint: audit.audit_fingerprint,
      comment,
    };
    try {
      await getJson(`/api/v1/plans/${planId}/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID(), "X-Sanjiv-Demo-Identity": identities[role] },
        body: JSON.stringify(body),
      });
      setGovernance(await getJson<Governance>(`/api/v1/plans/${planId}/governance`));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Lifecycle action failed"); }
    finally { setBusy(false); }
  }

  async function openEvidence(evidenceId: string) {
    try { setEvidence(await getJson<Evidence>(`/api/v1/evidence/${evidenceId}`)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Evidence unavailable"); }
  }

  const selectedMetric = audit?.metrics.find((item) => item.path.includes("shortage")) ?? audit?.metrics[0];
  const controls = useMemo(() => ({
    submit: role === "operator" || role === "reviewer" || role === "administrator",
    review: role === "reviewer" || role === "administrator",
    approve: role === "approver" || role === "administrator",
  }), [role]);

  return <section className={`scenario-card governance-panel ${compact ? "compact" : ""}`} aria-labelledby="governance-title">
    <div className="governance-heading"><div><p className="eyebrow">Human authority checkpoint</p><h2 id="governance-title">Evidence, assumptions &amp; approval</h2></div>{audit && <span className={`audit-badge ${audit.status.toLowerCase()}`}>{audit.status} · {audit.evidence_coverage_percentage.toFixed(1)}% coverage</span>}</div>
    <form className="planner-form" onSubmit={inspect}><label>Procurement or reserve plan ID<input required value={planId} onChange={(event) => setPlanId(event.target.value)} placeholder="UUID" /></label><button disabled={busy}>{busy ? "Checking…" : "Run Evidence Audit"}</button></form>
    <p className="truth-note">Approval records a human decision only. Sanjiv does not place orders, charter vessels, release reserves, or call operational control systems.</p>
    {error && <p role="alert" className="error-text">{error}</p>}
    {audit && <>
      {audit.status === "FAILED" && <div className="blocked-claim" role="alert"><strong>Recommendation blocked</strong>{audit.failures.map((failure) => <p key={`${failure.code}-${failure.path}`}>{failure.code}: {failure.message}</p>)}</div>}
      <div className="planner-two-column"><article><h3>Why this plan?</h3><p>{explanation?.summary}</p><p>{explanation?.difference_from_no_action}</p><details open={!compact}><summary>Objective and trade-offs</summary>{Object.entries(explanation?.objective_components ?? {}).map(([name, value]) => <p key={name}>{name}: {value.toFixed(4)} objective_point</p>)}{explanation?.primary_tradeoffs.map((item) => <p key={item}>{item}</p>)}</details><details><summary>Rejected alternatives</summary>{explanation?.rejected_alternatives.map((item) => <p key={item.subject_id}>{item.reason_codes.join(", ")}: {item.explanation}</p>)}</details></article>
      <article><h3>Recomputation status</h3><p>Solver {audit.solver_status} · checker {audit.checker_passed ? "PASSED" : "FAILED"}</p><p>Recompute {audit.recomputation_passed ? "RECONCILED" : "MISMATCH"} · auditor {audit.auditor_version}</p><p className="fingerprint">Audit {audit.audit_fingerprint}</p></article></div>
      {selectedMetric && <details open={!compact}><summary>KPI evidence drawer — {selectedMetric.path}</summary><p>{selectedMetric.value} {selectedMetric.unit} · {selectedMetric.truth_class} · {selectedMetric.freshness_status}</p><p>Transformation {selectedMetric.transformation} · model {selectedMetric.model_version}</p>{selectedMetric.evidence_ids.map((id) => <button className="evidence-link" key={id} onClick={() => void openEvidence(id)} type="button">Open evidence {id}</button>)}</details>}
      {evidence && <div className="evidence-card"><strong>{evidence.dataset} · {evidence.dataset_version}</strong><span>{evidence.source_id} / {evidence.source_record_id}</span><span>{evidence.truth_class} · {evidence.mode} · confidence {evidence.confidence}</span><span>Immutable payload hash {evidence.raw_payload_hash}</span></div>}
      <details open={!compact}><summary>Assumption drawer ({assumptions.length})</summary>{assumptions.map((item) => <div className="assumption-card" key={item.id}><strong>{item.key}</strong><span>{item.status} · expires {item.expires_at ? new Date(item.expires_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) : "never"}</span><span>{item.rationale}</span></div>)}</details>
      <div className="review-workflow"><h3>Review workflow · {governance?.state ?? "RECOMMENDED"}</h3>{governance?.superseded_warning && <p className="blocked-claim">{governance.superseded_warning}</p>}<label>Configured demo identity and role<select value={role} onChange={(event) => setRole(event.target.value as Role)}>{Object.keys(identities).map((item) => <option key={item} value={item}>{item}</option>)}</select></label><label>Immutable review comment<textarea value={comment} onChange={(event) => setComment(event.target.value)} /></label><div className="workflow-actions">{controls.submit && governance?.state === "RECOMMENDED" && <button onClick={() => void act("SUBMIT_FOR_REVIEW")} disabled={busy || !audit.approval_allowed}>Submit for review</button>}{controls.review && governance?.state === "UNDER_REVIEW" && <button onClick={() => void act("REVIEW")} disabled={busy}>Record review</button>}{controls.approve && governance?.state === "UNDER_REVIEW" && <><button onClick={() => void act("APPROVE")} disabled={busy || !audit.approval_allowed}>Approve</button><button className="danger-action" onClick={() => void act("REJECT")} disabled={busy}>Reject</button></>}</div>{governance?.records.map((record) => <p className="immutable-record" key={record.record_id}>{record.action} · {record.actor_id} ({record.actor_role}) · {new Date(record.occurred_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} · immutable</p>)}</div>
    </>}
  </section>;
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  if (!response.ok) { const body = await response.json().catch(() => ({})) as { message?: string; detail?: string }; throw new Error(body.message ?? body.detail ?? `Request failed (${response.status})`); }
  return await response.json() as T;
}
