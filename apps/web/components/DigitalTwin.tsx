"use client";

import type { components } from "@sanjiv/contracts";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

type Snapshot = components["schemas"]["TwinSnapshot"];
type Node = components["schemas"]["TwinNode"];
type Route = components["schemas"]["TwinRoute"];
type Grade = components["schemas"]["CrudeGrade"];

const API_URL = process.env.NEXT_PUBLIC_SANJIV_API_URL ?? "http://localhost:8000";
const lanes = ["SUPPLIER", "LOAD_PORT", "CHOKEPOINT", "INDIAN_PORT", "REFINERY", "RESERVE_SITE"] as const;

export function DigitalTwin() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [selection, setSelection] = useState<{ kind: "node" | "route" | "grade"; id: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const response = await fetch(`${API_URL}/api/v1/twin/snapshots/current`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Digital twin unavailable (${response.status})`);
    const data = (await response.json()) as Snapshot;
    setSnapshot(data);
    setSelection((current) => current ?? { kind: "node", id: data.nodes[0]?.id ?? "" });
    setError(null);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Digital twin unavailable"));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const selectedNode = selection?.kind === "node" ? snapshot?.nodes.find((item) => item.id === selection.id) : undefined;
  const selectedRoute = selection?.kind === "route" ? snapshot?.routes.find((item) => item.id === selection.id) : undefined;
  const selectedGrade = selection?.kind === "grade" ? snapshot?.grades.find((item) => item.id === selection.id) : undefined;
  const nodeById = useMemo(() => new Map(snapshot?.nodes.map((item) => [item.id, item]) ?? []), [snapshot]);

  return (
    <main className="twin-shell">
      <div className="assumption-banner" role="alert">
        ASSUMPTION-DRIVEN REFERENCE TWIN — NOT LIVE OPERATIONAL DATA
      </div>
      <header className="command-header twin-header">
        <div className="brand-lockup">
          <span className="brand-mark">S</span>
          <div><h1>Sanjiv</h1><p>India&apos;s Energy Resilience Command Center · Digital Twin</p><small>Keep India&apos;s energy moving.</small></div>
        </div>
        <nav className="product-nav" aria-label="Product modules"><Link href="/">Live Maritime Watch</Link><Link className="active" href="/digital-twin">Digital Twin</Link><Link href="/scenario-lab">Scenario Lab</Link><Link href="/response-planner">Response Planner</Link><Link href="/strategic-reserve">Strategic Reserve</Link><Link href="/risk-intelligence">Risk Intelligence</Link></nav>
      </header>

      {error && <div className="operational-warning" role="alert">{error}</div>}
      <section className="metric-strip" aria-label="Twin metrics">
        <Metric label="Snapshot version" value={snapshot?.version ?? "—"} detail={snapshot?.fingerprint.slice(0, 12) ?? "NO SNAPSHOT"} />
        <Metric label="Network assets" value={snapshot?.nodes.length ?? "—"} detail="EVIDENCE LINKED" />
        <Metric label="Routes / grades" value={snapshot ? `${snapshot.routes.length} / ${snapshot.grades.length}` : "—"} detail="CANONICAL IDS" />
        <Metric label="Mass balance" value={snapshot?.mass_balance.conserved ? "CONSERVED" : "BLOCKED"} detail={snapshot ? `${snapshot.mass_balance.absolute_residual.value} ${snapshot.mass_balance.absolute_residual.unit}` : "NO DATA"} />
      </section>

      <section className="twin-grid">
        <div className="network-board" aria-label="India energy network graph">
          <div className="section-heading"><p>Operational network</p><span>{snapshot?.created_at ? `FROZEN ${formatDate(snapshot.created_at)}` : "LOADING"}</span></div>
          <div className="network-lanes">
            {lanes.map((kind) => (
              <section className="network-lane" key={kind} aria-label={kind.replaceAll("_", " ")}>
                <h2>{kind.replaceAll("_", " ")}</h2>
                {snapshot?.nodes.filter((item) => item.kind === kind).map((node) => (
                  <button key={node.id} className={selectedNode?.id === node.id ? "asset-chip selected" : "asset-chip"} onClick={() => setSelection({ kind: "node", id: node.id })}>
                    <strong>{node.name}</strong><small>{node.canonical_id}</small>
                  </button>
                ))}
              </section>
            ))}
          </div>
          <div className="route-strip">
            <h2>Maritime and logistics edges</h2>
            <div>{snapshot?.routes.map((route) => <button key={route.id} className={selectedRoute?.id === route.id ? "route-chip selected" : "route-chip"} onClick={() => setSelection({ kind: "route", id: route.id })}>{nodeById.get(route.origin_id)?.name} → {nodeById.get(route.destination_id)?.name}</button>)}</div>
          </div>
          <div className="grade-strip">
            <h2>Crude-grade catalogue</h2>
            <div>{snapshot?.grades.map((grade) => <button key={grade.id} className={selectedGrade?.id === grade.id ? "grade-chip selected" : "grade-chip"} onClick={() => setSelection({ kind: "grade", id: grade.id })}>{grade.name}</button>)}</div>
          </div>
        </div>

        <aside className="twin-inspector" aria-label="Digital twin inspector">
          {snapshot && selectedNode && <NodeInspector node={selectedNode} snapshot={snapshot} />}
          {snapshot && selectedRoute && <RouteInspector route={selectedRoute} snapshot={snapshot} nodeById={nodeById} />}
          {snapshot && selectedGrade && <GradeInspector grade={selectedGrade} snapshot={snapshot} nodeById={nodeById} />}
          {!snapshot && <div className="side-card">Loading immutable snapshot…</div>}
        </aside>
      </section>
    </main>
  );
}

function NodeInspector({ node, snapshot }: { node: Node; snapshot: Snapshot }) {
  return <Inspector title="Asset" name={node.name} canonicalId={node.canonical_id} snapshot={snapshot} evidenceIds={node.evidence_ids ?? []} assumptionIds={node.assumption_ids ?? []}>
    <Row term="Kind" value={node.kind} /><Row term="Country" value={node.country_code} /><Row term="Coordinates" value={`${node.latitude.toFixed(2)}, ${node.longitude.toFixed(2)}`} />
    <MetricRows label="Capacity" metric={node.capacity} /><MetricRows label="Baseline supply" metric={node.baseline_supply} /><MetricRows label="Baseline demand" metric={node.baseline_demand} />
    {node.kind === "RESERVE_SITE" && <Row term="Current fill" value="UNKNOWN — no confidential fill assumed" />}
  </Inspector>;
}

function RouteInspector({ route, snapshot, nodeById }: { route: Route; snapshot: Snapshot; nodeById: Map<string, Node> }) {
  return <Inspector title="Route edge" name={`${nodeById.get(route.origin_id)?.name} → ${nodeById.get(route.destination_id)?.name}`} canonicalId={route.canonical_id} snapshot={snapshot} evidenceIds={route.evidence_ids ?? []} assumptionIds={route.assumption_ids ?? []}>
    <MetricRows label="Capacity" metric={route.capacity} /><MetricRows label="Transit time" metric={route.transit_time} /><MetricRows label="Distance" metric={route.distance} /><Row term="Available" value={route.available ? "YES" : "NO"} />
  </Inspector>;
}

function GradeInspector({ grade, snapshot, nodeById }: { grade: Grade; snapshot: Snapshot; nodeById: Map<string, Node> }) {
  const compatibility = snapshot.compatibility.filter((item) => item.grade_id === grade.id);
  return <Inspector title="Crude grade" name={grade.name} canonicalId={grade.canonical_id} snapshot={snapshot} evidenceIds={grade.evidence_ids ?? []} assumptionIds={grade.assumption_ids ?? []}>
    <MetricRows label="API gravity" metric={grade.api_gravity} /><MetricRows label="Sulfur" metric={grade.sulfur_pct} /><Row term="Sanctions" value={grade.sanctions_state} />
    <h3>Refinery compatibility</h3>{compatibility.map((item) => <div className="compatibility-card" key={item.refinery_id}><strong>{nodeById.get(item.refinery_id)?.name}</strong><span>{item.classification} · {(item.score.value * 100).toFixed(1)}%</span><small>{item.explanation}</small></div>)}
  </Inspector>;
}

function Inspector({ title, name, canonicalId, snapshot, evidenceIds, assumptionIds, children }: { title: string; name: string; canonicalId: string; snapshot: Snapshot; evidenceIds: string[]; assumptionIds: string[]; children: React.ReactNode }) {
  const evidence = snapshot.evidence_records.filter((item) => item.id && evidenceIds.includes(item.id));
  const assumptions = (snapshot.assumptions ?? []).filter((item) => item.id && assumptionIds.includes(item.id));
  return <section className="side-card inspector-card"><div className="section-heading"><p>{title}</p><span>SNAPSHOT {snapshot.version}</span></div><h2>{name}</h2><p className="canonical-id">{canonicalId}</p><dl>{children}</dl><h3>Input source</h3>{evidence.map((item) => <div className="evidence-card" key={item.id}><strong>{item.source_id} · {item.truth_class}</strong><span>{item.dataset} ({item.dataset_version})</span><span>Effective {formatDate(item.effective_at)} · fetched {formatDate(item.fetched_at)}</span><span>Evidence {item.id}</span><a href={item.source_url ?? "#"} rel="noreferrer" target="_blank">Official source reference</a></div>)}<h3>Assumptions</h3>{assumptions.length ? assumptions.map((item) => <div className="assumption-card" key={item.id}><strong>{item.key}</strong><span>{item.rationale}</span><span>Expires {item.expires_at ? formatDate(item.expires_at) : "not set"}</span></div>) : <p className="source-note">No assumption record is linked to this item.</p>}</section>;
}

function MetricRows({ label, metric }: { label: string; metric?: components["schemas"]["MetricEnvelope_float_"] | null }) {
  if (!metric) return null;
  return <><Row term={label} value={`${metric.value} ${metric.unit}`} /><Row term={`${label} truth`} value={`${metric.truth_class} · ${(metric.confidence * 100).toFixed(0)}%`} /></>;
}
function Metric({ label, value, detail }: { label: string; value: string | number; detail: string }) { return <div className="metric"><p>{label}</p><strong>{value}</strong><span>{detail}</span></div>; }
function Row({ term, value }: { term: string; value: string }) { return <div><dt>{term}</dt><dd>{value}</dd></div>; }
function formatDate(value: string) { return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeZone: "Asia/Kolkata" }).format(new Date(value)); }
