from __future__ import annotations

from datetime import datetime

import feedparser

from adapters.base import BaseAdapter
from config import settings
from models.events import SignalEvent


class EIATodayAdapter(BaseAdapter):
    source = "eia_today"

    FEED_URL = "https://www.eia.gov/rss/todayinenergy.xml"

    def fetch(self) -> list[SignalEvent]:
        if settings.ingestion_fixture_mode:
            entries = self.load_fixture("eia_today_entries.json")
        else:
            feed = feedparser.parse(self.FEED_URL)
            entries = [
                {
                    "title": entry.title,
                    "link": entry.link,
                    "summary": getattr(entry, "summary", ""),
                    "published": entry.get("published", datetime.utcnow().isoformat()),
                }
                for entry in feed.entries[:10]
            ]
        return self._entries_to_events(entries)

    def _entries_to_events(self, entries: list[dict]) -> list[SignalEvent]:
        events: list[SignalEvent] = []
        for entry in entries:
            published = entry.get("published", datetime.utcnow().isoformat())
            try:
                ts = datetime.fromisoformat(published.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                ts = datetime.utcnow()
            events.append(
                SignalEvent(
                    ts=ts,
                    source=self.source,
                    modality="text",
                    commodity=None,
                    payload={
                        "title": entry["title"],
                        "url": entry["link"],
                        "text": entry.get("summary", entry["title"]),
                        "category": "regulatory_market",
                    },
                )
            )
        return events
