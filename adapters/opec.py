from __future__ import annotations

from datetime import datetime

from adapters.base import BaseAdapter
from models.events import SignalEvent


class OPECAdapter(BaseAdapter):
    source = "opec"

    def fetch(self) -> list[SignalEvent]:
        releases = self.load_fixture("opec_releases.json")
        events: list[SignalEvent] = []
        for release in releases:
            events.append(
                SignalEvent(
                    ts=datetime.fromisoformat(release["date"]),
                    source=self.source,
                    modality="text",
                    commodity="crude",
                    payload={
                        "title": release["title"],
                        "url": release["url"],
                        "text": release["text"],
                        "category": "geopolitical",
                    },
                )
            )
        return events
