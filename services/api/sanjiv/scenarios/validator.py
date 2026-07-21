from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sanjiv.contracts import AssumptionStatus
from sanjiv.scenarios.contracts import (
    DisruptionEffect,
    DisruptionTarget,
    DisruptionTargetType,
    DisruptionType,
    ResolvedDisruptionTarget,
    ScenarioCandidate,
    ScenarioValidationResult,
    ValidationIssue,
    ValidationSeverity,
)
from sanjiv.twin.contracts import AssetKind, TwinNode, TwinSnapshot

VALIDATOR_VERSION = "scenario-validator-1.0.0"
MAX_DURATION_DAYS = 90.0

_EXPECTED_TARGETS = {
    DisruptionType.CHOKEPOINT_CLOSURE: DisruptionTargetType.CHOKEPOINT,
    DisruptionType.CHOKEPOINT_CAPACITY_REDUCTION: DisruptionTargetType.CHOKEPOINT,
    DisruptionType.MARITIME_ROUTE_CAPACITY_REDUCTION: DisruptionTargetType.ROUTE,
    DisruptionType.SUPPLIER_VOLUME_REDUCTION: DisruptionTargetType.SUPPLIER,
    DisruptionType.PORT_DISRUPTION: DisruptionTargetType.PORT,
    DisruptionType.REFINERY_THROUGHPUT_DISRUPTION: DisruptionTargetType.REFINERY,
}


def snapshot_reference_matches(candidate: ScenarioCandidate, snapshot: TwinSnapshot) -> bool:
    reference = candidate.twin_snapshot
    return (
        reference.snapshot_id == snapshot.snapshot_id
        and reference.fingerprint == snapshot.fingerprint
        and reference.version == snapshot.version
        and reference.effective_at == snapshot.effective_at
    )


def resolve_target(snapshot: TwinSnapshot, target: DisruptionTarget) -> DisruptionTarget:
    requested = target.requested_identifier.strip().casefold()
    if target.target_type is DisruptionTargetType.ROUTE:
        matches = [
            route
            for route in snapshot.routes
            if requested
            in {
                str(route.id).casefold(),
                route.canonical_id.casefold(),
                route.canonical_id.removeprefix("route:").casefold(),
            }
        ]
        if len(matches) == 1:
            route = matches[0]
            return target.model_copy(
                update={
                    "asset_id": route.id,
                    "canonical_id": route.canonical_id,
                    "display_name": route.canonical_id.removeprefix("route:")
                    .replace("-", " ")
                    .title(),
                }
            )
        return target.model_copy(update={"asset_id": None, "canonical_id": None})

    allowed_kinds = {
        DisruptionTargetType.CHOKEPOINT: {AssetKind.CHOKEPOINT},
        DisruptionTargetType.SUPPLIER: {AssetKind.SUPPLIER},
        DisruptionTargetType.PORT: {AssetKind.LOAD_PORT, AssetKind.INDIAN_PORT},
        DisruptionTargetType.REFINERY: {AssetKind.REFINERY},
    }[target.target_type]
    node_matches = [
        node
        for node in snapshot.nodes
        if node.kind in allowed_kinds and _matches_node(requested, node)
    ]
    if len(node_matches) == 1:
        node = node_matches[0]
        return target.model_copy(
            update={
                "asset_id": node.id,
                "canonical_id": node.canonical_id,
                "display_name": node.name,
            }
        )
    return target.model_copy(update={"asset_id": None, "canonical_id": None})


def resolve_effects(
    snapshot: TwinSnapshot, effects: list[DisruptionEffect]
) -> list[DisruptionEffect]:
    return [
        effect.model_copy(update={"target": resolve_target(snapshot, effect.target)})
        for effect in effects
    ]


def validate_scenario(
    candidate: ScenarioCandidate,
    snapshot: TwinSnapshot | None,
    *,
    now: datetime | None = None,
) -> ScenarioValidationResult:
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    issues: list[ValidationIssue] = []
    resolved: list[ResolvedDisruptionTarget] = []

    if snapshot is None:
        issues.append(
            _error(
                "TWIN_SNAPSHOT_MISSING",
                "twin_snapshot",
                "The selected twin snapshot is unavailable.",
            )
        )
    elif not snapshot_reference_matches(candidate, snapshot):
        issues.append(
            _error(
                "TWIN_SNAPSHOT_STALE",
                "twin_snapshot",
                "The selected immutable twin reference no longer matches its fingerprint.",
            )
        )

    duration_days = candidate.parameters.disruption_duration.days
    horizon_days = candidate.parameters.simulation_horizon.days
    if duration_days <= 0:
        issues.append(
            _error(
                "INVALID_DURATION",
                "parameters.disruption_duration",
                "Disruption duration must be positive.",
            )
        )
    elif duration_days > MAX_DURATION_DAYS:
        issues.append(
            _error(
                "DURATION_OUT_OF_RANGE",
                "parameters.disruption_duration",
                f"Disruption duration cannot exceed {MAX_DURATION_DAYS:g} days.",
            )
        )
    if horizon_days <= 0 or horizon_days > MAX_DURATION_DAYS:
        issues.append(
            _error(
                "INVALID_HORIZON",
                "parameters.simulation_horizon",
                f"Simulation horizon must be within 0 and {MAX_DURATION_DAYS:g} days.",
            )
        )
    elif horizon_days + 1e-9 < duration_days:
        issues.append(
            _error(
                "HORIZON_TOO_SHORT",
                "parameters.simulation_horizon",
                "Simulation horizon must cover the complete disruption duration.",
            )
        )
    if candidate.parameters.disruption_start.tzinfo is None:
        issues.append(
            _error(
                "START_TIME_NOT_UTC",
                "parameters.disruption_start",
                "Disruption start must be a timezone-aware UTC RFC 3339 timestamp.",
            )
        )

    seen: dict[UUID, DisruptionEffect] = {}
    for index, effect in enumerate(candidate.parameters.disruptions):
        field = f"parameters.disruptions.{index}"
        expected = _EXPECTED_TARGETS[effect.disruption_type]
        if effect.target.target_type is not expected:
            issues.append(
                _error(
                    "TARGET_TYPE_MISMATCH",
                    field,
                    f"{effect.disruption_type} requires a {expected} target.",
                )
            )
        reduction = effect.capacity_reduction.value
        if reduction <= 0 or reduction > 100:
            issues.append(
                _error(
                    "INVALID_PERCENTAGE",
                    f"{field}.capacity_reduction",
                    "Reduction must be greater than 0 and at most 100 percent.",
                )
            )
        if effect.disruption_type is DisruptionType.CHOKEPOINT_CLOSURE and reduction != 100:
            issues.append(
                _error(
                    "INCONSISTENT_CLOSURE",
                    f"{field}.capacity_reduction",
                    "A full closure must be represented as exactly 100 percent reduction.",
                )
            )
        if effect.target.asset_id is None or effect.target.canonical_id is None:
            issues.append(
                _error(
                    "UNKNOWN_TARGET",
                    f"{field}.target",
                    f"Unsupported or ambiguous target: {effect.target.requested_identifier}.",
                )
            )
            continue
        if snapshot is not None and not _resolved_target_exists(snapshot, effect.target):
            issues.append(
                _error(
                    "UNKNOWN_TARGET",
                    f"{field}.target",
                    f"The target does not exist in twin snapshot {snapshot.snapshot_id}.",
                )
            )
            continue
        resolved.append(
            ResolvedDisruptionTarget(
                requested_identifier=effect.target.requested_identifier,
                target_type=effect.target.target_type,
                asset_id=effect.target.asset_id,
                canonical_id=effect.target.canonical_id,
                display_name=effect.target.display_name or effect.target.canonical_id,
            )
        )
        prior = seen.get(effect.target.asset_id)
        if prior is not None:
            code = (
                "DUPLICATE_EFFECT"
                if prior.disruption_type is effect.disruption_type
                else "CONFLICTING_EFFECTS"
            )
            issues.append(
                _error(
                    code,
                    field,
                    "Multiple effects on the same target are refused; submit one "
                    "unambiguous reduction.",
                )
            )
        else:
            seen[effect.target.asset_id] = effect

    for default in candidate.defaults:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.DEFAULT_REQUIRES_CONFIRMATION,
                code="DEFAULT_REQUIRES_CONFIRMATION",
                field=default.field,
                message=(
                    f"Default {default.field}={default.value} {default.unit} must be confirmed."
                ),
            )
        )
    for assumption in candidate.parameters.assumptions:
        if assumption.expires_at is not None and assumption.expires_at <= checked_at:
            issues.append(
                _error(
                    "EXPIRED_ASSUMPTION",
                    f"assumptions.{assumption.id}",
                    f"Assumption {assumption.key} expired at {assumption.expires_at.isoformat()}.",
                )
            )
        elif assumption.status in {AssumptionStatus.EXPIRED, AssumptionStatus.SUPERSEDED}:
            issues.append(
                _error(
                    "INACTIVE_ASSUMPTION",
                    f"assumptions.{assumption.id}",
                    f"Assumption {assumption.key} is {assumption.status}.",
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ASSUMPTION_REQUIRES_CONFIRMATION,
                    code="ASSUMPTION_REQUIRES_CONFIRMATION",
                    field=f"assumptions.{assumption.id}",
                    message=f"Assumption {assumption.key} must be confirmed before simulation.",
                )
            )
    if not candidate.parameters.assumptions:
        issues.append(
            _error(
                "MISSING_INPUT_COVERAGE",
                "parameters.assumptions",
                "Scenario execution inputs require an explicit scenario assumption record.",
            )
        )

    errors = [item for item in issues if item.severity is ValidationSeverity.ERROR]
    validation_id = uuid5(
        NAMESPACE_URL,
        f"urn:sanjiv:scenario-validation:{candidate.scenario_fingerprint}:{VALIDATOR_VERSION}",
    )
    return ScenarioValidationResult(
        validation_id=validation_id,
        scenario_id=candidate.scenario_id,
        scenario_fingerprint=candidate.scenario_fingerprint,
        twin_snapshot=candidate.twin_snapshot,
        valid=not errors,
        issues=issues,
        resolved_targets=resolved,
        defaults=candidate.defaults,
        assumptions=candidate.parameters.assumptions,
        validated_at=checked_at,
        validator_version=VALIDATOR_VERSION,
    )


def _matches_node(requested: str, node: TwinNode) -> bool:
    canonical_short = node.canonical_id.split(":", 1)[-1].replace("-", " ").casefold()
    name = node.name.casefold()
    aliases = {requested, requested.replace("strait of ", ""), requested.replace(" port", "")}
    return any(
        alias in {str(node.id).casefold(), node.canonical_id.casefold(), canonical_short, name}
        or (len(alias) >= 5 and (alias in name or alias in canonical_short))
        for alias in aliases
    )


def _resolved_target_exists(snapshot: TwinSnapshot, target: DisruptionTarget) -> bool:
    if target.target_type is DisruptionTargetType.ROUTE:
        return any(
            route.id == target.asset_id and route.canonical_id == target.canonical_id
            for route in snapshot.routes
        )
    expected = {
        DisruptionTargetType.CHOKEPOINT: {AssetKind.CHOKEPOINT},
        DisruptionTargetType.SUPPLIER: {AssetKind.SUPPLIER},
        DisruptionTargetType.PORT: {AssetKind.LOAD_PORT, AssetKind.INDIAN_PORT},
        DisruptionTargetType.REFINERY: {AssetKind.REFINERY},
    }[target.target_type]
    return any(
        node.id == target.asset_id
        and node.canonical_id == target.canonical_id
        and node.kind in expected
        for node in snapshot.nodes
    )


def _error(code: str, field: str, message: str) -> ValidationIssue:
    return ValidationIssue(
        severity=ValidationSeverity.ERROR, code=code, field=field, message=message
    )
