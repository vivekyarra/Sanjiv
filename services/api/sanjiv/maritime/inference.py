from datetime import datetime

from sanjiv.contracts import MetricEnvelope, SourceRef, TruthClass
from sanjiv.maritime.contracts import IndiaBoundAssessment, InferenceContribution, VesselPosition

INDIA_BOUND_VERSION = "india-bound-heuristic-1.0.0"
INDIAN_DESTINATIONS = (
    "JAMNAGAR",
    "VADINAR",
    "MUMBAI",
    "PARADIP",
    "MANGALORE",
    "KOCHI",
    "VISAKHAPATNAM",
    "CHENNAI",
)


def assess_india_bound(position: VesselPosition, *, computed_at: datetime) -> IndiaBoundAssessment:
    destination = (position.destination_raw or "").upper()
    contributions = [
        InferenceContribution(
            key="destination",
            label="Reported destination resembles an Indian energy port",
            weight=0.30,
            score=1.0
            if destination and any(name in destination for name in INDIAN_DESTINATIONS)
            else (0.0 if destination else None),
            explanation="AIS destination is free text and does not establish cargo ownership.",
        ),
        InferenceContribution(
            key="route_cone",
            label="Position lies on a plausible approach to India",
            weight=0.25,
            score=1.0 if 5 <= position.latitude <= 30 and 50 <= position.longitude <= 85 else 0.0,
            explanation="Broad geographic heuristic only; not a confirmed voyage plan.",
        ),
        InferenceContribution(
            key="heading",
            label="Course is broadly eastbound toward India",
            weight=0.20,
            score=(
                1.0
                if position.course_degrees is not None and 45 <= position.course_degrees <= 135
                else (0.0 if position.course_degrees is not None else None)
            ),
            explanation="Course may change and is not a destination declaration.",
        ),
        InferenceContribution(
            key="previous_port",
            label="Previous-port consistency",
            weight=0.15,
            score=None,
            explanation="Previous-port evidence is unavailable in the Phase 1 feed.",
        ),
        InferenceContribution(
            key="vessel_class",
            label="AIS ship type is consistent with tanker traffic",
            weight=0.10,
            score=(
                1.0
                if position.ship_type is not None and 80 <= position.ship_type <= 89
                else (0.0 if position.ship_type is not None else None)
            ),
            explanation="Vessel class does not reveal cargo or charter availability.",
        ),
    ]
    available_weight = sum(item.weight for item in contributions if item.score is not None)
    weighted = sum(item.weight * item.score for item in contributions if item.score is not None)
    likelihood = weighted / available_weight if available_weight else 0.0
    return IndiaBoundAssessment(
        likelihood=MetricEnvelope[float](
            value=round(likelihood, 4),
            unit="fraction",
            truth_class=TruthClass.INFERRED,
            confidence=round(available_weight, 4),
            evidence_ids=position.evidence_ids,
            source_refs=[
                SourceRef(source_id=position.source_id, record_id=position.source_record_id)
            ],
            effective_at=position.source_timestamp,
            fetched_at=position.fetched_at,
            computed_at=computed_at,
            freshness_status=position.freshness_status,
            transformation=INDIA_BOUND_VERSION,
            model_version=INDIA_BOUND_VERSION,
        ),
        completeness=round(available_weight, 4),
        contributions=contributions,
        disclaimer=(
            "Heuristic likelihood only. It does not establish cargo ownership, charter "
            "availability, or a confirmed destination."
        ),
    )
