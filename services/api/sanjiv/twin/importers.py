from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter

from sanjiv.contracts import DataMode, TruthClass


class ReferenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=100)
    record_id: str = Field(min_length=1, max_length=200)
    dataset: str = Field(min_length=1, max_length=200)
    dataset_version: str = Field(min_length=1, max_length=100)
    effective_at: datetime
    fetched_at: datetime
    mode: DataMode
    truth_class: TruthClass
    confidence: float = Field(ge=0, le=1)
    source_url: AnyHttpUrl
    license: str = Field(min_length=1, max_length=500)
    redistribution_rights: str = Field(min_length=1, max_length=500)
    transformation: str = Field(min_length=1, max_length=250)
    expires_at: datetime | None = None
    payload: dict[str, Any]


class ReferenceDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    version: str
    records: list[ReferenceRecord] = Field(min_length=1)


class ReferenceDataImporter(Protocol):
    source_id: str

    def import_records(self, dataset: ReferenceDataset) -> list[ReferenceRecord]: ...


class _SourceImporter:
    source_id: str
    allowed_sections: frozenset[str]

    def import_records(self, dataset: ReferenceDataset) -> list[ReferenceRecord]:
        records = [item for item in dataset.records if item.source_id == self.source_id]
        if not records:
            raise ValueError(f"dataset contains no {self.source_id} records")
        for record in records:
            sections = set(record.payload)
            if not sections <= self.allowed_sections:
                unknown = ", ".join(sorted(sections - self.allowed_sections))
                raise ValueError(f"{self.source_id} record has unsupported sections: {unknown}")
            if record.truth_class is TruthClass.OBSERVED and record.mode is DataMode.FIXTURE:
                raise ValueError("fixture records cannot be presented as observed")
        return records


class PPACImporter(_SourceImporter):
    source_id = "PPAC"
    allowed_sections = frozenset({"nodes"})


class ISPRLImporter(_SourceImporter):
    source_id = "ISPRL"
    allowed_sections = frozenset({"nodes"})


class UNComtradeImporter(_SourceImporter):
    source_id = "UN_COMTRADE"
    allowed_sections = frozenset({"nodes", "allocations"})


class RepositoryFixtureImporter(_SourceImporter):
    source_id = "SANJIV_TWIN_FIXTURE"
    allowed_sections = frozenset({"nodes", "routes", "grades"})


def load_reference_dataset(path: Path) -> ReferenceDataset:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return TypeAdapter(ReferenceDataset).validate_python(payload)
