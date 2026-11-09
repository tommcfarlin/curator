"""Record of the artwork that Curator uploaded. Only these pieces can be deleted."""
from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Piece:
    content_id: str
    name: str
    thumb_path: Optional[str]
    created_at: float


@dataclass(frozen=True)
class Mark:
    content_id: str
    by: Optional[str]
    at: float


class Library:
    def __init__(self, db_path: str | Path):
        self._lock = threading.RLock()
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self._lock:
            self.db.execute(
                """CREATE TABLE IF NOT EXISTS art (
                    content_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    thumb_path TEXT, created_at REAL NOT NULL)"""
            )
            self.db.execute(
                """CREATE TABLE IF NOT EXISTS mark (
                    id INTEGER PRIMARY KEY CHECK (id = 1), content_id TEXT NOT NULL,
                    by TEXT, at REAL NOT NULL)"""
            )
            self.db.commit()

    def set_mark(self, content_id: str, by: Optional[str] = None) -> None:
        """Record that someone chose this photo to show. Only one is chosen at a time."""
        with self._lock:
            self.db.execute(
                "INSERT OR REPLACE INTO mark (id, content_id, by, at) VALUES (1, ?, ?, ?)",
                (content_id, by, time.time()),
            )
            self.db.commit()

    def get_mark(self) -> Optional[Mark]:
        with self._lock:
            row = self.db.execute("SELECT content_id, by, at FROM mark WHERE id=1").fetchone()
        return Mark(**dict(row)) if row else None

    def add(self, content_id: str, name: str, thumb_path: str | Path | None = None) -> None:
        with self._lock:
            self.db.execute(
                "INSERT OR REPLACE INTO art VALUES (?, ?, ?, ?)",
                (content_id, name, str(thumb_path) if thumb_path else None, time.time()),
            )
            self.db.commit()

    def get(self, content_id: str) -> Optional[Piece]:
        with self._lock:
            row = self.db.execute("SELECT * FROM art WHERE content_id=?", (content_id,)).fetchone()
        return Piece(**dict(row)) if row else None

    def has(self, content_id: str) -> bool:
        return self.get(content_id) is not None

    def remove(self, content_id: str) -> None:
        with self._lock:
            self.db.execute("DELETE FROM art WHERE content_id=?", (content_id,))
            self.db.commit()

    def list_pieces(self) -> list[Piece]:
        with self._lock:
            rows = self.db.execute("SELECT * FROM art ORDER BY created_at DESC").fetchall()
        return [Piece(**dict(r)) for r in rows]
