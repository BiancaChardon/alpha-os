from __future__ import annotations

from datetime import datetime

from adapters.base import BaseAdapter
from models.events import SignalEvent


class ERCOTAdapter(BaseAdapter):
    source = "ercot"

    def fetch(self) -> list[SignalEvent]:
        rows = self.load_fixture("ercot_lmp.json")
        events: list[SignalEvent] = []
        for row in rows:
            events.append(
                SignalEvent(
                    ts=datetime.fromisoformat(row["timestamp"]),
                    source=self.source,
                    modality="timeseries",
                    commodity="power",
                    payload={
                        "series": row.get("settlement_point", "HB_HOUSTON"),
                        "value": float(row["lmp"]),
                        "unit": "USD/MWh",
                        "region": "ERCOT",
                    },
                )
            )
        return events
