from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from maritime_helpers import build_service, raw_position
from sanjiv.contracts import DataMode, FreshnessStatus, SourceHealthRecord, SourceState
from sanjiv.maritime.contracts import AdapterHealth, ConnectionState, OperatingMode, RawAISMessage
from sanjiv.maritime.repository import InMemoryMaritimeRepository


class FailingLiveAdapter:
    source_id = "FAILING_LIVE"
    mode = DataMode.LIVE

    def stream(self) -> AsyncIterator[RawAISMessage]:
        return self._stream()

    async def _stream(self) -> AsyncIterator[RawAISMessage]:
        raise ConnectionError("provider unavailable")
        yield  # pragma: no cover

    async def health(self) -> AdapterHealth:
        raise AssertionError("failed live adapter must not remain active")


@pytest.mark.asyncio
async def test_live_failure_transitions_to_replay_and_remains_demonstrable(tmp_path: Path) -> None:
    service = build_service(tmp_path, live_adapter=FailingLiveAdapter())
    await service.repository.initialize(service._geofence_engine._geofences)
    await service.initialize()
    await service.run()

    snapshot = await service.snapshot()
    transitions = await service.repository.transitions()
    assert snapshot.operating_mode is OperatingMode.REPLAY
    assert snapshot.source_health.mode is DataMode.REPLAY
    assert snapshot.source_health.freshness_status is FreshnessStatus.REPLAY
    assert len(snapshot.vessels) == 3
    assert [item.to_mode for item in transitions] == [OperatingMode.REPLAY]
    assert transitions[0].reason_code == "AUTOMATIC_REPLAY_FALLBACK"
    repository = service.repository
    assert isinstance(repository, InMemoryMaritimeRepository)
    assert len(repository.audit_events) == len(transitions)


@pytest.mark.asyncio
async def test_malformed_message_is_quarantined_without_raw_payload(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    malformed = raw_position(payload_override={"bad": "payload"})
    await service.process(malformed)
    repository = service.repository
    assert isinstance(repository, InMemoryMaritimeRepository)
    assert len(repository.quarantined) == 1
    assert repository.quarantined[0].payload_hash
    assert not hasattr(repository.quarantined[0], "payload")


def test_source_health_contract_does_not_require_credentials() -> None:
    health = SourceHealthRecord(
        source_id="REPLAY",
        state=SourceState.READY,
        checked_at=raw_position().fetched_at,
        mode=DataMode.REPLAY,
        freshness_status=FreshnessStatus.REPLAY,
    )
    assert (
        AdapterHealth(
            source_health=health,
            connection_state=ConnectionState.CONNECTED,
            detail="synthetic fixture",
        ).source_health.error_count
        == 0
    )
