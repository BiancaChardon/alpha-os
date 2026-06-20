from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    ts: datetime
    source: str
    modality: Literal["timeseries", "text"]
    commodity: str | None = None
    payload: dict = Field(default_factory=dict)

    @property
    def dedupe_key(self) -> str:
        if self.modality == "text":
            return str(self.payload.get("url") or self.payload.get("title") or self.event_id)
        series = self.payload.get("series", "default")
        return f"{self.source}:{series}:{self.ts.isoformat()}"


class ClassifiedSignal(BaseModel):
    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    event_id: str
    ts: datetime
    source: str
    modality: Literal["timeseries", "text"]
    commodity: str
    urgency: Urgency
    sentiment: float = Field(ge=-1.0, le=1.0)
    relevance_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    one_line_summary: str
    detail_summary: str = ""
    action_hint: str = ""
    action: Literal["buy", "sell", "hold", "watch"] = "watch"
    signal_type: Literal["forward", "reactive"] = "reactive"
    entities: list[str] = Field(default_factory=list)
    evidence_links: list[str] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)


class BriefingItem(BaseModel):
    rank: int
    title: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_links: list[str] = Field(default_factory=list)
    corroboration_notes: str = ""
    contradiction_notes: str = ""
    supporting_signal_ids: list[str] = Field(default_factory=list)


class Briefing(BaseModel):
    briefing_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str
    ranked_items: list[BriefingItem] = Field(default_factory=list)
    signal_count: int = 0


class ContrarianReview(BaseModel):
    review_id: str = Field(default_factory=lambda: str(uuid4()))
    briefing_id: str
    counterarguments: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    alternative_interpretation: str
    confidence_adjustment: float = Field(ge=-1.0, le=1.0)


class IngestionRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    source: str
    status: Literal["running", "success", "failed"] = "running"
    events_fetched: int = 0
    error: str | None = None
