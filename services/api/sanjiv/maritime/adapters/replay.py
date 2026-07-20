import asyncio
import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from sanjiv.contracts import DataMode, FreshnessStatus, SourceHealthRecord, SourceState
from sanjiv.maritime.contracts import (
    AdapterHealth,
    ConnectionState,
    RawAISMessage,
    ReplayFixtureMessage,
    ReplayManifest,
    ReplayRecording,
)


class ReplayAISAdapter:
    def __init__(self, manifest_path: Path, *, speed: float = 20.0, loop: bool = False) -> None:
        if speed <= 0:
            raise ValueError("replay speed must be positive")
        self._manifest_path = manifest_path
        self._speed = speed
        self._loop = loop
        self._manifest, self._messages = self._load()
        self._last_success: datetime | None = None
        self._count = 0

    @property
    def source_id(self) -> str:
        return self._manifest.source_id

    @property
    def mode(self) -> DataMode:
        return DataMode.REPLAY

    @property
    def recording(self) -> ReplayRecording:
        from uuid import NAMESPACE_URL, uuid5

        return ReplayRecording(
            id=uuid5(NAMESPACE_URL, self._manifest.dataset_id),
            dataset_id=self._manifest.dataset_id,
            manifest_version=self._manifest.schema_version,
            classification=self._manifest.classification,
            object_ref=str(self._manifest_path),
            checksum_sha256=self._manifest.checksum_sha256,
            starts_at=self._manifest.starts_at,
            ends_at=self._manifest.ends_at,
            record_count=self._manifest.record_count,
            license=self._manifest.license,
        )

    async def health(self) -> AdapterHealth:
        now = datetime.now(UTC)
        return AdapterHealth(
            source_health=SourceHealthRecord(
                source_id=self.source_id,
                state=SourceState.READY,
                checked_at=now,
                last_success_at=self._last_success,
                expected_cadence_seconds=60,
                stale_after_seconds=300,
                message_count=self._count,
                mode=DataMode.REPLAY,
                freshness_status=FreshnessStatus.REPLAY,
            ),
            connection_state=ConnectionState.CONNECTED,
            detail=f"Replay: {self._manifest.classification}; {self._manifest.description}",
        )

    def stream(self) -> AsyncIterator[RawAISMessage]:
        return self._stream()

    async def _stream(self) -> AsyncIterator[RawAISMessage]:
        while True:
            previous: datetime | None = None
            for item in self._messages:
                source_timestamp = item.source_timestamp.astimezone(UTC)
                if previous is not None:
                    delay = max(0.0, (source_timestamp - previous).total_seconds() / self._speed)
                    if delay:
                        await asyncio.sleep(delay)
                fetched_at = datetime.now(UTC)
                self._last_success = fetched_at
                self._count += 1
                yield RawAISMessage(
                    source_id=self.source_id,
                    source_record_id=item.source_record_id,
                    source_timestamp=source_timestamp,
                    fetched_at=fetched_at,
                    mode=DataMode.REPLAY,
                    payload=item.payload,
                    dataset=self._manifest.dataset_id,
                    dataset_version=self._manifest.schema_version,
                    license=self._manifest.license,
                    source_url=None,
                )
                previous = source_timestamp
            if not self._loop:
                return

    def _load(self) -> tuple[ReplayManifest, list[ReplayFixtureMessage]]:
        manifest = ReplayManifest.model_validate_json(
            self._manifest_path.read_text(encoding="utf-8")
        )
        data_path = self._manifest_path.parent / manifest.data_file
        raw = data_path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        if checksum != manifest.checksum_sha256:
            raise ValueError("replay data checksum does not match manifest")
        messages = [
            ReplayFixtureMessage.model_validate_json(line)
            for line in raw.decode("utf-8").splitlines()
            if line.strip()
        ]
        if len(messages) != manifest.record_count:
            raise ValueError("replay record count does not match manifest")
        timestamps = [item.source_timestamp for item in messages]
        if timestamps != sorted(timestamps):
            raise ValueError("replay messages must be ordered by source timestamp")
        return manifest, messages
