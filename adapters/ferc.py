from __future__ import annotations

from datetime import datetime

from adapters.base import BaseAdapter
from models.events import SignalEvent


class FERCAdapter(BaseAdapter):
    source = "ferc"

    def fetch(self) -> list[SignalEvent]:
        notices = self.load_fixture("ferc_notices.json")
        events: list[SignalEvent] = []
        for notice in notices:
            events.append(
                SignalEvent(
                    ts=datetime.fromisoformat(notice["date"]),
                    source=self.source,
                    modality="text",
                    commodity=notice.get("commodity"),
                    payload={
                        "title": notice["title"],
                        "url": notice["url"],
                        "text": notice["text"],
                        "docket": notice.get("docket"),
                        "category": "regulatory",
                    },
                )
            )
        return events
