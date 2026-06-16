from __future__ import annotations

from datetime import datetime

from adapters.base import BaseAdapter
from models.events import SignalEvent


class CAISOAdapter(BaseAdapter):
    source = "caiso"

    def fetch(self) -> list[SignalEvent]:
        rows = self.load_fixture("caiso_renewables.json")
        events: list[SignalEvent] = []
        for row in rows:
            events.append(
                SignalEvent(
                    ts=datetime.fromisoformat(row["timestamp"]),
                    source=self.source,
                    modality="timeseries",
                    commodity="renewables",
                    payload={
                        "series": row.get("metric", "curtailment_mw"),
                        "value": float(row["value"]),
                        "unit": row.get("unit", "MW"),
                        "region": "CAISO",
                    },
                )
            )
        return events
