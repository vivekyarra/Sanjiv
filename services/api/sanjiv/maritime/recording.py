import json
from datetime import UTC, datetime
from pathlib import Path

from sanjiv.maritime.contracts import RawAISMessage


class RawBatchRecorder:
    """Secret-free local spool for deterministic conversion into replay datasets."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def record(self, raw: RawAISMessage) -> Path:
        self._directory.mkdir(parents=True, exist_ok=True)
        day = datetime.now(UTC).strftime("%Y%m%d")
        target = self._directory / f"{raw.source_id.lower()}-{day}.ndjson"
        serialized = {
            "source_id": raw.source_id,
            "source_record_id": raw.source_record_id,
            "source_timestamp": raw.source_timestamp.isoformat().replace("+00:00", "Z"),
            "fetched_at": raw.fetched_at.isoformat().replace("+00:00", "Z"),
            "dataset": raw.dataset,
            "dataset_version": raw.dataset_version,
            "mode": raw.mode,
            "payload": raw.payload,
        }
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(serialized, sort_keys=True, separators=(",", ":")) + "\n")
        return target
