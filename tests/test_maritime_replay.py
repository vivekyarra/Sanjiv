import json
from pathlib import Path

import pytest
from maritime_helpers import REPLAY_MANIFEST
from sanjiv.contracts import DataMode
from sanjiv.maritime.adapters.replay import ReplayAISAdapter


async def _collect_ids(adapter: ReplayAISAdapter) -> list[str]:
    return [item.source_record_id async for item in adapter.stream()]


@pytest.mark.asyncio
async def test_replay_is_deterministic_and_schema_identical() -> None:
    first = await _collect_ids(ReplayAISAdapter(REPLAY_MANIFEST, speed=1000))
    second = await _collect_ids(ReplayAISAdapter(REPLAY_MANIFEST, speed=1000))
    assert first == second
    assert len(first) == 8
    sample = anext(ReplayAISAdapter(REPLAY_MANIFEST, speed=1000).stream())
    assert (await sample).mode is DataMode.REPLAY


def test_replay_rejects_checksum_tampering(tmp_path: Path) -> None:
    manifest = json.loads(REPLAY_MANIFEST.read_text(encoding="utf-8"))
    source_data = REPLAY_MANIFEST.parent / manifest["data_file"]
    (tmp_path / "messages.ndjson").write_bytes(source_data.read_bytes() + b"\n")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        ReplayAISAdapter(tmp_path / "manifest.json")
