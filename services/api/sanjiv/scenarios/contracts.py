from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sanjiv.contracts import Assumption, AuditEvent


class ScenarioSourceMode(StrEnum):
    STRUCTURED_FORM = "STRUCTURED_FORM"
    DETERMINISTIC_TEXT = "DETERMINISTIC_TEXT"
    LLM_PROVIDER = "LLM_PROVIDER"


class ScenarioCompileMode(StrEnum):
    AUTO = "AUTO"
    STRUCTURED_FORM = "STRUCTURED_FORM"
    DETERMINISTIC_TEXT = "DETERMINISTIC_TEXT"
    OPTIONAL_PROVIDER = "OPTIONAL_PROVIDER"


class ScenarioLifecycle(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    CONFIRMED = "CONFIRMED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DisruptionTargetType(StrEnum):
    CHOKEPOINT = "CHOKEPOINT"
    ROUTE = "ROUTE"
    SUPPLIER = "SUPPLIER"
    PORT = "PORT"
    REFINERY = "REFINERY"


class DisruptionType(StrEnum):
    CHOKEPOINT_CLOSURE = "CHOKEPOINT_CLOSURE"
    CHOKEPOINT_CAPACITY_REDUCTION = "CHOKEPOINT_CAPACITY_REDUCTION"
    MARITIME_ROUTE_CAPACITY_REDUCTION = "MARITIME_ROUTE_CAPACITY_REDUCTION"
    SUPPLIER_VOLUME_REDUCTION = "SUPPLIER_VOLUME_REDUCTION"
    PORT_DISRUPTION = "PORT_DISRUPTION"
    REFINERY_THROUGHPUT_DISRUPTION = "REFINERY_THROUGHPUT_DISRUPTION"


class DurationUnit(StrEnum):
    HOUR = "hour"
    DAY = "day"


class DurationQuantity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float = Field(allow_inf_nan=False)
    unit: DurationUnit

    @property
    def days(self) -> float:
        return self.value / 24 if self.unit is DurationUnit.HOUR else self.value


class PercentageQuantity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float = Field(allow_inf_nan=False)
    unit: Literal["percent"] = "percent"


class TwinSnapshotReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    version: str = Field(min_length=1, max_length=100)
    effective_at: datetime


class DisruptionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_type: DisruptionTargetType
    requested_identifier: str = Field(min_length=1, max_length=200)
    asset_id: UUID | None = None
    canonical_id: str | None = None
    display_name: str | None = None


class DisruptionEffect(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    disruption_type: DisruptionType
    target: DisruptionTarget
    capacity_reduction: PercentageQuantity


class ScenarioDefault(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=200)
    value: Any
    unit: str = Field(min_length=1, max_length=50)
    rationale: str = Field(min_length=1, max_length=1000)
    requires_confirmation: bool = True


class ScenarioParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    commodity: Literal["CRUDE_OIL", "LPG"] = "CRUDE_OIL"
    disruption_start: datetime
    disruption_duration: DurationQuantity
    simulation_horizon: DurationQuantity
    disruptions: list[DisruptionEffect] = Field(min_length=1, max_length=4)
    assumptions: list[Assumption] = Field(default_factory=list, max_length=20)


class StructuredScenarioInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_name: str = Field(min_length=1, max_length=200)
    twin_snapshot_id: UUID
    commodity: Literal["CRUDE_OIL", "LPG"] = "CRUDE_OIL"
    disruption_start: datetime | None = None
    disruption_duration: DurationQuantity
    simulation_horizon: DurationQuantity | None = None
    disruptions: list[DisruptionEffect] = Field(min_length=1, max_length=4)
    assumptions: list[Assumption] = Field(default_factory=list, max_length=20)


class CompileScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: ScenarioCompileMode = ScenarioCompileMode.AUTO
    twin_snapshot_id: UUID
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    structured: StructuredScenarioInput | None = None

    @model_validator(mode="after")
    def validate_input_path(self) -> Self:
        if self.mode is ScenarioCompileMode.STRUCTURED_FORM and self.structured is None:
            raise ValueError("structured mode requires structured input")
        if (
            self.mode
            in {
                ScenarioCompileMode.DETERMINISTIC_TEXT,
                ScenarioCompileMode.OPTIONAL_PROVIDER,
            }
            and self.text is None
        ):
            raise ValueError("text mode requires text input")
        if self.structured and self.structured.twin_snapshot_id != self.twin_snapshot_id:
            raise ValueError("structured and selected twin snapshot IDs must match")
        if self.text is None and self.structured is None:
            raise ValueError("text or structured input is required")
        return self


class InterpreterStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TIMED_OUT = "TIMED_OUT"


class InterpretationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: InterpreterStatus
    source_mode: ScenarioSourceMode | None = None
    provider: str = Field(min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    timeout_seconds: float = Field(gt=0, le=60)
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = Field(default=None, max_length=100)
    error_message: str | None = Field(default=None, max_length=1000)


class ScenarioCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: UUID
    lifecycle: ScenarioLifecycle = ScenarioLifecycle.DRAFT
    scenario_name: str = Field(min_length=1, max_length=200)
    original_text: str | None = Field(default=None, max_length=2000)
    source_mode: ScenarioSourceMode
    interpreter_provider: str = Field(min_length=1, max_length=100)
    interpreter_model: str | None = Field(default=None, max_length=200)
    twin_snapshot: TwinSnapshotReference
    parameters: ScenarioParameters
    defaults: list[ScenarioDefault] = Field(default_factory=list)
    created_at: datetime
    scenario_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def create(
        cls,
        *,
        scenario_name: str,
        original_text: str | None,
        source_mode: ScenarioSourceMode,
        interpreter_provider: str,
        interpreter_model: str | None,
        twin_snapshot: TwinSnapshotReference,
        parameters: ScenarioParameters,
        defaults: list[ScenarioDefault],
        created_at: datetime,
    ) -> Self:
        fingerprint = scenario_fingerprint(twin_snapshot, parameters, defaults)
        return cls(
            scenario_id=uuid5(NAMESPACE_URL, f"urn:sanjiv:scenario:{fingerprint}"),
            scenario_name=scenario_name,
            original_text=original_text,
            source_mode=source_mode,
            interpreter_provider=interpreter_provider,
            interpreter_model=interpreter_model,
            twin_snapshot=twin_snapshot,
            parameters=parameters,
            defaults=defaults,
            created_at=created_at,
            scenario_fingerprint=fingerprint,
        )

    @model_validator(mode="after")
    def validate_fingerprint(self) -> Self:
        expected = scenario_fingerprint(self.twin_snapshot, self.parameters, self.defaults)
        if self.scenario_fingerprint != expected:
            raise ValueError("scenario fingerprint does not match canonical execution inputs")
        expected_id = uuid5(NAMESPACE_URL, f"urn:sanjiv:scenario:{expected}")
        if self.scenario_id != expected_id:
            raise ValueError("scenario_id does not match scenario fingerprint")
        return self


class ValidationSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    DEFAULT_REQUIRES_CONFIRMATION = "DEFAULT_REQUIRES_CONFIRMATION"
    ASSUMPTION_REQUIRES_CONFIRMATION = "ASSUMPTION_REQUIRES_CONFIRMATION"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: ValidationSeverity
    code: str = Field(min_length=1, max_length=100)
    field: str = Field(min_length=1, max_length=300)
    message: str = Field(min_length=1, max_length=1000)


class ResolvedDisruptionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_identifier: str
    target_type: DisruptionTargetType
    asset_id: UUID
    canonical_id: str
    display_name: str


class ScenarioValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_id: UUID
    scenario_id: UUID
    scenario_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    twin_snapshot: TwinSnapshotReference
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    resolved_targets: list[ResolvedDisruptionTarget] = Field(default_factory=list)
    defaults: list[ScenarioDefault] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    validated_at: datetime
    validator_version: str = Field(min_length=1, max_length=100)


class ConfirmScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    confirming_identity: str = Field(min_length=1, max_length=200)


class ConfirmedScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: UUID
    scenario_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    twin_snapshot: TwinSnapshotReference
    candidate: ScenarioCandidate
    validation: ScenarioValidationResult
    confirmed_by: str = Field(min_length=1, max_length=200)
    confirmed_at: datetime
    lifecycle: Literal[ScenarioLifecycle.CONFIRMED] = ScenarioLifecycle.CONFIRMED
    audit_event: AuditEvent


class ScenarioCompileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: ScenarioCandidate | None = None
    interpretation: InterpretationResult
    validation: ScenarioValidationResult | None = None
    fallback_available: bool = True


class SupportedScenarioType(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    disruption_type: DisruptionType
    target_type: DisruptionTargetType
    supports_full_closure: bool
    description: str


class ScenarioFormMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    supported_types: list[SupportedScenarioType]
    duration_units: list[DurationUnit]
    duration_min_hours: float
    duration_max_days: float
    reduction_unit: Literal["percent"] = "percent"
    maximum_compound_effects: int
    interpreter_label: str
    llm_provider_available: bool


def scenario_fingerprint(
    twin_snapshot: TwinSnapshotReference,
    parameters: ScenarioParameters,
    defaults: list[ScenarioDefault],
) -> str:
    payload = {
        "twin_snapshot": twin_snapshot.model_dump(mode="json"),
        "parameters": parameters.model_dump(mode="json"),
        "defaults": [item.model_dump(mode="json") for item in defaults],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
