from __future__ import annotations

import json
from collections import defaultdict

from agents.llm import call_claude, extract_json
from config import settings
from models.events import Briefing, BriefingItem, ClassifiedSignal, Urgency

COMMODITY_LABELS = {
    "power": "Power Markets",
    "natgas": "Natural Gas",
    "crude": "Crude Oil",
    "renewables": "Renewables",
    "weather": "Weather & Demand",
}


def _commodity_label(commodity: str) -> str:
    return COMMODITY_LABELS.get(commodity, commodity.replace("_", " ").title())


def _synthesize_with_rules(signals: list[ClassifiedSignal]) -> Briefing:
    grouped: dict[str, list[ClassifiedSignal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.commodity].append(signal)

    ranked_items: list[BriefingItem] = []
    rank = 1
    for commodity, group in sorted(
        grouped.items(),
        key=lambda item: max(s.relevance_score for s in item[1]),
        reverse=True,
    ):
        group_sorted = sorted(group, key=lambda s: s.relevance_score, reverse=True)
        top = group_sorted[0]
        corroboration = [
            s.one_line_summary
            for s in group_sorted[1:3]
            if s.source != top.source
        ]
        contradictions = [
            s.one_line_summary
            for s in group_sorted
            if (s.sentiment > 0 and top.sentiment < 0) or (s.sentiment < 0 and top.sentiment > 0)
        ]
        confidence = min(0.95, sum(s.confidence for s in group_sorted[:3]) / min(3, len(group_sorted)))
        links: list[str] = []
        for s in group_sorted:
            links.extend(s.evidence_links)

        ranked_items.append(
            BriefingItem(
                rank=rank,
                title=f"{_commodity_label(commodity)} — {top.one_line_summary[:100]}",
                confidence=round(confidence, 2),
                evidence_links=list(dict.fromkeys(links))[:5],
                corroboration_notes="; ".join(corroboration) if corroboration else "Single-source signal cluster.",
                contradiction_notes="; ".join(contradictions[:2]) if contradictions else "No major contradictions detected.",
                supporting_signal_ids=[s.signal_id for s in group_sorted[:5]],
            )
        )
        rank += 1

    high_urgency = sum(1 for s in signals if s.urgency == Urgency.HIGH)
    commodity_names = [_commodity_label(name) for name in grouped]
    summary = (
        f"Today's briefing synthesizes {len(signals)} signals across "
        f"{', '.join(commodity_names)}. "
        f"{high_urgency} high-urgency items flagged for desk review."
    )
    return Briefing(summary=summary, ranked_items=ranked_items[:8], signal_count=len(signals))


def synthesize_briefing(signals: list[ClassifiedSignal]) -> Briefing:
    if not signals:
        return Briefing(
            summary="No classified signals available for synthesis.",
            ranked_items=[],
            signal_count=0,
        )

    payload = [
        {
            "commodity": s.commodity,
            "urgency": s.urgency.value,
            "sentiment": s.sentiment,
            "relevance_score": s.relevance_score,
            "confidence": s.confidence,
            "summary": s.one_line_summary,
            "source": s.source,
            "evidence_links": s.evidence_links,
            "signal_id": s.signal_id,
        }
        for s in signals
    ]
    system = (
        "You are an energy market synthesis analyst. Merge classified signals into a ranked briefing. "
        "Return ONLY JSON with keys: summary (string), ranked_items (array). Each ranked_item needs: "
        "rank, title, confidence (0-1), evidence_links, corroboration_notes, contradiction_notes, "
        "supporting_signal_ids. Identify corroborating and contradictory clusters across commodities."
    )
    raw = call_claude(
        settings.anthropic_synthesis_model,
        system,
        json.dumps(payload, indent=2),
        max_tokens=3000,
    )
    if raw:
        parsed = extract_json(raw)
        if isinstance(parsed, dict) and parsed.get("ranked_items"):
            try:
                items = [BriefingItem.model_validate(item) for item in parsed["ranked_items"]]
                return Briefing(
                    summary=str(parsed.get("summary", "")),
                    ranked_items=items[:8],
                    signal_count=len(signals),
                )
            except Exception:
                pass

    return _synthesize_with_rules(signals)
