from __future__ import annotations

from sanjiv.contracts import FreshnessStatus, TruthClass

ALLOWED_EVIDENCE_TRUTH: dict[TruthClass, set[TruthClass]] = {
    TruthClass.OBSERVED: {TruthClass.OBSERVED},
    TruthClass.DERIVED: {TruthClass.OBSERVED, TruthClass.DERIVED, TruthClass.ASSUMPTION},
    TruthClass.INFERRED: {
        TruthClass.OBSERVED,
        TruthClass.DERIVED,
        TruthClass.INFERRED,
        TruthClass.ASSUMPTION,
    },
    TruthClass.MODELED: set(TruthClass),
    # Assumption envelopes still carry the evidence that establishes their context;
    # the actual assumed value is validated through the separate assumption ledger.
    TruthClass.ASSUMPTION: set(TruthClass),
}

BLOCKING_FRESHNESS = {FreshnessStatus.STALE, FreshnessStatus.UNAVAILABLE}


def truth_transition_allowed(metric_truth: TruthClass, evidence_truth: TruthClass) -> bool:
    return evidence_truth in ALLOWED_EVIDENCE_TRUTH[metric_truth]
