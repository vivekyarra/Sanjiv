import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from sanjiv.contracts import (
    AuditEvent,
    DataMode,
    EvidenceRecord,
    MetricEnvelope,
    SourceRef,
    TruthClass,
)
from sanjiv.maritime.contracts import (
    Geofence,
    GeofenceEvent,
    OperatingModeTransition,
    QuarantinedAISMessage,
    ReplayRecording,
    SanctionsAssessment,
    SanctionsMatchStatus,
    VesselHistoryResponse,
    VesselOperationalView,
    VesselPosition,
    VesselTrackSegment,
)
from sanjiv.maritime.inference import assess_india_bound


class MaritimeRepository(Protocol):
    async def initialize(self, geofences: list[Geofence]) -> None: ...
    async def save_observation(
        self, evidence: EvidenceRecord, view: VesselOperationalView
    ) -> bool: ...
    async def save_geofence_event(self, event: GeofenceEvent) -> bool: ...
    async def save_transition(
        self, transition: OperatingModeTransition, audit: AuditEvent
    ) -> None: ...
    async def save_replay_recording(self, recording: ReplayRecording) -> None: ...
    async def quarantine(self, item: QuarantinedAISMessage) -> None: ...
    async def latest_views(self) -> list[VesselOperationalView]: ...
    async def history(self, vessel_id: UUID, limit: int) -> VesselHistoryResponse | None: ...
    async def transitions(self) -> list[OperatingModeTransition]: ...
    async def geofences(self) -> list[Geofence]: ...


class InMemoryMaritimeRepository:
    def __init__(self) -> None:
        self._geofences: list[Geofence] = []
        self._views: dict[UUID, VesselOperationalView] = {}
        self._positions: dict[UUID, list[VesselPosition]] = defaultdict(list)
        self._segments: dict[UUID, list[VesselTrackSegment]] = defaultdict(list)
        self._position_ids: set[UUID] = set()
        self._geofence_event_ids: set[UUID] = set()
        self._transitions: list[OperatingModeTransition] = []
        self.evidence: dict[UUID, EvidenceRecord] = {}
        self.geofence_events: list[GeofenceEvent] = []
        self.replay_recordings: dict[UUID, ReplayRecording] = {}
        self.quarantined: list[QuarantinedAISMessage] = []
        self.audit_events: list[AuditEvent] = []

    async def initialize(self, geofences: list[Geofence]) -> None:
        self._geofences = list(geofences)
        self.evidence.update(
            {_geofence_evidence(item).id: _geofence_evidence(item) for item in geofences}
        )

    async def save_observation(self, evidence: EvidenceRecord, view: VesselOperationalView) -> bool:
        position = view.position
        if position.id in self._position_ids:
            return False
        self._position_ids.add(position.id)
        self.evidence[evidence.id] = evidence
        positions = self._positions[position.vessel_id]
        if positions and positions[-1].source_timestamp < position.source_timestamp:
            self._segments[position.vessel_id].append(_segment(positions[-1], position))
        positions.append(position)
        positions.sort(key=lambda item: item.source_timestamp)
        current = self._views.get(position.vessel_id)
        latest_view = (
            current
            if current and current.position.source_timestamp > position.source_timestamp
            else view
        )
        self._views[position.vessel_id] = latest_view.model_copy(
            update={"recent_track": [(item.longitude, item.latitude) for item in positions[-50:]]}
        )
        return True

    async def save_geofence_event(self, event: GeofenceEvent) -> bool:
        if event.id in self._geofence_event_ids:
            return False
        self._geofence_event_ids.add(event.id)
        self.geofence_events.append(event)
        return True

    async def save_transition(self, transition: OperatingModeTransition, audit: AuditEvent) -> None:
        self._transitions.append(transition)
        self.audit_events.append(audit)

    async def save_replay_recording(self, recording: ReplayRecording) -> None:
        self.replay_recordings[recording.id] = recording

    async def quarantine(self, item: QuarantinedAISMessage) -> None:
        self.quarantined.append(item)

    async def latest_views(self) -> list[VesselOperationalView]:
        return sorted(self._views.values(), key=lambda item: item.position.mmsi)

    async def history(self, vessel_id: UUID, limit: int) -> VesselHistoryResponse | None:
        if vessel_id not in self._positions:
            return None
        return VesselHistoryResponse(
            vessel_id=vessel_id,
            positions=self._positions[vessel_id][-limit:],
            segments=self._segments[vessel_id][-max(0, limit - 1) :],
        )

    async def transitions(self) -> list[OperatingModeTransition]:
        return list(self._transitions)

    async def geofences(self) -> list[Geofence]:
        return list(self._geofences)


class PostgresMaritimeRepository(InMemoryMaritimeRepository):
    """PostgreSQL persistence plus an in-process current-state cache for low-latency map reads."""

    def __init__(self, database_url: str) -> None:
        super().__init__()
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)

    async def close(self) -> None:
        await self._engine.dispose()

    async def initialize(self, geofences: list[Geofence]) -> None:
        async with self._engine.begin() as connection:
            for item in geofences:
                evidence = _geofence_evidence(item)
                await connection.execute(text(_EVIDENCE_INSERT), _evidence_params(evidence))
                polygon = _polygon_wkt(item.coordinates[0])
                await connection.execute(
                    text(
                        """INSERT INTO geofences
                        (id, slug, name, kind, geometry, source_ref, effective_at, truth_class,
                         confidence, evidence_id, transformation, version, authoritative)
                        VALUES (:id, :slug, :name, :kind,
                                ST_GeomFromText(:polygon, 4326), :source_ref,
                                :effective_at, :truth_class, :confidence, :evidence_id,
                                :transformation, :version, :authoritative)
                        ON CONFLICT (slug) DO NOTHING"""
                    ),
                    {
                        "id": item.id,
                        "slug": item.slug,
                        "name": item.name,
                        "kind": item.kind,
                        "polygon": polygon,
                        "source_ref": item.source_ref,
                        "effective_at": item.effective_at,
                        "truth_class": item.truth_class,
                        "confidence": item.confidence,
                        "evidence_id": item.evidence_id,
                        "transformation": item.transformation,
                        "version": item.version,
                        "authoritative": item.authoritative,
                    },
                )
        await super().initialize(geofences)
        await self._hydrate_latest_views()

    async def save_observation(self, evidence: EvidenceRecord, view: VesselOperationalView) -> bool:
        position = view.position
        if position.id in self._position_ids:
            return False
        positions = self._positions[position.vessel_id]
        segment = (
            _segment(positions[-1], position)
            if positions and positions[-1].source_timestamp < position.source_timestamp
            else None
        )
        async with self._engine.begin() as connection:
            await connection.execute(text(_EVIDENCE_INSERT), _evidence_params(evidence))
            await connection.execute(
                text(
                    """INSERT INTO vessels (id, mmsi, imo, name, ship_type, sanctions_status,
                    created_at, updated_at) VALUES (:id, :mmsi, :imo, :name, :ship_type,
                    :sanctions_status, :created_at, :updated_at)
                    ON CONFLICT (mmsi) DO UPDATE SET imo=COALESCE(EXCLUDED.imo, vessels.imo),
                    name=COALESCE(EXCLUDED.name, vessels.name),
                    ship_type=COALESCE(EXCLUDED.ship_type, vessels.ship_type),
                    sanctions_status=EXCLUDED.sanctions_status,
                    updated_at=EXCLUDED.updated_at"""
                ),
                {
                    "id": position.vessel_id,
                    "mmsi": position.mmsi,
                    "imo": position.imo,
                    "name": position.vessel_name,
                    "ship_type": position.ship_type,
                    "sanctions_status": view.sanctions.status,
                    "created_at": position.computed_at,
                    "updated_at": position.computed_at,
                },
            )
            inserted = await connection.execute(text(_POSITION_INSERT), _position_params(position))
            if inserted.rowcount == 0:
                return False
            if segment:
                await connection.execute(text(_SEGMENT_INSERT), _segment_params(segment))
        return await super().save_observation(evidence, view)

    async def save_geofence_event(self, event: GeofenceEvent) -> bool:
        if event.id in self._geofence_event_ids:
            return False
        async with self._engine.begin() as connection:
            inserted = await connection.execute(
                text(
                    """INSERT INTO geofence_events
                    (id, vessel_id, geofence_id, position_id, event_type, occurred_at,
                     truth_class, confidence, evidence_ids, transformation)
                    VALUES (:id, :vessel_id, :geofence_id, :position_id, :event_type, :occurred_at,
                            :truth_class, :confidence, :evidence_ids, :transformation)
                    ON CONFLICT (id) DO NOTHING"""
                ),
                {**event.model_dump(), "evidence_ids": event.evidence_ids},
            )
            if inserted.rowcount == 0:
                return False
        return await super().save_geofence_event(event)

    async def save_transition(self, transition: OperatingModeTransition, audit: AuditEvent) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(text(_AUDIT_INSERT), audit.model_dump())
            await connection.execute(
                text(
                    """INSERT INTO operating_mode_transitions
                    (id, from_mode, to_mode, occurred_at, reason_code, explanation, automatic,
                     audit_event_id) VALUES (:id, :from_mode, :to_mode, :occurred_at, :reason_code,
                     :explanation, :automatic, :audit_event_id)"""
                ),
                transition.model_dump(),
            )
        await super().save_transition(transition, audit)

    async def save_replay_recording(self, recording: ReplayRecording) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """INSERT INTO replay_recordings
                    (id, dataset_id, manifest_version, classification, object_ref, checksum_sha256,
                     starts_at, ends_at, record_count, license)
                    VALUES (:id, :dataset_id, :manifest_version, :classification, :object_ref,
                            :checksum_sha256, :starts_at, :ends_at, :record_count, :license)
                    ON CONFLICT (id) DO NOTHING"""
                ),
                recording.model_dump(),
            )
        await super().save_replay_recording(recording)

    async def quarantine(self, item: QuarantinedAISMessage) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """INSERT INTO ais_quarantine
                    (id, source_id, source_record_id, fetched_at, reason_code, payload_hash)
                    VALUES (:id, :source_id, :source_record_id, :fetched_at, :reason_code,
                            :payload_hash) ON CONFLICT (id) DO NOTHING"""
                ),
                item.model_dump(),
            )
        await super().quarantine(item)

    async def history(self, vessel_id: UUID, limit: int) -> VesselHistoryResponse | None:
        async with self._engine.connect() as connection:
            result = await connection.execute(
                text(_POSITION_SELECT + " WHERE p.vessel_id = :vessel_id " + _POSITION_ORDER_LIMIT),
                {"vessel_id": vessel_id, "limit": limit},
            )
            positions = [_position_from_row(row) for row in reversed(result.mappings().all())]
        if not positions:
            return None
        return VesselHistoryResponse(
            vessel_id=vessel_id,
            positions=positions,
            segments=[
                _segment(start, end) for start, end in zip(positions, positions[1:], strict=False)
            ],
        )

    async def transitions(self) -> list[OperatingModeTransition]:
        async with self._engine.connect() as connection:
            result = await connection.execute(
                text("SELECT * FROM operating_mode_transitions ORDER BY occurred_at")
            )
            return [OperatingModeTransition.model_validate(dict(row)) for row in result.mappings()]

    async def _hydrate_latest_views(self) -> None:
        async with self._engine.connect() as connection:
            result = await connection.execute(
                text(
                    _POSITION_SELECT
                    + " WHERE (p.vessel_id, p.source_timestamp) IN "
                    + "(SELECT vessel_id, MAX(source_timestamp) FROM vessel_positions "
                    + "GROUP BY vessel_id) ORDER BY v.mmsi"
                )
            )
            latest = [_position_from_row(row) for row in result.mappings()]
        for position in latest:
            history = await self.history(position.vessel_id, 50)
            track = (
                [(item.longitude, item.latitude) for item in history.positions]
                if history
                else [(position.longitude, position.latitude)]
            )
            self._position_ids.add(position.id)
            self._positions[position.vessel_id] = history.positions if history else [position]
            self._segments[position.vessel_id] = history.segments if history else []
            self._views[position.vessel_id] = VesselOperationalView(
                position=position,
                recent_track=track,
                india_bound=assess_india_bound(position, computed_at=position.computed_at),
                sanctions=SanctionsAssessment(
                    status=SanctionsMatchStatus.NOT_SCREENED,
                    truth_class=TruthClass.INFERRED,
                    confidence=0.0,
                    evidence_ids=[],
                    explanation=(
                        "No sanctions dataset is loaded; this vessel has not been screened."
                    ),
                ),
            )


def _segment(start: VesselPosition, end: VesselPosition) -> VesselTrackSegment:
    computed_at = max(start.computed_at, end.computed_at)
    distance = _haversine_nm(start.latitude, start.longitude, end.latitude, end.longitude)
    segment_id = uuid5(NAMESPACE_URL, f"urn:sanjiv:track:{start.id}:{end.id}")
    evidence_ids = list(dict.fromkeys([*start.evidence_ids, *end.evidence_ids]))
    return VesselTrackSegment(
        id=segment_id,
        vessel_id=end.vessel_id,
        start_position_id=start.id,
        end_position_id=end.id,
        start_at=start.source_timestamp,
        end_at=end.source_timestamp,
        coordinates=[(start.longitude, start.latitude), (end.longitude, end.latitude)],
        distance_nm=MetricEnvelope[float](
            value=round(distance, 4),
            unit="nautical_mile",
            truth_class=TruthClass.DERIVED,
            confidence=min(start.confidence, end.confidence),
            evidence_ids=evidence_ids,
            source_refs=[
                SourceRef(source_id=start.source_id, record_id=start.source_record_id),
                SourceRef(source_id=end.source_id, record_id=end.source_record_id),
            ],
            effective_at=end.source_timestamp,
            fetched_at=end.fetched_at,
            computed_at=computed_at,
            freshness_status=end.freshness_status,
            transformation="haversine-track-distance-1.0.0",
            model_version="haversine-track-distance-1.0.0",
        ),
    )


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_nm = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_nm * math.asin(math.sqrt(a))


def _polygon_wkt(ring: Sequence[tuple[float, float]]) -> str:
    return "POLYGON((" + ",".join(f"{lon} {lat}" for lon, lat in ring) + "))"


def _geofence_evidence(item: Geofence) -> EvidenceRecord:
    raw = json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    return EvidenceRecord(
        id=item.evidence_id,
        source_id="SANJIV_GEOFENCE_FIXTURE",
        source_record_id=item.slug,
        dataset="Sanjiv Phase 1 approximate development geofences",
        dataset_version=item.version,
        effective_at=item.effective_at,
        fetched_at=item.effective_at,
        mode=DataMode.FIXTURE,
        truth_class=item.truth_class,
        raw_payload_hash=hashlib.sha256(raw).hexdigest(),
        raw_object_ref="data/fixtures/maritime/geofences.geojson",
        transformation=item.transformation,
        confidence=item.confidence,
        license="Project development fixture; non-authoritative boundaries",
    )


def _evidence_params(item: EvidenceRecord) -> dict[str, object]:
    payload = item.model_dump()
    payload["source_url"] = str(item.source_url) if item.source_url else None
    return payload


def _position_params(item: VesselPosition) -> dict[str, object]:
    return item.model_dump()


def _position_from_row(row: Any) -> VesselPosition:
    return VesselPosition(
        id=row["id"],
        vessel_id=row["vessel_id"],
        mmsi=row["mmsi"],
        imo=row["imo"],
        vessel_name=row["vessel_name"],
        ship_type=row["ship_type"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        speed_knots=row["speed_knots"],
        course_degrees=row["course_degrees"],
        heading_degrees=row["heading_degrees"],
        navigation_status=row["navigation_status"],
        destination_raw=row["destination_raw"],
        source_timestamp=row["source_timestamp"],
        fetched_at=row["fetched_at"],
        computed_at=row["computed_at"],
        source_id=row["source_id"],
        source_record_id=row["source_record_id"],
        mode=row["mode"],
        truth_class=row["truth_class"],
        freshness_status=row["freshness_status"],
        confidence=float(row["confidence"]),
        evidence_ids=list(row["evidence_ids"]),
        transformation=row["transformation"],
        adapter_version=row["adapter_version"],
    )


def _segment_params(item: VesselTrackSegment) -> dict[str, object]:
    return {
        "id": item.id,
        "vessel_id": item.vessel_id,
        "start_position_id": item.start_position_id,
        "end_position_id": item.end_position_id,
        "start_at": item.start_at,
        "end_at": item.end_at,
        "line": "LINESTRING(" + ",".join(f"{lon} {lat}" for lon, lat in item.coordinates) + ")",
        "distance_nm": item.distance_nm.value,
        "evidence_ids": item.distance_nm.evidence_ids,
        "transformation": item.distance_nm.transformation,
    }


_EVIDENCE_INSERT = """INSERT INTO evidence_records
(id, source_id, source_record_id, source_url, dataset, dataset_version, effective_at,
 fetched_at, mode, truth_class, raw_payload_hash, raw_object_ref, transformation,
 confidence, license, parent_evidence_ids)
VALUES (:id, :source_id, :source_record_id, :source_url, :dataset, :dataset_version,
 :effective_at, :fetched_at, :mode, :truth_class, :raw_payload_hash, :raw_object_ref,
 :transformation, :confidence, :license, :parent_evidence_ids)
ON CONFLICT (source_id, source_record_id, dataset_version) DO NOTHING"""

_POSITION_INSERT = """INSERT INTO vessel_positions
(id, vessel_id, source_message_id, source_timestamp, fetched_at, computed_at, position,
 latitude, longitude, speed_knots, course_degrees, heading_degrees, navigation_status,
 destination_raw, source_id, mode, truth_class, freshness_status, confidence, evidence_ids,
 transformation, adapter_version)
VALUES (:id, :vessel_id, :source_record_id, :source_timestamp, :fetched_at, :computed_at,
 ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326), :latitude, :longitude,
 :speed_knots, :course_degrees, :heading_degrees, :navigation_status, :destination_raw,
 :source_id, :mode, :truth_class, :freshness_status, :confidence, :evidence_ids,
 :transformation, :adapter_version) ON CONFLICT (id, source_timestamp) DO NOTHING"""

_POSITION_SELECT = """SELECT p.id, p.vessel_id, v.mmsi, v.imo, v.name AS vessel_name,
v.ship_type, p.source_timestamp, p.fetched_at, p.computed_at, p.latitude, p.longitude,
p.speed_knots, p.course_degrees, p.heading_degrees, p.navigation_status,
p.destination_raw, p.source_id, p.source_message_id AS source_record_id, p.mode,
p.truth_class, p.freshness_status, p.confidence, p.evidence_ids, p.transformation,
p.adapter_version FROM vessel_positions p JOIN vessels v ON v.id = p.vessel_id"""

_POSITION_ORDER_LIMIT = " ORDER BY p.source_timestamp DESC LIMIT :limit"

_SEGMENT_INSERT = """INSERT INTO vessel_track_segments
(id, vessel_id, start_position_id, end_position_id, start_at, end_at, path,
 distance_nm, evidence_ids, transformation)
VALUES (:id, :vessel_id, :start_position_id, :end_position_id, :start_at, :end_at,
 ST_GeomFromText(:line, 4326), :distance_nm, :evidence_ids, :transformation)
ON CONFLICT (id) DO NOTHING"""

_AUDIT_INSERT = """INSERT INTO audit_events
(id, occurred_at, actor_id, actor_type, action, resource_type, resource_id, before_hash,
 after_hash, reason, correlation_id, causation_id, outcome)
VALUES (:id, :occurred_at, :actor_id, :actor_type, :action, :resource_type, :resource_id,
 :before_hash, :after_hash, :reason, :correlation_id, :causation_id, :outcome)"""
