from __future__ import annotations

import json
import re
from typing import Iterable

from agents.sentiment import score_sentiment
from models.events import ClassifiedSignal, SignalEvent, Urgency

FORWARD_KEYWORDS = {
    "forecast",
    "outlook",
    "guidance",
    "expected",
    "projected",
    "maintenance",
    "notice",
    "approval",
    "proposal",
    "schedule",
}
REACTIVE_KEYWORDS = {"rose", "fell", "spiked", "dropped", "surged", "printed", "hit", "at "}

SERIES_LABELS: dict[str, str] = {
    "DCOILWTICO": "WTI crude",
    "DHHNGSP": "Henry Hub spot gas",
    "RNGWHHD": "Henry Hub futures",
    "WESTERN_HUB": "PJM Western Hub LMP",
    "HB_BUSAVG": "ERCOT hub LMP",
    "HB_HOUSTON": "ERCOT Houston LMP",
    "solar_curtailment_mw": "CAISO solar curtailment",
    "forecast_temp": "Temperature forecast",
    "forecast_wind_mw": "Wind output forecast",
}


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


def _human_series_label(series: str) -> str:
    if series in SERIES_LABELS:
        return SERIES_LABELS[series]
    return re.sub(r"_+", " ", series).strip().title()


def _signal_type_text(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in FORWARD_KEYWORDS):
        return "forward"
    return "reactive"


def _signal_type_timeseries(series: str, pct_change: float, z_score: float) -> str:
    if any(k in series.lower() for k in ("forecast", "outlook", "maintenance", "notice")):
        return "forward"
    if abs(z_score) >= 2.0 or abs(pct_change) >= 5:
        return "reactive"
    return "forward"


def _derive_action(
    *,
    sentiment: float,
    urgency: Urgency,
    pct_change: float,
    signal_type: str,
    commodity: str,
) -> str:
    if signal_type == "reactive" and urgency == Urgency.LOW:
        return "hold"

    urgency_score = {Urgency.HIGH: 0.35, Urgency.MEDIUM: 0.15, Urgency.LOW: -0.05}[urgency]
    momentum = max(-0.35, min(0.35, pct_change / 25))
    composite = sentiment * 0.45 + urgency_score + momentum

    if commodity in {"weather", "renewables", "general"} and abs(composite) < 0.3:
        return "watch"
    if composite >= 0.28:
        return "buy"
    if composite <= -0.28:
        return "sell"
    if signal_type == "reactive":
        return "hold"
    return "watch"


def _action_hint(
    *,
    action: str,
    signal_type: str,
    commodity: str,
    series_label: str,
    pct_change: float,
) -> str:
    if signal_type == "reactive":
        return (
            f"{series_label} move likely already in the tape — treat as confirmation, not a fresh entry trigger."
        )
    if action == "buy":
        return f"Bullish {commodity} setup — watch {series_label} for follow-through over the next session."
    if action == "sell":
        return f"Bearish {commodity} pressure — consider tightening risk if exposed to {series_label}."
    if action == "hold":
        return "Insufficient edge after the recent move — stand aside until new information arrives."
    return f"Monitor {series_label}; signal is informational until corroborated by price or fundamentals."


def _timeseries_summaries(
    commodity: str,
    series: str,
    value: float | int | None,
    pct_change: float,
    z_score: float,
) -> tuple[str, str]:
    label = _human_series_label(series)
    direction = "rose" if pct_change > 0.5 else "fell" if pct_change < -0.5 else "held steady"
    one_line = f"{label} {direction} {abs(pct_change):.1f}% to {value} ({commodity.title()})"
    detail = (
        f"{label} is at {value} with a {pct_change:+.1f}% change vs the prior print "
        f"(z-score {z_score:+.1f}). "
    )
    if commodity == "power":
        detail += "Higher LMP/load signals tighten regional power balances; negative moves often reflect surplus renewables or mild weather."
    elif commodity == "natgas":
        detail += "Gas price moves feed directly into spark spreads and winter storage narratives."
    elif commodity == "crude":
        detail += "Crude moves ripple through cracks, product spreads, and OPEC positioning."
    elif commodity == "renewables":
        detail += "Curtailment and renewable output shifts change midday power supply and can suppress peak prices."
    elif commodity == "weather":
        detail += "Weather forecasts drive load expectations and can front-run power and gas demand."
    else:
        detail += "Cross-check against related commodity signals before acting."
    return one_line, detail


def _classify_timeseries(event: SignalEvent) -> ClassifiedSignal:
    payload = event.payload
    commodity = _infer_commodity(event)
    z_score = float(payload.get("z_score", 0.0))
    pct_change = float(payload.get("pct_change", 0.0))
    spike = bool(payload.get("spike_flag"))
    abs_z = abs(z_score)
    abs_pct = abs(pct_change)
    signal_type = _signal_type_timeseries(str(payload.get("series", "")), pct_change, z_score)

    if spike or abs_z >= 2.5 or abs_pct >= 8:
        urgency = Urgency.HIGH
        relevance = 0.9
    elif abs_z >= 1.5 or abs_pct >= 4:
        urgency = Urgency.MEDIUM
        relevance = 0.7
    else:
        urgency = Urgency.LOW
        relevance = 0.5

    if signal_type == "reactive" and urgency == Urgency.HIGH and abs_pct < 6:
        urgency = Urgency.MEDIUM
        relevance = min(relevance, 0.75)

    value = payload.get("value")
    series = str(payload.get("series", "series"))
    one_line, detail = _timeseries_summaries(commodity, series, value, pct_change, z_score)
    sentiment = score_sentiment(f"{one_line} {detail}")
    if abs(pct_change) >= 0.5:
        sentiment = round(max(-1.0, min(1.0, sentiment + (0.15 if pct_change > 0 else -0.15))), 3)

    action = _derive_action(
        sentiment=sentiment,
        urgency=urgency,
        pct_change=pct_change,
        signal_type=signal_type,
        commodity=commodity,
    )
    hint = _action_hint(
        action=action,
        signal_type=signal_type,
        commodity=commodity,
        series_label=_human_series_label(series),
        pct_change=pct_change,
    )

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
        one_line_summary=one_line,
        detail_summary=detail,
        action_hint=hint,
        action=action,
        signal_type=signal_type,
        entities=[event.source.upper(), series],
        evidence_links=[],
        stats={
            "value": value,
            "pct_change": payload.get("pct_change"),
            "z_score": payload.get("z_score"),
            "spike_flag": spike,
            "series": series,
        },
    )


def _classify_text(event: SignalEvent) -> ClassifiedSignal:
    commodity = _infer_commodity(event)
    text = str(event.payload.get("text") or event.payload.get("title") or "")
    title = str(event.payload.get("title", ""))
    sentiment = score_sentiment(text or title)
    lower = text.lower()
    signal_type = _signal_type_text(text or title)

    if any(k in lower for k in ("approval", "sanction", "cut", "outage", "emergency")):
        urgency = Urgency.HIGH
        relevance = 0.85
    elif any(k in lower for k in ("forecast", "storage", "expansion", "record", "maintenance")):
        urgency = Urgency.MEDIUM
        relevance = 0.7
    else:
        urgency = Urgency.LOW
        relevance = 0.55

    if signal_type == "reactive" and urgency == Urgency.HIGH:
        urgency = Urgency.MEDIUM

    summary = title or text[:120]
    detail = text[:500] if text else summary
    action = _derive_action(
        sentiment=sentiment,
        urgency=urgency,
        pct_change=0.0,
        signal_type=signal_type,
        commodity=commodity,
    )
    hint = _action_hint(
        action=action,
        signal_type=signal_type,
        commodity=commodity,
        series_label=summary[:60],
        pct_change=0.0,
    )
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
        one_line_summary=summary,
        detail_summary=detail,
        action_hint=hint,
        action=action,
        signal_type=signal_type,
        entities=[event.source.upper(), commodity],
        evidence_links=[url] if url else [],
        stats={"title": title, "url": url},
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
        "relevance_score (0 to 1), confidence (0 to 1), one_line_summary, detail_summary "
        "(2-3 sentences), action_hint (one actionable sentence), action (buy|sell|hold|watch), "
        "signal_type (forward|reactive), entities (array), evidence_links (array of URLs)."
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
        summary = str(item.get("one_line_summary", ""))[:200]
        detail = str(item.get("detail_summary", summary))[:500]
        llm_sentiment = float(item.get("sentiment", 0.0))
        nltk_sentiment = score_sentiment(summary + " " + detail)
        blended = round((llm_sentiment * 0.6) + (nltk_sentiment * 0.4), 3)
        action = str(item.get("action", "watch"))
        if action not in {"buy", "sell", "hold", "watch"}:
            action = "watch"
        signal_type = str(item.get("signal_type", "forward"))
        if signal_type not in {"forward", "reactive"}:
            signal_type = _signal_type_text(summary)
        results.append(
            ClassifiedSignal(
                event_id=event.event_id,
                ts=event.ts,
                source=event.source,
                modality=event.modality,
                commodity=item.get("commodity", _infer_commodity(event)),
                urgency=urgency,
                sentiment=blended,
                relevance_score=float(item.get("relevance_score", 0.5)),
                confidence=float(item.get("confidence", 0.7)),
                one_line_summary=summary,
                detail_summary=detail,
                action_hint=str(item.get("action_hint", ""))[:300],
                action=action,
                signal_type=signal_type,
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
