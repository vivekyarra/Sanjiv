import asyncio
import hashlib
import json
from collections import deque
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sanjiv.contracts import (
    AuditEvent,
    AuditOutcome,
    DataMode,
    FreshnessStatus,
    MetricEnvelope,
    SourceRef,
    TruthClass,
)
from sanjiv.maritime.adapters.base import AISSourceAdapter
from sanjiv.maritime.adapters.replay import ReplayAISAdapter
from sanjiv.maritime.broker import OperationsBroker
from sanjiv.maritime.contracts import (
    ConnectionState,
    OperatingMode,
    OperatingModeTransition,
    OperationsSnapshot,
    QuarantinedAISMessage,
    RawAISMessage,
    VesselHistoryResponse,
    VesselOperationalView,
)
from sanjiv.maritime.geofences import GeofenceEngine
from sanjiv.maritime.inference import assess_india_bound
from sanjiv.maritime.normalization import normalize_ais_position
from sanjiv.maritime.recording import RawBatchRecorder
from sanjiv.maritime.repository import MaritimeRepository
from sanjiv.maritime.sanctions import SanctionsMatcher


class MaritimeWatchService:
    def __init__(
        self,
        *,
        repository: MaritimeRepository,
        geofence_engine: GeofenceEngine,
        live_adapter: AISSourceAdapter | None,
        replay_adapter: ReplayAISAdapter,
        recorder: RawBatchRecorder,
        broker: OperationsBroker | None = None,
        sanctions_matcher: SanctionsMatcher | None = None,
        stale_after_seconds: int = 300,
    ) -> None:
        self.repository = repository
        self.broker = broker or OperationsBroker()
        self._geofence_engine = geofence_engine
        self._live_adapter = live_adapter
        self._replay_adapter = replay_adapter
        self._active_adapter: AISSourceAdapter = replay_adapter
        self._recorder = recorder
        self._sanctions = sanctions_matcher or SanctionsMatcher()
        self._stale_after_seconds = stale_after_seconds
        self._mode = OperatingMode.DEGRADED
        self._mode_explanation = "Maritime source initialization is pending."
        self._connection = ConnectionState.CONNECTING
        self._task: asyncio.Task[None] | None = None
        self._processed_at: deque[datetime] = deque()

    async def initialize(self) -> None:
        await self.repository.save_replay_recording(self._replay_adapter.recording)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run(), name="maritime-watch-ingestion")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def run(self) -> None:
        if self._live_adapter is None:
            await self._transition(
                OperatingMode.REPLAY,
                reason_code="AISSTREAM_NOT_CONFIGURED",
                explanation=(
                    "Live AIS is unavailable because no credential is configured. "
                    "Synthetic replay is active."
                ),
                automatic=True,
            )
            await self._consume(self._replay_adapter)
            return

        try:
            self._active_adapter = self._live_adapter
            self._connection = ConnectionState.CONNECTING
            async for raw in self._live_adapter.stream():
                await self.process(raw)
            raise ConnectionError("live AIS stream ended")
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._transition(
                OperatingMode.DEGRADED,
                reason_code="AISSTREAM_FAILURE",
                explanation=(
                    "Live AIS failed after bounded retries. Preparing deterministic fallback."
                ),
                automatic=True,
            )
            await self._transition(
                OperatingMode.REPLAY,
                reason_code="AUTOMATIC_REPLAY_FALLBACK",
                explanation=(
                    "Synthetic replay is active because the live AIS provider is unavailable."
                ),
                automatic=True,
            )
            await self._consume(self._replay_adapter)

    async def _consume(self, adapter: AISSourceAdapter) -> None:
        self._active_adapter = adapter
        self._connection = ConnectionState.CONNECTED
        async for raw in adapter.stream():
            await self.process(raw)

    async def process(self, raw: RawAISMessage) -> None:
        if raw.mode is DataMode.LIVE:
            self._recorder.record(raw)
        try:
            observation = normalize_ais_position(raw, stale_after_seconds=self._stale_after_seconds)
        except Exception as exc:
            payload = json.dumps(raw.payload, sort_keys=True, default=str).encode()
            item = QuarantinedAISMessage(
                id=uuid5(
                    NAMESPACE_URL, f"urn:sanjiv:quarantine:{raw.source_id}:{raw.source_record_id}"
                ),
                source_id=raw.source_id,
                source_record_id=raw.source_record_id,
                fetched_at=raw.fetched_at,
                reason_code=type(exc).__name__.upper(),
                payload_hash=hashlib.sha256(payload).hexdigest(),
            )
            await self.repository.quarantine(item)
            await self.broker.publish(
                "ERROR",
                self._mode,
                {"code": "AIS_MESSAGE_QUARANTINED", "record_id": raw.source_record_id},
            )
            return

        position = observation.position
        if raw.mode is DataMode.LIVE and self._mode is not OperatingMode.LIVE:
            await self._transition(
                OperatingMode.LIVE,
                reason_code="AISSTREAM_VALIDATED_MESSAGE",
                explanation="A validated live AISStream position was received.",
                automatic=True,
            )
        computed_at = position.computed_at
        view = VesselOperationalView(
            position=position,
            recent_track=[(position.longitude, position.latitude)],
            india_bound=assess_india_bound(position, computed_at=computed_at),
            sanctions=self._sanctions.assess(position),
        )
        if not await self.repository.save_observation(observation.evidence, view):
            return
        self._processed_at.append(datetime.now(UTC))
        self._prune_rate_window()
        await self.broker.publish("VESSEL_POSITION", self._mode, view.model_dump(mode="json"))
        for event in self._geofence_engine.evaluate(position):
            if await self.repository.save_geofence_event(event):
                await self.broker.publish(
                    "GEOFENCE_EVENT", self._mode, event.model_dump(mode="json")
                )

    async def _transition(
        self,
        to_mode: OperatingMode,
        *,
        reason_code: str,
        explanation: str,
        automatic: bool,
    ) -> None:
        if to_mode is self._mode:
            self._mode_explanation = explanation
            self._connection = (
                ConnectionState.CONNECTED
                if to_mode in (OperatingMode.LIVE, OperatingMode.REPLAY)
                else ConnectionState.DEGRADED
            )
            return
        now = datetime.now(UTC)
        transition_id = uuid4()
        audit_id = uuid4()
        transition = OperatingModeTransition(
            id=transition_id,
            from_mode=self._mode,
            to_mode=to_mode,
            occurred_at=now,
            reason_code=reason_code,
            explanation=explanation,
            automatic=automatic,
            audit_event_id=audit_id,
        )
        serialized = json.dumps(transition.model_dump(mode="json"), sort_keys=True).encode()
        audit = AuditEvent(
            id=audit_id,
            occurred_at=now,
            actor_id="maritime-watch-service",
            actor_type="SERVICE",
            action="maritime.operating_mode.transitioned",
            resource_type="operating_mode",
            resource_id=str(transition_id),
            after_hash=hashlib.sha256(serialized).hexdigest(),
            reason=explanation,
            correlation_id=transition_id,
            outcome=AuditOutcome.SUCCEEDED,
        )
        self._mode = to_mode
        self._mode_explanation = explanation
        self._connection = (
            ConnectionState.CONNECTED
            if to_mode in (OperatingMode.LIVE, OperatingMode.REPLAY)
            else ConnectionState.DEGRADED
        )
        await self.repository.save_transition(transition, audit)
        await self.broker.publish("MODE_TRANSITION", self._mode, transition.model_dump(mode="json"))

    async def snapshot(self) -> OperationsSnapshot:
        now = datetime.now(UTC)
        views = await self.repository.latest_views()
        health = await self._active_adapter.health()
        transitions = await self.repository.transitions()
        count_metric: MetricEnvelope[int] | None = None
        rate_metric: MetricEnvelope[float] | None = None
        if views:
            evidence_ids = list(
                dict.fromkeys(
                    evidence_id for item in views for evidence_id in item.position.evidence_ids
                )
            )
            source_refs = [
                SourceRef(
                    source_id=item.position.source_id, record_id=item.position.source_record_id
                )
                for item in views
            ]
            effective_at = max(item.position.source_timestamp for item in views)
            fetched_at = max(item.position.fetched_at for item in views)
            freshness = (
                FreshnessStatus.REPLAY
                if self._mode is OperatingMode.REPLAY
                else _worst_freshness(views)
            )
            common = {
                "truth_class": TruthClass.DERIVED,
                "confidence": min(item.position.confidence for item in views),
                "evidence_ids": evidence_ids,
                "source_refs": source_refs,
                "effective_at": effective_at,
                "fetched_at": fetched_at,
                "computed_at": now,
                "freshness_status": freshness,
            }
            count_metric = MetricEnvelope[int](
                value=len(views),
                unit="vessel",
                transformation="current-vessel-count-1.0.0",
                model_version="maritime-watch-1.0.0",
                **common,
            )
            self._prune_rate_window()
            rate_metric = MetricEnvelope[float](
                value=float(len(self._processed_at)),
                unit="message_per_minute",
                transformation="rolling-message-rate-1.0.0",
                model_version="maritime-watch-1.0.0",
                **common,
            )
        return OperationsSnapshot(
            cursor=self.broker.cursor,
            as_of=now,
            operating_mode=self._mode,
            mode_explanation=self._mode_explanation,
            connection_state=self._connection,
            source_health=health.source_health,
            vessel_count=count_metric,
            messages_per_minute=rate_metric,
            vessels=views,
            geofences=await self.repository.geofences(),
            latest_transition=transitions[-1] if transitions else None,
        )

    async def history(self, vessel_id: UUID, limit: int = 100) -> VesselHistoryResponse | None:
        return await self.repository.history(vessel_id, limit)

    async def vessel(self, vessel_id: UUID) -> VesselOperationalView | None:
        return next(
            (
                item
                for item in await self.repository.latest_views()
                if item.position.vessel_id == vessel_id
            ),
            None,
        )

    def _prune_rate_window(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(minutes=1)
        while self._processed_at and self._processed_at[0] < cutoff:
            self._processed_at.popleft()


def _worst_freshness(views: list[VesselOperationalView]) -> FreshnessStatus:
    statuses = {item.position.freshness_status for item in views}
    for candidate in (
        FreshnessStatus.UNAVAILABLE,
        FreshnessStatus.STALE,
        FreshnessStatus.CURRENT,
        FreshnessStatus.RECENT,
        FreshnessStatus.LIVE,
    ):
        if candidate in statuses:
            return candidate
    return FreshnessStatus.UNAVAILABLE
