from __future__ import annotations

from datetime import datetime

import httpx

from adapters.base import BaseAdapter
from config import settings
from models.events import SignalEvent


class EIAAdapter(BaseAdapter):
    source = "eia"

    def fetch(self) -> list[SignalEvent]:
        if settings.ingestion_fixture_mode or not settings.eia_api_key:
            return self._from_fixture()
        return self._from_api()

    def _from_api(self) -> list[SignalEvent]:
        url = "https://api.eia.gov/v2/natural-gas/pri/fut/data/"
        params = {
            "api_key": settings.eia_api_key,
            "frequency": "daily",
            "data[0]": "value",
            "facets[series][]": "RNGWHHD",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": 10,
        }
        response = httpx.get(url, params=params, timeout=30.0)
        response.raise_for_status()
        rows = response.json()["response"]["data"]
        return self._rows_to_events(rows)

    def _from_fixture(self) -> list[SignalEvent]:
        rows = self.load_fixture("eia_henry_hub.json")
        return self._rows_to_events(rows)

    def _rows_to_events(self, rows: list[dict]) -> list[SignalEvent]:
        events: list[SignalEvent] = []
        for row in rows:
            events.append(
                SignalEvent(
                    ts=datetime.fromisoformat(row["period"]),
                    source=self.source,
                    modality="timeseries",
                    commodity="natgas",
                    payload={
                        "series": row.get("series", "RNGWHHD"),
                        "value": float(row["value"]),
                        "unit": "USD/MMBtu",
                    },
                )
            )
        return events
