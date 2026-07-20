from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sanjiv.contracts import Assumption
from sanjiv.scenarios.contracts import (
    CompileScenarioRequest,
    ConfirmScenarioRequest,
    DisruptionEffect,
    DisruptionTarget,
    DisruptionTargetType,
    DisruptionType,
    DurationQuantity,
    DurationUnit,
    PercentageQuantity,
    ScenarioCompileMode,
    StructuredScenarioInput,
    TwinSnapshotReference,
    scenario_fingerprint,
)
from sanjiv.scenarios.repository import InMemoryScenarioRepository
from sanjiv.scenarios.service import ScenarioDomainError, ScenarioService
from sanjiv.scenarios.validator import validate_scenario
from sanjiv.twin.service import build_default_twin_service
from scenario_helpers import NOW, memory_service


def _input(
    *,
    target: str = "Strait of Hormuz",
    target_type: DisruptionTargetType = DisruptionTargetType.CHOKEPOINT,
    disruption_type: DisruptionType = DisruptionType.CHOKEPOINT_CLOSURE,
    duration: float = 14,
    reduction: float = 100,
    assumptions: list[Assumption] | None = None,
    duplicate: bool = False,
) -> StructuredScenarioInput:
    snapshot = build_default_twin_service().current()
    effect = DisruptionEffect(
        disruption_type=disruption_type,
        target=DisruptionTarget(target_type=target_type, requested_identifier=target),
        capacity_reduction=PercentageQuantity(value=reduction),
    )
    return StructuredScenarioInput(
        scenario_name="validation case",
        twin_snapshot_id=snapshot.snapshot_id,
        disruption_start=NOW,
        disruption_duration=DurationQuantity(value=duration, unit=DurationUnit.DAY),
        disruptions=[effect, effect] if duplicate else [effect],
        assumptions=assumptions or [],
    )


async def _compile(structured: StructuredScenarioInput, key: str):
    service = memory_service()
    result = await service.compile(
        CompileScenarioRequest(
            mode=ScenarioCompileMode.STRUCTURED_FORM,
            twin_snapshot_id=structured.twin_snapshot_id,
            structured=structured,
        ),
        idempotency_key=key,
        now=NOW,
    )
    assert result.candidate is not None and result.validation is not None
    return service, result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("structured", "code"),
    [
        (_input(target="unknown chokepoint"), "UNKNOWN_TARGET"),
        (
            _input(
                target="unknown route",
                target_type=DisruptionTargetType.ROUTE,
                disruption_type=DisruptionType.MARITIME_ROUTE_CAPACITY_REDUCTION,
                reduction=50,
            ),
            "UNKNOWN_TARGET",
        ),
        (_input(duration=0), "INVALID_DURATION"),
        (_input(reduction=101), "INVALID_PERCENTAGE"),
        (_input(reduction=50), "INCONSISTENT_CLOSURE"),
        (_input(duplicate=True), "DUPLICATE_EFFECT"),
    ],
)
async def test_blocking_validation_cases(structured: StructuredScenarioInput, code: str) -> None:
    _service, result = await _compile(structured, f"invalid-{code}")
    assert not result.validation.valid
    assert any(item.code == code for item in result.validation.issues)


@pytest.mark.asyncio
async def test_conflicting_compound_effects_are_refused() -> None:
    structured = _input()
    second = structured.disruptions[0].model_copy(
        update={"disruption_type": DisruptionType.CHOKEPOINT_CAPACITY_REDUCTION}
    )
    structured = structured.model_copy(update={"disruptions": [*structured.disruptions, second]})
    _service, result = await _compile(structured, "conflict")
    assert any(item.code == "CONFLICTING_EFFECTS" for item in result.validation.issues)


@pytest.mark.asyncio
async def test_expired_assumption_is_surfaced() -> None:
    expired = Assumption(
        key="scenario.expired",
        value=1,
        unit="scenario_effects",
        rationale="test",
        source_gap="test",
        owner="test",
        entered_at=NOW - timedelta(days=3),
        effective_at=NOW - timedelta(days=2),
        expires_at=NOW - timedelta(days=1),
    )
    _service, result = await _compile(_input(assumptions=[expired]), "expired")
    assert any(item.code == "EXPIRED_ASSUMPTION" for item in result.validation.issues)
    assert not result.validation.valid


@pytest.mark.asyncio
async def test_missing_and_stale_snapshot_are_typed_validation_failures() -> None:
    _service, result = await _compile(_input(), "snapshot-validation")
    candidate = result.candidate
    missing = validate_scenario(candidate, None, now=NOW)
    assert any(item.code == "TWIN_SNAPSHOT_MISSING" for item in missing.issues)
    stale_ref = candidate.twin_snapshot.model_copy(update={"fingerprint": "0" * 64})
    stale = candidate.model_copy(update={"twin_snapshot": stale_ref})
    validation = validate_scenario(stale, build_default_twin_service().current(), now=NOW)
    assert any(item.code == "TWIN_SNAPSHOT_STALE" for item in validation.issues)


@pytest.mark.asyncio
async def test_fingerprint_is_stable_and_changes_after_execution_input_edit() -> None:
    _service, first = await _compile(_input(), "fingerprint-one")
    _service, second = await _compile(_input(), "fingerprint-two")
    assert first.candidate.scenario_fingerprint == second.candidate.scenario_fingerprint
    parameters = first.candidate.parameters.model_copy(
        update={"disruption_duration": DurationQuantity(value=15, unit=DurationUnit.DAY)}
    )
    changed = scenario_fingerprint(
        first.candidate.twin_snapshot, parameters, first.candidate.defaults
    )
    assert changed != first.candidate.scenario_fingerprint


@pytest.mark.asyncio
async def test_confirmation_is_server_enforced_audited_and_idempotent() -> None:
    service, result = await _compile(_input(), "confirm-compile")
    assert result.candidate is not None
    request = ConfirmScenarioRequest(confirming_identity="local-demo")
    first = await service.confirm(
        result.candidate.scenario_id,
        request,
        idempotency_key="confirm-idempotent",
        now=NOW,
    )
    second = await service.confirm(
        result.candidate.scenario_id,
        request,
        idempotency_key="confirm-idempotent",
        now=NOW + timedelta(seconds=1),
    )
    assert first == second
    assert first.twin_snapshot.fingerprint == result.candidate.twin_snapshot.fingerprint
    assert first.audit_event.action == "SCENARIO_CONFIRMED"
    assert await service.repository.audits(first.scenario_id) == [first.audit_event]


@pytest.mark.asyncio
async def test_unvalidated_and_invalid_scenarios_cannot_be_confirmed() -> None:
    snapshot = build_default_twin_service().current()
    repository = InMemoryScenarioRepository()
    service = ScenarioService(twin_service=build_default_twin_service(), repository=repository)
    _compiled_service, result = await _compile(_input(), "candidate-source")
    await repository.save_candidate(result.candidate)
    with pytest.raises(ScenarioDomainError, match="deterministic validation"):
        await service.confirm(
            result.candidate.scenario_id,
            ConfirmScenarioRequest(confirming_identity="test"),
            idempotency_key="unvalidated-confirm",
        )

    invalid_service, invalid = await _compile(_input(target="unknown"), "invalid-confirm")
    with pytest.raises(ScenarioDomainError, match="blocking validation"):
        await invalid_service.confirm(
            invalid.candidate.scenario_id,
            ConfirmScenarioRequest(confirming_identity="test"),
            idempotency_key="invalid-confirm-key",
        )
    assert snapshot.snapshot_id == result.candidate.twin_snapshot.snapshot_id


def test_snapshot_reference_requires_fingerprint_shape() -> None:
    snapshot = build_default_twin_service().current()
    with pytest.raises(ValueError):
        TwinSnapshotReference(
            snapshot_id=uuid4(),
            fingerprint="bad",
            version=snapshot.version,
            effective_at=datetime.now(UTC),
        )
