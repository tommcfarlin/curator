"""Retry queue stored in SQLite (standard library only).

A job is one prepared image waiting to go to the TV. When the TV is off,
the job stays in the queue and runs again later with growing delays.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

PENDING, DONE, FAILED = "pending", "done", "failed"


@dataclass(frozen=True)
class Job:
    id: int
    path: str
    status: str
    attempts: int
    next_attempt_at: float
    last_error: Optional[str]


class RetryQueue:
    def __init__(
        self,
        db_path: str | Path,
        max_attempts: int = 12,
        base_delay: float = 30.0,
        max_delay: float = 3600.0,
        clock: Callable[[], float] = time.time,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.clock = clock
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path))
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL,
                last_error TEXT)"""
        )
        self.db.commit()

    @staticmethod
    def _job(row: sqlite3.Row) -> Job:
        return Job(**{k: row[k] for k in row.keys()})

    def enqueue(self, path: str | Path) -> int:
        """Add a job, or return the id of an open job for the same path."""
        row = self.db.execute(
            "SELECT id FROM jobs WHERE path=? AND status=?", (str(path), PENDING)
        ).fetchone()
        if row:
            return row["id"]
        cur = self.db.execute(
            "INSERT INTO jobs (path, next_attempt_at) VALUES (?, ?)",
            (str(path), self.clock()),
        )
        self.db.commit()
        return cur.lastrowid

    def get(self, job_id: int) -> Job:
        return self._job(self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def next_due(self) -> Optional[Job]:
        row = self.db.execute(
            "SELECT * FROM jobs WHERE status=? AND next_attempt_at<=? "
            "ORDER BY next_attempt_at, id LIMIT 1",
            (PENDING, self.clock()),
        ).fetchone()
        return self._job(row) if row else None

    def mark_done(self, job_id: int) -> None:
        self.db.execute("UPDATE jobs SET status=?, last_error=NULL WHERE id=?", (DONE, job_id))
        self.db.commit()

    def mark_failed_attempt(self, job_id: int, error: str) -> Job:
        """Record a failed try. Retry later, or give up after max_attempts."""
        attempts = self.get(job_id).attempts + 1
        if attempts >= self.max_attempts:
            self.db.execute(
                "UPDATE jobs SET status=?, attempts=?, last_error=? WHERE id=?",
                (FAILED, attempts, error, job_id),
            )
        else:
            delay = min(self.base_delay * 2 ** (attempts - 1), self.max_delay)
            self.db.execute(
                "UPDATE jobs SET attempts=?, last_error=?, next_attempt_at=? WHERE id=?",
                (attempts, error, self.clock() + delay, job_id),
            )
        self.db.commit()
        return self.get(job_id)

    def retry(self, job_id: int) -> None:
        """Put a failed job back in the queue, for the user to try again."""
        self.db.execute(
            "UPDATE jobs SET status=?, attempts=0, next_attempt_at=? WHERE id=?",
            (PENDING, self.clock(), job_id),
        )
        self.db.commit()

    def counts(self) -> dict[str, int]:
        rows = self.db.execute("SELECT status, COUNT(*) n FROM jobs GROUP BY status").fetchall()
        out = {PENDING: 0, DONE: 0, FAILED: 0}
        out.update({r["status"]: r["n"] for r in rows})
        return out

    def close(self) -> None:
        self.db.close()
