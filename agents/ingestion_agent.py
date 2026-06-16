from __future__ import annotations

import json
from typing import Iterable

from models.events import ClassifiedSignal, SignalEvent, Urgency


NEGATIVE_KEYWORDS = {"cut", "sanction", "outage", "curtailment", "shortage", "spike", "tight"}
POSITIVE_KEYWORDS = {"build", "approval", "expansion", "record", "surplus", "decline", "drop"}


def _infer_commodity(event: SignalEvent) -> str:
    if event.commodity:
        return event.commodity
    text = json.dumps(event.payload).lower()
    if any(k in text for k in ("gas", "pipeline", "bcf", "henry")):
        return "natgas"
    if any(k in text for k in ("oil", "crude", "opec", "barrel")):
        return "crude"
    if any(k in text for k in ("lmp", "mw", "ercot", "pjm", "grid", "power")):
        return "power"
    if any(k in text for k in ("solar", "wind", "renewable", "curtailment")):
        return "renewables"
    if any(k in text for k in ("weather", "heat", "temperature", "forecast")):
        return "weather"
    return "general"


def _text_sentiment(text: str) -> float:
    lower = text.lower()
    score = 0.0
    for word in NEGATIVE_KEYWORDS:
        if word in lower:
            score -= 0.2
    for word in POSITIVE_KEYWORDS:
        if word in lower:
            score += 0.2
    return max(-1.0, min(1.0, score))


def _classify_timeseries(event: SignalEvent) -> ClassifiedSignal:
    payload = event.payload
    commodity = _infer_commodity(event)
    z_score = abs(float(payload.get("z_score", 0.0)))
    pct_change = abs(float(payload.get("pct_change", 0.0)))
    spike = bool(payload.get("spike_flag"))

    if spike or z_score >= 2.5 or pct_change >= 8:
        urgency = Urgency.HIGH
        relevance = 0.9
    elif z_score >= 1.5 or pct_change >= 4:
        urgency = Urgency.MEDIUM
        relevance = 0.7
    else:
        urgency = Urgency.LOW
        relevance = 0.5

    value = payload.get("value")
    series = payload.get("series", "series")
    summary = f"{commodity} {series} at {value}; pct_change={payload.get('pct_change', 0)}%"
    sentiment = 0.3 if float(payload.get("pct_change", 0)) > 0 else -0.2

    return ClassifiedSignal(
        event_id=event.event_id,
        ts=event.ts,
        source=event.source,
        modality=event.modality,
        commodity=commodity,
        urgency=urgency,
        sentiment=sentiment,
        relevance_score=relevance,
        confidence=0.85 if spike else 0.7,
        one_line_summary=summary,
        entities=[event.source.upper(), series],
        evidence_links=[],
        stats={
            "value": value,
            "pct_change": payload.get("pct_change"),
            "z_score": payload.get("z_score"),
            "spike_flag": spike,
        },
    )


def _classify_text(event: SignalEvent) -> ClassifiedSignal:
    commodity = _infer_commodity(event)
    text = str(event.payload.get("text") or event.payload.get("title") or "")
    title = str(event.payload.get("title", ""))
    sentiment = _text_sentiment(text)
    lower = text.lower()

    if any(k in lower for k in ("approval", "sanction", "cut", "outage", "emergency")):
        urgency = Urgency.HIGH
        relevance = 0.85
    elif any(k in lower for k in ("forecast", "storage", "expansion", "record")):
        urgency = Urgency.MEDIUM
        relevance = 0.7
    else:
        urgency = Urgency.LOW
        relevance = 0.55

    url = event.payload.get("url")
    return ClassifiedSignal(
        event_id=event.event_id,
        ts=event.ts,
        source=event.source,
        modality=event.modality,
        commodity=commodity,
        urgency=urgency,
        sentiment=sentiment,
        relevance_score=relevance,
        confidence=0.75,
        one_line_summary=title or text[:120],
        entities=[event.source.upper(), commodity],
        evidence_links=[url] if url else [],
        stats={"title": title},
    )


def classify_events(events: Iterable[SignalEvent]) -> list[ClassifiedSignal]:
    """Hybrid classification: rules for timeseries, Claude Haiku for text."""
    classified: list[ClassifiedSignal] = []
    text_events: list[SignalEvent] = []

    for event in events:
        if event.modality == "timeseries":
            classified.append(_classify_timeseries(event))
        else:
            text_events.append(event)

    if text_events:
        llm_results = _classify_text_batch_with_llm(text_events)
        if llm_results:
            classified.extend(llm_results)
        else:
            classified.extend(_classify_text(event) for event in text_events)

    return classified


def _classify_text_batch_with_llm(events: list[SignalEvent]) -> list[ClassifiedSignal] | None:
    from agents.llm import call_claude, extract_json
    from config import settings

    payload = [
        {
            "event_id": e.event_id,
            "source": e.source,
            "title": e.payload.get("title"),
            "text": e.payload.get("text") or e.payload.get("excerpt"),
            "url": e.payload.get("url"),
            "commodity_hint": e.commodity,
        }
        for e in events
    ]
    system = (
        "You are an energy market signal classifier. Classify each text signal and return "
        "ONLY a JSON array. Each item must include: event_id, commodity (natgas|crude|power|"
        "renewables|weather|general), urgency (low|medium|high), sentiment (-1 to 1), "
        "relevance_score (0 to 1), confidence (0 to 1), one_line_summary, entities (array), "
        "evidence_links (array of URLs)."
    )
    raw = call_claude(
        settings.anthropic_classification_model,
        system,
        json.dumps(payload, indent=2),
        max_tokens=2048,
    )
    if not raw:
        return None

    parsed = extract_json(raw)
    if not isinstance(parsed, list):
        return None

    event_map = {e.event_id: e for e in events}
    results: list[ClassifiedSignal] = []
    for item in parsed:
        event_id = item.get("event_id")
        event = event_map.get(event_id)
        if not event:
            continue
        try:
            urgency = Urgency(item.get("urgency", "low"))
        except ValueError:
            urgency = Urgency.LOW
        results.append(
            ClassifiedSignal(
                event_id=event.event_id,
                ts=event.ts,
                source=event.source,
                modality=event.modality,
                commodity=item.get("commodity", _infer_commodity(event)),
                urgency=urgency,
                sentiment=float(item.get("sentiment", 0.0)),
                relevance_score=float(item.get("relevance_score", 0.5)),
                confidence=float(item.get("confidence", 0.7)),
                one_line_summary=str(item.get("one_line_summary", ""))[:200],
                entities=item.get("entities", []),
                evidence_links=item.get("evidence_links", []) or (
                    [event.payload["url"]] if event.payload.get("url") else []
                ),
            )
        )
    return results or None


def classify_events_with_llm(events: list[SignalEvent]) -> list[ClassifiedSignal]:
    """Backward-compatible alias."""
    return classify_events(events)
