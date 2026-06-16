from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from config import settings
from models.events import Briefing, ClassifiedSignal, ContrarianReview, IngestionRun, SignalEvent


class EventStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS raw_events (
                    event_id TEXT PRIMARY KEY,
                    ts TEXT NOT NULL,
                    source TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    commodity TEXT,
                    payload TEXT NOT NULL,
                    dedupe_key TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS classified_signals (
                    signal_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS briefings (
                    briefing_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contrarian_reviews (
                    review_id TEXT PRIMARY KEY,
                    briefing_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ingestion_runs (
                    run_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS perplexity_research (
                    briefing_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_events(self, events: list[SignalEvent]) -> int:
        inserted = 0
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            for event in events:
                try:
                    conn.execute(
                        """
                        INSERT INTO raw_events
                        (event_id, ts, source, modality, commodity, payload, dedupe_key, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.event_id,
                            event.ts.isoformat(),
                            event.source,
                            event.modality,
                            event.commodity,
                            json.dumps(event.payload),
                            event.dedupe_key,
                            now,
                        ),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    continue
        return inserted

    def get_recent_events(self, hours: int | None = None) -> list[SignalEvent]:
        hours = hours or settings.signal_lookback_hours
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM raw_events WHERE ts >= ? ORDER BY ts DESC",
                (cutoff,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def save_classified_signals(self, signals: list[ClassifiedSignal]) -> None:
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            for signal in signals:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO classified_signals (signal_id, event_id, data, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (signal.signal_id, signal.event_id, signal.model_dump_json(), now),
                )

    def get_recent_classified_signals(self, hours: int | None = None) -> list[ClassifiedSignal]:
        hours = hours or settings.signal_lookback_hours
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT data FROM classified_signals WHERE created_at >= ? ORDER BY created_at DESC",
                (cutoff,),
            ).fetchall()
        return [ClassifiedSignal.model_validate_json(row["data"]) for row in rows]

    def save_briefing(self, briefing: Briefing) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO briefings (briefing_id, data, created_at) VALUES (?, ?, ?)",
                (briefing.briefing_id, briefing.model_dump_json(), briefing.created_at.isoformat()),
            )

    def get_latest_briefing(self) -> Briefing | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM briefings ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return Briefing.model_validate_json(row["data"]) if row else None

    def save_contrarian_review(self, review: ContrarianReview) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO contrarian_reviews (review_id, briefing_id, data, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    review.review_id,
                    review.briefing_id,
                    review.model_dump_json(),
                    datetime.utcnow().isoformat(),
                ),
            )

    def get_latest_contrarian_review(self) -> ContrarianReview | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM contrarian_reviews ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return ContrarianReview.model_validate_json(row["data"]) if row else None

    def get_contrarian_for_briefing(self, briefing_id: str) -> ContrarianReview | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM contrarian_reviews WHERE briefing_id = ? ORDER BY created_at DESC LIMIT 1",
                (briefing_id,),
            ).fetchone()
        return ContrarianReview.model_validate_json(row["data"]) if row else None

    def save_ingestion_run(self, run: IngestionRun) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ingestion_runs (run_id, data) VALUES (?, ?)",
                (run.run_id, run.model_dump_json()),
            )

    def get_ingestion_runs(self, limit: int = 20) -> list[IngestionRun]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT data FROM ingestion_runs ORDER BY json_extract(data, '$.started_at') DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [IngestionRun.model_validate_json(row["data"]) for row in rows]

    def save_perplexity_research(self, briefing_id: str, data: dict) -> None:
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO perplexity_research (briefing_id, data, created_at)
                VALUES (?, ?, ?)
                """,
                (briefing_id, json.dumps(data), now),
            )

    def get_perplexity_research(self, briefing_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM perplexity_research WHERE briefing_id = ?",
                (briefing_id,),
            ).fetchone()
        return json.loads(row["data"]) if row else None

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> SignalEvent:
        return SignalEvent(
            event_id=row["event_id"],
            ts=datetime.fromisoformat(row["ts"]),
            source=row["source"],
            modality=row["modality"],
            commodity=row["commodity"],
            payload=json.loads(row["payload"]),
        )
