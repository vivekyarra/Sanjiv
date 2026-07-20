"use client";

import type { components } from "@sanjiv/contracts";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

type Snapshot = components["schemas"]["TwinSnapshot"];
type Metadata = components["schemas"]["ScenarioFormMetadata"];
type CompileResponse = components["schemas"]["ScenarioCompileResponse"];
type Confirmed = components["schemas"]["ConfirmedScenario"];
type Run = components["schemas"]["SimulationRun"];
type Progress = components["schemas"]["SimulationProgressEvent"];
type DisruptionType = components["schemas"]["DisruptionType"];
type TargetType = components["schemas"]["DisruptionTargetType"];

const API_URL = process.env.NEXT_PUBLIC_SANJIV_API_URL ?? "http://localhost:8000";
const TERMINAL = new Set(["COMPLETED", "FAILED", "CANCELLED"]);

const targetFor: Record<DisruptionType, TargetType> = {
  CHOKEPOINT_CLOSURE: "CHOKEPOINT",
  CHOKEPOINT_CAPACITY_REDUCTION: "CHOKEPOINT",
  MARITIME_ROUTE_CAPACITY_REDUCTION: "ROUTE",
  SUPPLIER_VOLUME_REDUCTION: "SUPPLIER",
  PORT_DISRUPTION: "PORT",
  REFINERY_THROUGHPUT_DISRUPTION: "REFINERY",
};

export function ScenarioLab() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [metadata, setMetadata] = useState<Metadata | null>(null);
  const [text, setText] = useState("Close the Strait of Hormuz for 14 days.");
  const [structured, setStructured] = useState(false);
  const [disruptionType, setDisruptionType] = useState<DisruptionType>("CHOKEPOINT_CLOSURE");
  const [target, setTarget] = useState("chokepoint:strait-of-hormuz");
  const [duration, setDuration] = useState(14);
  const [reduction, setReduction] = useState(100);
  const [delayedStart, setDelayedStart] = useState(0);
  const [compoundRefinery, setCompoundRefinery] = useState(false);
  const [compiled, setCompiled] = useState<CompileResponse | null>(null);
  const [confirmed, setConfirmed] = useState<Confirmed | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [progress, setProgress] = useState<Progress[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([
      fetchJson<Snapshot>("/api/v1/twin/snapshots/current"),
      fetchJson<Metadata>("/api/v1/scenarios/form-metadata"),
    ])
      .then(([nextSnapshot, nextMetadata]) => {
        setSnapshot(nextSnapshot);
        setMetadata(nextMetadata);
      })
      .catch((reason: unknown) => setError(message(reason)));
  }, []);

  const activeTargetType = targetFor[disruptionType];
  const targetOptions = useMemo(() => {
    if (!snapshot) return [];
    if (activeTargetType === "ROUTE") {
      return snapshot.routes.map((route) => ({ id: route.canonical_id, name: route.canonical_id }));
    }
    const kinds: Record<Exclude<TargetType, "ROUTE">, string[]> = {
      CHOKEPOINT: ["CHOKEPOINT"],
      SUPPLIER: ["SUPPLIER"],
      PORT: ["LOAD_PORT", "INDIAN_PORT"],
      REFINERY: ["REFINERY"],
    };
    return snapshot.nodes
      .filter((node) => kinds[activeTargetType as Exclude<TargetType, "ROUTE">].includes(node.kind))
      .map((node) => ({ id: node.canonical_id, name: node.name }));
  }, [activeTargetType, snapshot]);

  const selectedTarget = targetOptions.some((item) => item.id === target)
    ? target
    : (targetOptions[0]?.id ?? target);

  const compile = useCallback(async () => {
    if (!snapshot) return;
    setBusy(true);
    setError(null);
    setConfirmed(null);
    setRun(null);
    try {
      const start = new Date(Date.now() + delayedStart * 86_400_000).toISOString();
      const disruptions = [effect(disruptionType, activeTargetType, selectedTarget, reduction)];
      if (compoundRefinery) {
        disruptions.push(
          effect(
            "REFINERY_THROUGHPUT_DISRUPTION",
            "REFINERY",
            "refinery:jamnagar",
            20,
          ),
        );
      }
      const payload = structured
        ? {
            mode: "STRUCTURED_FORM",
            twin_snapshot_id: snapshot.snapshot_id,
            structured: {
              scenario_name: "Structured no-action disruption",
              twin_snapshot_id: snapshot.snapshot_id,
              disruption_start: start,
              disruption_duration: { value: duration, unit: "day" },
              simulation_horizon: { value: Math.max(30, duration), unit: "day" },
              disruptions,
              assumptions: [],
            },
          }
        : {
            mode: "AUTO",
            twin_snapshot_id: snapshot.snapshot_id,
            text,
          };
      setCompiled(
        await fetchJson<CompileResponse>("/api/v1/scenarios/compile", {
          method: "POST",
          headers: mutationHeaders(),
          body: JSON.stringify(payload),
        }),
      );
    } catch (reason: unknown) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }, [
    activeTargetType,
    compoundRefinery,
    delayedStart,
    disruptionType,
    duration,
    reduction,
    snapshot,
    structured,
    selectedTarget,
    text,
  ]);

  const confirm = useCallback(async () => {
    const candidate = compiled?.candidate;
    if (!candidate) return;
    setBusy(true);
    setError(null);
    try {
      setConfirmed(
        await fetchJson<Confirmed>(`/api/v1/scenarios/${candidate.scenario_id}/confirm`, {
          method: "POST",
          headers: mutationHeaders(),
          body: JSON.stringify({ confirming_identity: "local-demo-operator" }),
        }),
      );
    } catch (reason: unknown) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }, [compiled]);

  const simulate = useCallback(async () => {
    if (!confirmed) return;
    setBusy(true);
    setError(null);
    try {
      setRun(
        await fetchJson<Run>("/api/v1/scenario-runs", {
          method: "POST",
          headers: mutationHeaders(),
          body: JSON.stringify({ scenario_id: confirmed.scenario_id, configuration: {} }),
        }),
      );
    } catch (reason: unknown) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }, [confirmed]);

  useEffect(() => {
    if (!run || TERMINAL.has(run.status)) return;
    const timer = window.setInterval(() => {
      void Promise.all([
        fetchJson<Run>(`/api/v1/scenario-runs/${run.run_id}`),
        fetchJson<Progress[]>(`/api/v1/scenario-runs/${run.run_id}/progress`),
      ])
        .then(([nextRun, nextProgress]) => {
          setRun(nextRun);
          setProgress(nextProgress);
        })
        .catch((reason: unknown) => setError(message(reason)));
    }, 350);
    return () => window.clearInterval(timer);
  }, [run]);

  const cancel = useCallback(async () => {
    if (!run) return;
    try {
      setRun(
        await fetchJson<Run>(`/api/v1/scenario-runs/${run.run_id}/cancel`, {
          method: "POST",
          headers: mutationHeaders(),
        }),
      );
    } catch (reason: unknown) {
      setError(message(reason));
    }
  }, [run]);

  const validation = compiled?.validation;
  const result = run?.result;
  const errors = (validation?.issues ?? []).filter((item) => item.severity === "ERROR");
  const warnings = (validation?.issues ?? []).filter((item) => item.severity !== "ERROR");

  return (
    <main className="scenario-shell">
      <div className="scenario-banner" role="status">
        DETERMINISTIC NO-ACTION ANALYSIS · HUMAN CONFIRMATION REQUIRED · NO PROCUREMENT ACTIONS
      </div>
      <header className="command-header twin-header">
        <div className="brand-lockup">
          <span className="brand-mark">S</span>
          <div>
            <h1>Sanjiv</h1>
            <p>India&apos;s Energy Resilience Command Center · Scenario Lab</p>
            <small>Keep India&apos;s energy moving.</small>
          </div>
        </div>
        <nav className="product-nav" aria-label="Product modules">
          <Link href="/">Live Maritime Watch</Link>
          <Link href="/digital-twin">Digital Twin</Link>
          <Link className="active" href="/scenario-lab">Scenario Lab</Link>
        </nav>
      </header>

      {error && <div className="operational-warning" role="alert">{error}</div>}
      {error?.toLowerCase().includes("stale") && <div className="operational-warning" role="alert">STALE SNAPSHOT — select and reconfirm an available immutable twin.</div>}
      <section className="scenario-status-strip" aria-label="Scenario status">
        <Status label="Interpreter" value={metadata?.interpreter_label ?? "Loading"} />
        <Status label="Optional LLM" value={metadata?.llm_provider_available ? "AVAILABLE" : "UNAVAILABLE · FALLBACK ACTIVE"} />
        <Status label="Twin snapshot" value={snapshot ? `${snapshot.version} · ${snapshot.fingerprint.slice(0, 12)}` : "Loading"} />
        <Status label="Lifecycle" value={run?.status ?? confirmed?.lifecycle ?? (validation?.valid ? "VALIDATED" : "DRAFT")} />
      </section>

      <section className="scenario-layout">
        <div className="scenario-workbench">
          <section className="scenario-card input-card">
            <div className="section-heading"><p>Scenario compiler</p><span>{structured ? "STRUCTURED FORM" : "DETERMINISTIC TEXT"}</span></div>
            <div className="mode-switch" role="group" aria-label="Scenario input mode">
              <button className={!structured ? "selected" : ""} onClick={() => setStructured(false)}>Natural-language pattern</button>
              <button className={structured ? "selected" : ""} onClick={() => setStructured(true)}>Structured fallback</button>
            </div>
            {!structured ? (
              <label>Supported scenario text<textarea value={text} onChange={(event) => setText(event.target.value)} /><small>Bounded patterns only. Unsupported or ambiguous language returns clarification; it is never invented.</small></label>
            ) : (
              <div className="structured-grid">
                <label>Disruption type<select value={disruptionType} onChange={(event) => setDisruptionType(event.target.value as DisruptionType)}>{metadata?.supported_types.map((item) => <option key={item.disruption_type} value={item.disruption_type}>{item.disruption_type.replaceAll("_", " ")}</option>)}</select></label>
                <label>Target<select value={selectedTarget} onChange={(event) => setTarget(event.target.value)}>{targetOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                <label>Delayed start (days)<input type="number" min="0" max="90" value={delayedStart} onChange={(event) => setDelayedStart(Number(event.target.value))} /></label>
                <label>Duration (days)<input type="number" min="1" max="90" value={duration} onChange={(event) => setDuration(Number(event.target.value))} /></label>
                <label>Capacity / volume reduction (%)<input type="number" min="1" max="100" value={reduction} onChange={(event) => setReduction(Number(event.target.value))} /></label>
                <label className="compound-control"><input type="checkbox" checked={compoundRefinery} onChange={(event) => setCompoundRefinery(event.target.checked)} /> Add Jamnagar throughput reduction (20%)</label>
              </div>
            )}
            <button className="primary-action" disabled={busy || !snapshot} onClick={() => void compile()}>{busy ? "Compiling…" : "Compile and validate"}</button>
          </section>

          {!compiled && <section className="scenario-card empty-state"><h2>No scenario candidate yet</h2><p>Compile a documented text pattern or use the always-available structured form.</p></section>}
          {compiled?.interpretation.status === "PROVIDER_UNAVAILABLE" && <section className="scenario-card provider-state" role="alert"><h2>Optional provider unavailable</h2><p>Nothing is blocked. Continue with the deterministic parser or structured form.</p></section>}
          {compiled?.candidate && <section className="scenario-card candidate-card">
            <div className="section-heading"><p>Parsed scenario candidate</p><span>{compiled.candidate.source_mode}</span></div>
            <h2>{compiled.candidate.scenario_name}</h2>
            <p className="fingerprint">Scenario fingerprint {compiled.candidate.scenario_fingerprint}</p>
            <div className="candidate-facts"><Fact label="Start" value={format(compiled.candidate.parameters.disruption_start)} /><Fact label="Duration" value={`${compiled.candidate.parameters.disruption_duration.value} ${compiled.candidate.parameters.disruption_duration.unit}`} /><Fact label="Horizon" value={`${compiled.candidate.parameters.simulation_horizon.value} ${compiled.candidate.parameters.simulation_horizon.unit}`} /></div>
            <h3>Resolved assets</h3>{(validation?.resolved_targets ?? []).map((item) => <div className="resolved-row" key={item.asset_id}><strong>{item.display_name}</strong><span>{item.canonical_id}</span></div>)}
            <h3>Defaults requiring confirmation</h3>{(compiled.candidate.defaults ?? []).length ? (compiled.candidate.defaults ?? []).map((item) => <Notice key={item.field} tone="default" title={item.field} text={`${String(item.value)} ${item.unit} · ${item.rationale}`} />) : <p className="muted">No defaults were applied.</p>}
            <h3>Assumptions requiring confirmation</h3>{(compiled.candidate.parameters.assumptions ?? []).map((item) => <Notice key={item.id} tone="assumption" title={item.key} text={`${item.rationale} · expires ${item.expires_at ? format(item.expires_at) : "not set"}`} />)}
            {errors.map((item) => <Notice key={`${item.code}-${item.field}`} tone="error" title={item.code} text={item.message} />)}
            {warnings.map((item) => <Notice key={`${item.code}-${item.field}`} tone="warning" title={item.severity} text={item.message} />)}
            <details><summary>Canonical candidate JSON</summary><pre>{JSON.stringify(compiled.candidate, null, 2)}</pre></details>
            <button className="primary-action" disabled={busy || !validation?.valid || Boolean(confirmed)} onClick={() => void confirm()}>{confirmed ? "Confirmed" : "Confirm frozen scenario"}</button>
          </section>}

          {confirmed && <section className="scenario-card confirmation-card"><div className="section-heading"><p>Human confirmation</p><span>SERVER AUDITED</span></div><h2>Frozen and ready</h2><p>Confirmed by {confirmed.confirmed_by} at {format(confirmed.confirmed_at)}. Any input edit produces a new fingerprint and requires confirmation again.</p><button className="primary-action" disabled={busy || Boolean(run)} onClick={() => void simulate()}>Run deterministic no-action simulation</button></section>}

          {run && <section className="scenario-card progress-card"><div className="section-heading"><p>Simulation progress</p><span>{run.status}</span></div><div className="progress-track"><i style={{ width: `${progress.at(-1)?.progress_percent ?? 0}%` }} /></div>{progress.map((item) => <div className="progress-row" key={item.sequence}><strong>{item.phase}</strong><span>{item.progress_percent}% · {item.message}</span></div>)}{!TERMINAL.has(run.status) && <button className="danger-action" onClick={() => void cancel()}>Cancel simulation</button>}{run.status === "CANCELLED" && <Notice tone="warning" title="CANCELLED" text="No result was fabricated. Create a new confirmed scenario to run again." />}{run.status === "FAILED" && <Notice tone="error" title={run.failure?.code ?? "SIMULATION FAILED"} text={run.failure?.message ?? "Typed simulation failure."} />}</section>}

          {result && <Results run={run} />}
        </div>

        <aside className="scenario-sidebar">
          <section className="scenario-card"><div className="section-heading"><p>Truth boundary</p><span>PHASE 3</span></div><Fact label="Baseline" value="Frozen twin reference" /><Fact label="No-action impact" value="MODELED" /><Fact label="Inventory" value={result?.inventory_status ?? "UNKNOWN unless supplied"} /><Fact label="Future response planning" value="NOT INCLUDED" /><p className="muted">This phase does not optimise procurement, recommend reserve actions, or execute operational changes.</p></section>
          <section className="scenario-card"><div className="section-heading"><p>Evidence access</p><span>INSPECTABLE</span></div><p className="muted">Every modeled metric preserves the scenario, frozen snapshot, evidence, assumption, transformation, model version, timestamps, confidence, freshness, and units.</p>{result && <details><summary>Simulation provenance</summary><pre>{JSON.stringify(result.provenance, null, 2)}</pre></details>}</section>
        </aside>
      </section>
    </main>
  );
}

function Results({ run }: { run: Run }) {
  const result = run.result;
  if (!result) return null;
  return <section className="scenario-card results-card"><div className="section-heading"><p>Baseline versus no-action</p><span>COMPLETED</span></div><div className="comparison-grid"><ResultMetric label="Baseline supply" value={result.baseline.total_supply} /><ResultMetric label="No-action supply" value={result.disrupted.total_supply} /><ResultMetric label="Peak shortfall" value={result.disrupted.shortfall} /><ResultMetric label="Cumulative shortfall" value={result.disrupted.cumulative_shortfall} /></div><h3>Disruption timeline</h3><div className="timeline-chart" aria-label="No-action shortfall timeline">{result.timeline.map((item) => <div key={item.step} title={`Day ${item.step + 1}: ${item.shortfall.value} ${item.shortfall.unit}`}><i style={{ height: `${Math.max(3, (item.shortfall.value / Math.max(result.baseline.total_demand.value, 1)) * 100)}%` }} /><span>{item.step + 1}</span></div>)}</div><h3>Affected routes and flows</h3><div className="result-table">{result.flows.filter((item) => item.affected).map((item) => <div key={`${item.route_id}-${item.supplier_id}-${item.grade_id}`}><strong>{item.route_canonical_id}</strong><span>{item.baseline_flow.value} → {item.disrupted_flow.value} {item.disrupted_flow.unit}</span></div>)}</div><h3>Refinery throughput impact</h3><div className="result-table">{result.refinery_throughput.map((item) => <div key={item.refinery_id}><strong>{item.refinery_canonical_id}</strong><span>{item.disrupted_throughput.value} throughput · {item.shortfall.value} shortfall {item.shortfall.unit}</span></div>)}</div><h3>Inventory trajectory</h3>{result.inventory_status === "UNKNOWN" ? <Notice tone="warning" title="UNKNOWN" text="No starting-inventory assumption was supplied. Sanjiv does not invent private inventory." /> : <Notice tone="assumption" title="ASSUMPTION-DEPENDENT INVENTORY" text="Trajectory is modeled only from the confirmed, expiring starting-inventory assumption." />}<h3>Deterministic uncertainty range</h3><p>{result.uncertainty.lower_bound.value} – {result.uncertainty.upper_bound.value} {result.uncertainty.central.unit}; central {result.uncertainty.central.value}. Bounded sensitivity, not a statistical probability.</p><div className="runtime-row"><strong>Measured simulation runtime</strong><span>{run.runtime_ms?.toFixed(2)} ms · “under 10 seconds” remains a target, not a stored benchmark claim.</span></div><details><summary>Physical invariant report</summary><pre>{JSON.stringify(result.invariants, null, 2)}</pre></details></section>;
}

function effect(disruptionType: DisruptionType, targetType: TargetType, requested: string, value: number) { return { disruption_type: disruptionType, target: { target_type: targetType, requested_identifier: requested, asset_id: null, canonical_id: null, display_name: null }, capacity_reduction: { value, unit: "percent" } }; }
function Status({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function Fact({ label, value }: { label: string; value: string }) { return <div className="fact"><span>{label}</span><strong>{value}</strong></div>; }
function Notice({ tone, title, text }: { tone: string; title: string; text: string }) { return <div className={`scenario-notice ${tone}`}><strong>{title}</strong><span>{text}</span></div>; }
function ResultMetric({ label, value }: { label: string; value: components["schemas"]["MetricEnvelope_float_"] }) { return <div><span>{label}</span><strong>{value.value}</strong><small>{value.unit} · {value.truth_class}</small></div>; }
function format(value: string) { return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(value)); }
function mutationHeaders() { return { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }; }
function message(reason: unknown) { return reason instanceof Error ? reason.message : "Scenario Lab request failed"; }
async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> { const response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init }); const body = (await response.json()) as { message?: string } | T; if (!response.ok) throw new Error("message" in (body as object) ? (body as { message?: string }).message ?? `Request failed (${response.status})` : `Request failed (${response.status})`); return body as T; }
