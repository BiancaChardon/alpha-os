from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from config import settings
from models.events import SignalEvent


class BaseAdapter(ABC):
    source: str

    @abstractmethod
    def fetch(self) -> list[SignalEvent]:
        raise NotImplementedError

    def load_fixture(self, filename: str) -> dict | list:
        path = settings.fixtures_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Fixture not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, BaseAdapter] = {}

    def register(self, adapter: BaseAdapter) -> None:
        self._adapters[adapter.source] = adapter

    def all(self) -> list[BaseAdapter]:
        return list(self._adapters.values())

    def get(self, source: str) -> BaseAdapter:
        return self._adapters[source]
