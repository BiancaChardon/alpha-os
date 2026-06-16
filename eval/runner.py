from __future__ import annotations

from dataclasses import dataclass

from agents.contrarian_agent import generate_contrarian_review
from agents.synthesis_agent import synthesize_briefing
from models.events import Briefing, BriefingItem, ClassifiedSignal, Urgency


@dataclass
class EvalResult:
    scenario_id: str
    score: float
    notes: list[str]


RUBRIC_WEIGHTS = {
    "has_ranked_items": 0.25,
    "mentions_commodity": 0.2,
    "has_evidence_or_corroboration": 0.2,
    "contrarian_present": 0.2,
    "urgency_alignment": 0.15,
}


def _sample_signals() -> list[ClassifiedSignal]:
    from datetime import datetime

    return [
        ClassifiedSignal(
            event_id="e1",
            ts=datetime.utcnow(),
            source="eia",
            modality="timeseries",
            commodity="natgas",
            urgency=Urgency.HIGH,
            sentiment=0.4,
            relevance_score=0.9,
            confidence=0.85,
            one_line_summary="Henry Hub futures rose 2.3% on lower storage build",
            evidence_links=["https://www.eia.gov/todayinenergy/example1.php"],
        ),
        ClassifiedSignal(
            event_id="e2",
            ts=datetime.utcnow(),
            source="ercot",
            modality="timeseries",
            commodity="power",
            urgency=Urgency.HIGH,
            sentiment=0.5,
            relevance_score=0.88,
            confidence=0.82,
            one_line_summary="ERCOT Houston hub LMP spiked above $60/MWh",
        ),
        ClassifiedSignal(
            event_id="e3",
            ts=datetime.utcnow(),
            source="opec",
            modality="text",
            commodity="crude",
            urgency=Urgency.MEDIUM,
            sentiment=-0.1,
            relevance_score=0.7,
            confidence=0.75,
            one_line_summary="OPEC+ extends production cuts through Q3",
            evidence_links=["https://www.opec.org/example/release"],
        ),
    ]


def score_briefing(scenario_id: str, briefing: Briefing, review_present: bool, expected_commodity: str) -> EvalResult:
    notes: list[str] = []
    score = 0.0

    if briefing.ranked_items:
        score += RUBRIC_WEIGHTS["has_ranked_items"]
    else:
        notes.append("Missing ranked items")

    commodity_hit = any(expected_commodity in item.title.lower() for item in briefing.ranked_items)
    if commodity_hit:
        score += RUBRIC_WEIGHTS["mentions_commodity"]
    else:
        notes.append(f"Expected commodity '{expected_commodity}' not reflected in titles")

    evidence_hit = any(item.evidence_links or item.corroboration_notes for item in briefing.ranked_items)
    if evidence_hit:
        score += RUBRIC_WEIGHTS["has_evidence_or_corroboration"]
    else:
        notes.append("No evidence links or corroboration notes")

    if review_present:
        score += RUBRIC_WEIGHTS["contrarian_present"]
    else:
        notes.append("Missing contrarian review")

    if briefing.signal_count >= 2:
        score += RUBRIC_WEIGHTS["urgency_alignment"]
    else:
        notes.append("Insufficient signal count for urgency alignment")

    return EvalResult(scenario_id=scenario_id, score=round(score, 3), notes=notes)


GOLDEN_SCENARIOS = [
    {"id": "natgas_storage", "expected_commodity": "natgas"},
    {"id": "ercot_heat_spike", "expected_commodity": "power"},
    {"id": "opec_cuts", "expected_commodity": "crude"},
    {"id": "caiso_curtailment", "expected_commodity": "renewables"},
    {"id": "ferc_pipeline", "expected_commodity": "natgas"},
    {"id": "pjm_lmp_move", "expected_commodity": "power"},
    {"id": "weather_demand", "expected_commodity": "weather"},
    {"id": "mixed_cluster", "expected_commodity": "natgas"},
    {"id": "regulatory_notice", "expected_commodity": "power"},
    {"id": "contrarian_stress", "expected_commodity": "crude"},
]


def run_eval() -> dict:
    signals = _sample_signals()
    briefing = synthesize_briefing(signals)
    review = generate_contrarian_review(briefing)
    results = [
        score_briefing(
            scenario["id"],
            briefing,
            review_present=review is not None,
            expected_commodity=scenario["expected_commodity"],
        )
        for scenario in GOLDEN_SCENARIOS
    ]
    avg = sum(r.score for r in results) / len(results)
    return {
        "average_score": round(avg, 3),
        "scenario_count": len(results),
        "results": [r.__dict__ for r in results],
    }
