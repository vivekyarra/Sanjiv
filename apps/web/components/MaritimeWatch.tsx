"use client";

import type { components } from "@sanjiv/contracts";
import Link from "next/link";
import maplibregl, {
  type GeoJSONSource,
  type Map as MapLibreMap,
  type StyleSpecification,
} from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  connectionLabel,
  hasStaleVessels,
  modePresentation,
  reconnectDelay,
  type SocketState,
} from "../lib/maritimeState";

type Snapshot = components["schemas"]["OperationsSnapshot"];
type Vessel = components["schemas"]["VesselOperationalView"];

const API_URL = process.env.NEXT_PUBLIC_SANJIV_API_URL ?? "http://localhost:8000";
const WS_URL = process.env.NEXT_PUBLIC_SANJIV_WS_URL ?? "ws://localhost:8000";

const mapStyle: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#07130f" } },
    { id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.34, "raster-saturation": -0.75 } },
  ],
};

const emptyCollection = { type: "FeatureCollection" as const, features: [] };

export function MaritimeWatch() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempt = useRef(0);
  const cursor = useRef(0);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [socketState, setSocketState] = useState<SocketState>("CONNECTING");
  const [error, setError] = useState<string | null>(null);

  const loadSnapshot = useCallback(async () => {
    const response = await fetch(`${API_URL}/api/v1/operations/snapshot`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Snapshot unavailable (${response.status})`);
    const data = (await response.json()) as Snapshot;
    cursor.current = data.cursor;
    setSnapshot(data);
    setError(null);
    return data;
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadSnapshot().catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Snapshot unavailable");
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadSnapshot]);

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | null = null;
    const connect = () => {
      if (disposed) return;
      setSocketState("CONNECTING");
      socket = new WebSocket(`${WS_URL}/ws/v1/operations?after=${cursor.current}`);
      socket.onopen = () => {
        reconnectAttempt.current = 0;
        setSocketState("CONNECTED");
      };
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data as string) as {
            event_type: string;
            sequence?: number;
          };
          if (event.sequence) cursor.current = event.sequence;
          if (
            ["VESSEL_POSITION", "GEOFENCE_EVENT", "MODE_TRANSITION", "RESYNC_REQUIRED"].includes(
              event.event_type,
            )
          ) {
            void loadSnapshot();
          }
        } catch {
          setError("A malformed WebSocket update was rejected; resynchronizing.");
          void loadSnapshot();
        }
      };
      socket.onerror = () => setSocketState("ERROR");
      socket.onclose = () => {
        if (disposed) return;
        setSocketState("DISCONNECTED");
        const delay = reconnectDelay(reconnectAttempt.current++);
        reconnectTimer.current = setTimeout(connect, delay);
      };
    };
    connect();
    return () => {
      disposed = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      socket?.close();
    };
  }, [loadSnapshot]);

  const mapData = useMemo(() => toMapData(snapshot, selectedId), [snapshot, selectedId]);
  const mapDataRef = useRef(mapData);

  useEffect(() => {
    mapDataRef.current = mapData;
  }, [mapData]);

  useEffect(() => {
    if (!mapContainer.current || map.current) return;
    const instance = new maplibregl.Map({
      container: mapContainer.current,
      style: mapStyle,
      center: [71.5, 20],
      zoom: 3.25,
      minZoom: 2,
      maxZoom: 12,
      attributionControl: { compact: true },
    });
    instance.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
    instance.on("load", () => {
      instance.addSource("geofences", { type: "geojson", data: emptyCollection });
      instance.addSource("tracks", { type: "geojson", data: emptyCollection });
      instance.addSource("vessels", { type: "geojson", data: emptyCollection });
      instance.addLayer({
        id: "geofence-fill",
        type: "fill",
        source: "geofences",
        paint: { "fill-color": ["match", ["get", "kind"], "PORT", "#38bdf8", "#f59e0b"], "fill-opacity": 0.13 },
      });
      instance.addLayer({
        id: "geofence-line",
        type: "line",
        source: "geofences",
        paint: { "line-color": ["match", ["get", "kind"], "PORT", "#38bdf8", "#f59e0b"], "line-width": 1.4, "line-dasharray": [2, 2] },
      });
      instance.addLayer({ id: "tracks-line", type: "line", source: "tracks", paint: { "line-color": "#7dd3fc", "line-width": 2, "line-opacity": 0.72 } });
      instance.addLayer({
        id: "vessels-circle",
        type: "circle",
        source: "vessels",
        paint: {
          "circle-radius": ["case", ["boolean", ["get", "selected"], false], 9, 6],
          "circle-color": ["match", ["get", "freshness"], "STALE", "#94a3b8", "UNAVAILABLE", "#64748b", "REPLAY", "#fbbf24", "#34d399"],
          "circle-stroke-color": "#ecfdf5",
          "circle-stroke-width": 1.5,
        },
      });
      instance.on("click", "vessels-circle", (event) => {
        const id = event.features?.[0]?.properties?.id as string | undefined;
        if (id) setSelectedId(id);
      });
      updateSources(instance, mapDataRef.current);
    });
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    if (map.current?.isStyleLoaded()) updateSources(map.current, mapData);
  }, [mapData]);

  const selected = snapshot?.vessels.find((item) => item.position.vessel_id === selectedId) ?? snapshot?.vessels[0];
  const mode = modePresentation(snapshot?.operating_mode ?? "DEGRADED");
  const stale = hasStaleVessels(snapshot?.vessels.map((item) => item.position.freshness_status) ?? []);

  return (
    <main className="watch-shell">
      {snapshot?.operating_mode === "REPLAY" && (
        <div className="replay-banner" role="alert">
          <strong>REPLAY — NOT LIVE DATA</strong>
          <span>{snapshot.mode_explanation}</span>
        </div>
      )}
      <header className="command-header">
        <div className="brand-lockup">
          <span className="brand-mark">S</span>
          <div>
            <h1>Sanjiv</h1>
            <p>India’s Energy Resilience Command Center · Live Maritime Watch</p>
            <small>Keep India’s energy moving.</small>
          </div>
        </div>
        <div className="status-cluster">
          <Link className="module-link" href="/digital-twin">Digital Twin</Link>
          <Link className="module-link" href="/scenario-lab">Scenario Lab</Link>
          <Link className="module-link" href="/response-planner">Response Planner</Link>
          <Link className="module-link" href="/strategic-reserve">Strategic Reserve</Link>
          <Link className="module-link" href="/risk-intelligence">Risk Intelligence</Link>
          <span className={`mode-chip ${mode.tone}`}>{mode.label}</span>
          <span className={`connection-chip ${socketState.toLowerCase()}`}><i />{connectionLabel(socketState)}</span>
          <time>{snapshot ? formatTime(snapshot.as_of) : "Waiting for source"}</time>
        </div>
      </header>

      <section className="metric-strip" aria-label="Operational metrics">
        <Metric label="Vessels monitored" value={snapshot?.vessel_count?.value ?? "—"} truth={snapshot?.vessel_count?.truth_class} />
        <Metric label="Messages / minute" value={snapshot?.messages_per_minute?.value ?? "—"} truth={snapshot?.messages_per_minute?.truth_class} />
        <Metric label="Source" value={snapshot?.source_health.source_id ?? "Connecting"} truth={snapshot?.source_health.mode} />
        <Metric label="Freshness" value={snapshot?.source_health.freshness_status ?? "UNAVAILABLE"} truth={snapshot?.source_health.state} />
      </section>

      {(error || stale || snapshot?.operating_mode === "DEGRADED") && (
        <div className="operational-warning" role="status">
          {error ?? (stale ? "One or more vessel records are stale. Inspect source timestamps before use." : snapshot?.mode_explanation)}
        </div>
      )}

      <section className="watch-grid">
        <div className="map-panel">
          <div ref={mapContainer} className="map-canvas" aria-label="Maritime vessel and geofence map" />
          {!snapshot && <div className="map-state">Loading operational picture…</div>}
          {snapshot && snapshot.vessels.length === 0 && <div className="map-state">No validated vessel positions are available.</div>}
          <div className="map-legend"><span><i className="live-dot" />Live/current</span><span><i className="replay-dot" />Replay</span><span><i className="stale-dot" />Stale</span></div>
        </div>

        <aside className="watch-sidebar">
          <section className="side-card source-card">
            <div className="section-heading"><p>Source health</p><span>{snapshot?.source_health.state ?? "CONNECTING"}</span></div>
            <dl>
              <Row term="Mode" value={snapshot?.source_health.mode ?? "—"} />
              <Row term="Last source update" value={selected ? formatTime(selected.position.source_timestamp) : "—"} />
              <Row term="Fetched" value={selected ? formatTime(selected.position.fetched_at) : "—"} />
              <Row term="Errors" value={String(snapshot?.source_health.error_count ?? 0)} />
            </dl>
            <p className="source-note">AIS coverage is incomplete and does not reveal cargo ownership or charter availability.</p>
          </section>

          <section className="side-card vessel-list">
            <div className="section-heading"><p>Validated vessels</p><span>{snapshot?.vessels.length ?? 0}</span></div>
            <div className="vessel-scroll">
              {snapshot?.vessels.map((item) => (
                <button key={item.position.vessel_id} className={item.position.vessel_id === selected?.position.vessel_id ? "vessel-row selected" : "vessel-row"} onClick={() => setSelectedId(item.position.vessel_id)}>
                  <span><strong>{item.position.vessel_name ?? "Unnamed vessel"}</strong><small>MMSI {item.position.mmsi}</small></span>
                  <em className={item.position.freshness_status.toLowerCase()}>{item.position.freshness_status}</em>
                </button>
              ))}
            </div>
          </section>

          {selected && <VesselDetails vessel={selected} />}
        </aside>
      </section>
    </main>
  );
}

function Metric({ label, value, truth }: { label: string; value: string | number; truth?: string }) {
  return <div className="metric"><p>{label}</p><strong>{value}</strong><span>{truth ?? "NO DATA"}</span></div>;
}

function Row({ term, value }: { term: string; value: string }) {
  return <div><dt>{term}</dt><dd>{value}</dd></div>;
}

function VesselDetails({ vessel }: { vessel: Vessel }) {
  const p = vessel.position;
  return (
    <section className="side-card vessel-detail">
      <div className="section-heading"><p>Selected vessel</p><span>{p.truth_class}</span></div>
      <h2>{p.vessel_name ?? "Unnamed vessel"}</h2>
      <p className="coordinates">{p.latitude.toFixed(4)}°, {p.longitude.toFixed(4)}°</p>
      <dl>
        <Row term="MMSI" value={p.mmsi} />
        <Row term="Speed" value={p.speed_knots == null ? "Not reported" : `${p.speed_knots.toFixed(1)} kn`} />
        <Row term="Course" value={p.course_degrees == null ? "Not reported" : `${p.course_degrees.toFixed(0)}°`} />
        <Row term="Destination (reported)" value={p.destination_raw ?? "Not reported"} />
        <Row term="India-bound likelihood" value={`${(vessel.india_bound.likelihood.value * 100).toFixed(0)}% · ${vessel.india_bound.likelihood.truth_class}`} />
        <Row term="Sanctions" value={`${vessel.sanctions.status} · ${vessel.sanctions.truth_class}`} />
      </dl>
      <div className="provenance-box">
        <strong>Evidence & provenance</strong>
        <span>Source: {p.source_id}</span>
        <span>Evidence: {p.evidence_ids[0]}</span>
        <span>Transform: {p.transformation}</span>
        <span>Adapter: {p.adapter_version}</span>
        <span>Confidence: {(p.confidence * 100).toFixed(0)}%</span>
      </div>
      <p className="source-note">{vessel.india_bound.disclaimer}</p>
    </section>
  );
}

function toMapData(snapshot: Snapshot | null, selectedId: string | null) {
  if (!snapshot) return { vessels: emptyCollection, tracks: emptyCollection, geofences: emptyCollection };
  return {
    vessels: { type: "FeatureCollection" as const, features: snapshot.vessels.map((item) => ({ type: "Feature" as const, geometry: { type: "Point" as const, coordinates: [item.position.longitude, item.position.latitude] }, properties: { id: item.position.vessel_id, freshness: item.position.freshness_status, selected: item.position.vessel_id === selectedId } })) },
    tracks: { type: "FeatureCollection" as const, features: snapshot.vessels.filter((item) => item.recent_track.length > 1).map((item) => ({ type: "Feature" as const, geometry: { type: "LineString" as const, coordinates: item.recent_track }, properties: { vessel_id: item.position.vessel_id } })) },
    geofences: { type: "FeatureCollection" as const, features: snapshot.geofences.map((item) => ({ type: "Feature" as const, geometry: { type: "Polygon" as const, coordinates: item.coordinates }, properties: { id: item.id, name: item.name, kind: item.kind, truth_class: item.truth_class, authoritative: item.authoritative } })) },
  };
}

function updateSources(instance: MapLibreMap, data: ReturnType<typeof toMapData>) {
  (instance.getSource("vessels") as GeoJSONSource | undefined)?.setData(data.vessels);
  (instance.getSource("tracks") as GeoJSONSource | undefined)?.setData(data.tracks);
  (instance.getSource("geofences") as GeoJSONSource | undefined)?.setData(data.geofences);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "medium", timeZone: "Asia/Kolkata" }).format(new Date(value));
}
