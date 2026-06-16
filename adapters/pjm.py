from __future__ import annotations

from datetime import datetime

from adapters.base import BaseAdapter
from config import settings
from models.events import SignalEvent


class PJMAdapter(BaseAdapter):
    source = "pjm"

    def fetch(self) -> list[SignalEvent]:
        rows = self.load_fixture("pjm_lmp.json")
        events: list[SignalEvent] = []
        for row in rows:
            events.append(
                SignalEvent(
                    ts=datetime.fromisoformat(row["datetime_beginning_ept"]),
                    source=self.source,
                    modality="timeseries",
                    commodity="power",
                    payload={
                        "series": row.get("pnode_name", "PJM_HUB"),
                        "value": float(row["lmp"]),
                        "unit": "USD/MWh",
                        "region": "PJM",
                    },
                )
            )
        return events
