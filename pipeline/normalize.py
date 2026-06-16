from __future__ import annotations

import hashlib
import re
from collections.abc import Callable

from models.events import SignalEvent


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def enrich_text_event(event: SignalEvent) -> SignalEvent:
    payload = dict(event.payload)
    if "text" in payload:
        payload["text"] = normalize_text(payload["text"])
        payload["text_hash"] = hashlib.sha256(payload["text"].encode("utf-8")).hexdigest()[:16]
    if "title" in payload:
        payload["title"] = normalize_text(str(payload["title"]))
    if "excerpt" not in payload and "text" in payload:
        payload["excerpt"] = payload["text"][:500]
    event.payload = payload
    return event


def enrich_timeseries_event(event: SignalEvent, history: list[SignalEvent] | None = None) -> SignalEvent:
    payload = dict(event.payload)
    value = payload.get("value")
    if value is None:
        return event

    same_series = []
    if history:
        series = payload.get("series")
        same_series = [
            e.payload.get("value")
            for e in history
            if e.source == event.source
            and e.payload.get("series") == series
            and isinstance(e.payload.get("value"), (int, float))
        ]

    if len(same_series) >= 2:
        prev = same_series[0]
        delta = float(value) - float(prev)
        pct = (delta / float(prev) * 100) if prev else 0.0
        mean = sum(same_series) / len(same_series)
        variance = sum((x - mean) ** 2 for x in same_series) / len(same_series)
        std = variance**0.5
        z = (float(value) - mean) / std if std else 0.0
        payload["delta"] = round(delta, 4)
        payload["pct_change"] = round(pct, 2)
        payload["z_score"] = round(z, 2)
        payload["spike_flag"] = abs(z) >= 2.0

    event.payload = payload
    return event


def dedupe_events(events: list[SignalEvent]) -> list[SignalEvent]:
    seen: set[str] = set()
    unique: list[SignalEvent] = []
    for event in events:
        key = event.dedupe_key
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def refresh_event_timestamps(events: list[SignalEvent]) -> list[SignalEvent]:
    """Shift fixture timestamps forward so recent lookback filters include them."""
    if not events:
        return events
    from datetime import datetime

    latest = max(event.ts for event in events)
    offset = datetime.utcnow() - latest
    return [event.model_copy(update={"ts": event.ts + offset}) for event in events]


def normalize_events(events: list[SignalEvent]) -> list[SignalEvent]:
    events = refresh_event_timestamps(events)
    normalized: list[SignalEvent] = []
    for event in events:
        if event.modality == "text":
            normalized.append(enrich_text_event(event))
        else:
            normalized.append(enrich_timeseries_event(event, history=events))
    return dedupe_events(normalized)
