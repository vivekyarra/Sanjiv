import pytest
from sanjiv.maritime.broker import OperationsBroker
from sanjiv.maritime.contracts import OperatingMode


@pytest.mark.asyncio
async def test_broker_reconnect_backlog_and_resynchronization() -> None:
    broker = OperationsBroker(history_size=2)
    await broker.publish("VESSEL_POSITION", OperatingMode.REPLAY, {"id": 1})
    await broker.publish("VESSEL_POSITION", OperatingMode.REPLAY, {"id": 2})
    assert [item.sequence for item in broker.since(1) or []] == [2]
    await broker.publish("VESSEL_POSITION", OperatingMode.REPLAY, {"id": 3})
    assert broker.since(0) is not None
    await broker.publish("VESSEL_POSITION", OperatingMode.REPLAY, {"id": 4})
    assert broker.since(1) is None


@pytest.mark.asyncio
async def test_slow_subscriber_receives_resync_instead_of_unbounded_queue() -> None:
    broker = OperationsBroker(subscriber_queue_size=1)
    async with broker.subscribe() as queue:
        await broker.publish("VESSEL_POSITION", OperatingMode.REPLAY, {"id": 1})
        await broker.publish("VESSEL_POSITION", OperatingMode.REPLAY, {"id": 2})
        assert (await queue.get()).event_type == "RESYNC_REQUIRED"
