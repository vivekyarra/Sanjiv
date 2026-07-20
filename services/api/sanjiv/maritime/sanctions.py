from dataclasses import dataclass
from difflib import SequenceMatcher
from uuid import UUID

from sanjiv.contracts import TruthClass
from sanjiv.maritime.contracts import SanctionsAssessment, SanctionsMatchStatus, VesselPosition


@dataclass(frozen=True)
class SanctionsRecord:
    name: str
    evidence_id: UUID
    imo: str | None = None
    mmsi: str | None = None


class SanctionsMatcher:
    """Offline matcher. Source acquisition is deliberately outside this Phase 1 slice."""

    def __init__(
        self, records: list[SanctionsRecord] | None = None, *, fuzzy_threshold: float = 0.9
    ) -> None:
        self._records = records
        self._threshold = fuzzy_threshold

    def assess(self, position: VesselPosition) -> SanctionsAssessment:
        if self._records is None:
            return SanctionsAssessment(
                status=SanctionsMatchStatus.NOT_SCREENED,
                truth_class=TruthClass.INFERRED,
                confidence=0.0,
                evidence_ids=[],
                explanation="No sanctions dataset is loaded; this vessel has not been screened.",
            )
        for record in self._records:
            if (record.imo and position.imo == record.imo) or (
                record.mmsi and position.mmsi == record.mmsi
            ):
                return SanctionsAssessment(
                    status=SanctionsMatchStatus.EXACT_MATCH,
                    truth_class=TruthClass.DERIVED,
                    confidence=1.0,
                    evidence_ids=[record.evidence_id, *position.evidence_ids],
                    explanation=(
                        "Exact identifier match against the loaded sanctions record; "
                        "review source details."
                    ),
                )
        vessel_name = position.vessel_name
        if vessel_name:
            candidate = max(
                self._records,
                key=lambda item: SequenceMatcher(
                    None, vessel_name.upper(), item.name.upper()
                ).ratio(),
                default=None,
            )
            if candidate is not None:
                score = SequenceMatcher(None, vessel_name.upper(), candidate.name.upper()).ratio()
                if score >= self._threshold:
                    return SanctionsAssessment(
                        status=SanctionsMatchStatus.POTENTIAL_MATCH,
                        truth_class=TruthClass.INFERRED,
                        confidence=score,
                        evidence_ids=[candidate.evidence_id, *position.evidence_ids],
                        explanation="Fuzzy name similarity only; not a confirmed sanctions match.",
                    )
        return SanctionsAssessment(
            status=SanctionsMatchStatus.NO_MATCH,
            truth_class=TruthClass.DERIVED,
            confidence=1.0,
            evidence_ids=position.evidence_ids,
            explanation=(
                "No match in the loaded dataset version; this is not a guarantee of "
                "sanctions clearance."
            ),
        )
