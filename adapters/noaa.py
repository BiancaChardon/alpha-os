from __future__ import annotations

from datetime import datetime

import httpx

from adapters.base import BaseAdapter
from config import settings
from models.events import SignalEvent


class NOAAAdapter(BaseAdapter):
    source = "noaa"

    def fetch(self) -> list[SignalEvent]:
        if settings.ingestion_fixture_mode:
            return self._from_fixture()
        return self._from_api()

    def _from_api(self) -> list[SignalEvent]:
        url = "https://api.weather.gov/gridpoints/TOP/31,80/forecast"
        headers = {"User-Agent": "AlphaOS/1.0 (energy-analytics@example.com)"}
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        periods = response.json()["properties"]["periods"][:6]
        return self._periods_to_events(periods)

    def _from_fixture(self) -> list[SignalEvent]:
        periods = self.load_fixture("noaa_forecast.json")
        return self._periods_to_events(periods)

    def _periods_to_events(self, periods: list[dict]) -> list[SignalEvent]:
        events: list[SignalEvent] = []
        for period in periods:
            events.append(
                SignalEvent(
                    ts=datetime.fromisoformat(period["startTime"].replace("Z", "+00:00")).replace(tzinfo=None),
                    source=self.source,
                    modality="timeseries",
                    commodity="weather",
                    payload={
                        "series": "forecast_temp",
                        "value": float(period["temperature"]),
                        "unit": period.get("temperatureUnit", "F"),
                        "label": period.get("shortForecast", ""),
                        "region": "Central US",
                    },
                )
            )
        return events
