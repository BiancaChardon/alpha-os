from __future__ import annotations

from datetime import datetime

import httpx

from adapters.base import BaseAdapter
from config import settings
from models.events import SignalEvent


class FREDAdapter(BaseAdapter):
    source = "fred"

    SERIES = {
        "DCOILWTICO": ("crude", "WTI Crude Oil"),
        "DHHNGSP": ("natgas", "Henry Hub Spot"),
    }

    def fetch(self) -> list[SignalEvent]:
        if settings.ingestion_fixture_mode or not settings.fred_api_key:
            return self._from_fixture()
        return self._from_api()

    def _from_api(self) -> list[SignalEvent]:
        events: list[SignalEvent] = []
        for series_id, (commodity, label) in self.SERIES.items():
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": series_id,
                "api_key": settings.fred_api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 10,
            }
            response = httpx.get(url, params=params, timeout=30.0)
            response.raise_for_status()
            observations = response.json().get("observations", [])
            events.extend(self._observations_to_events(observations, series_id, commodity, label))
        return events

    def _from_fixture(self) -> list[SignalEvent]:
        data = self.load_fixture("fred_observations.json")
        events: list[SignalEvent] = []
        for series_id, payload in data.items():
            commodity, label = self.SERIES[series_id]
            events.extend(
                self._observations_to_events(payload["observations"], series_id, commodity, label)
            )
        return events

    def _observations_to_events(
        self, observations: list[dict], series_id: str, commodity: str, label: str
    ) -> list[SignalEvent]:
        events: list[SignalEvent] = []
        for obs in observations:
            if obs.get("value") in (".", None, ""):
                continue
            events.append(
                SignalEvent(
                    ts=datetime.fromisoformat(obs["date"]),
                    source=self.source,
                    modality="timeseries",
                    commodity=commodity,
                    payload={
                        "series": series_id,
                        "label": label,
                        "value": float(obs["value"]),
                    },
                )
            )
        return events
