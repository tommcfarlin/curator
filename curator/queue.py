"""Retry queue stored in SQLite (standard library only).

A job is one prepared image waiting to go to the TV. When the TV is off,
the job stays in the queue and runs again later with growing delays.
The queue is safe to use from the web threads and the worker thread.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

PENDING, DONE, FAILED = "pending", "done", "failed"


@dataclass(frozen=True)
class Job:
    id: int
    path: str
    name: Optional[str]
    status: str
    attempts: int
    next_attempt_at: float
    last_error: Optional[str]
    created_at: float
    kind: str = "upload"  # "upload" sends a photo. "show" tells the TV to show one.
    show_now: int = 0  # for uploads: show the photo once it is on the TV
    target: Optional[str] = None  # for "show" jobs: the content id
    by: Optional[str] = None  # who asked (a name typed on the phone, no login)


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
        self._lock = threading.RLock()
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self._lock:
            self.db.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    name TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL,
                    last_error TEXT,
                    created_at REAL NOT NULL DEFAULT 0)"""
            )
            have = {r["name"] for r in self.db.execute("PRAGMA table_info(jobs)")}
            for col, ddl in (
                ("kind", "TEXT NOT NULL DEFAULT 'upload'"),
                ("show_now", "INTEGER NOT NULL DEFAULT 0"),
                ("target", "TEXT"),
                ("by", "TEXT"),
            ):
                if col not in have:
                    self.db.execute(f'ALTER TABLE jobs ADD COLUMN "{col}" {ddl}')
            self.db.commit()

    @staticmethod
    def _job(row: sqlite3.Row) -> Job:
        return Job(**{k: row[k] for k in row.keys()})

    def enqueue(self, path: str | Path, name: Optional[str] = None,
                show_now: bool = False, by: Optional[str] = None) -> int:
        """Add a job, or return the id of an open job for the same path."""
        with self._lock:
            row = self.db.execute(
                "SELECT id FROM jobs WHERE path=? AND status=?", (str(path), PENDING)
            ).fetchone()
            if row:
                return row["id"]
            now = self.clock()
            cur = self.db.execute(
                'INSERT INTO jobs (path, name, next_attempt_at, created_at, show_now, "by") '
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(path), name, now, now, int(show_now), by),
            )
            self.db.commit()
            return cur.lastrowid

    def enqueue_show(self, content_id: str, name: Optional[str] = None,
                     by: Optional[str] = None) -> int:
        """Ask the TV to show one photo. The last request wins.

        Older waiting requests are removed. Waiting uploads lose their
        show_now flag, so they cannot replace this choice later.
        """
        with self._lock:
            self.db.execute("DELETE FROM jobs WHERE kind='show' AND status=?", (PENDING,))
            self.db.execute(
                "UPDATE jobs SET show_now=0 WHERE kind='upload' AND status=?", (PENDING,)
            )
            now = self.clock()
            cur = self.db.execute(
                'INSERT INTO jobs (path, name, next_attempt_at, created_at, kind, target, "by") '
                "VALUES (?, ?, ?, ?, 'show', ?, ?)",
                (f"show:{content_id}", name, now, now, content_id, by),
            )
            self.db.commit()
            return cur.lastrowid

    def pending_show_target(self) -> Optional[str]:
        with self._lock:
            row = self.db.execute(
                "SELECT target FROM jobs WHERE kind='show' AND status=? ORDER BY id DESC LIMIT 1",
                (PENDING,),
            ).fetchone()
        return row["target"] if row else None

    def get(self, job_id: int) -> Job:
        with self._lock:
            return self._job(self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def list_jobs(self, limit: int = 50) -> list[Job]:
        """Newest first."""
        with self._lock:
            rows = self.db.execute(
                "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._job(r) for r in rows]

    def next_due(self) -> Optional[Job]:
        with self._lock:
            row = self.db.execute(
                "SELECT * FROM jobs WHERE status=? AND next_attempt_at<=? "
                "ORDER BY next_attempt_at, id LIMIT 1",
                (PENDING, self.clock()),
            ).fetchone()
            return self._job(row) if row else None

    def mark_done(self, job_id: int) -> None:
        with self._lock:
            self.db.execute("UPDATE jobs SET status=?, last_error=NULL WHERE id=?", (DONE, job_id))
            self.db.commit()

    def mark_failed(self, job_id: int, error: str) -> None:
        """Give up on a job at once (for errors that a retry cannot fix)."""
        with self._lock:
            self.db.execute(
                "UPDATE jobs SET status=?, last_error=? WHERE id=?", (FAILED, error, job_id)
            )
            self.db.commit()

    def mark_failed_attempt(self, job_id: int, error: str) -> Job:
        """Record a failed try. Retry later, or give up after max_attempts."""
        with self._lock:
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
        with self._lock:
            self.db.execute(
                "UPDATE jobs SET status=?, attempts=0, next_attempt_at=? WHERE id=?",
                (PENDING, self.clock(), job_id),
            )
            self.db.commit()

    def retry_now(self) -> None:
        """Make every waiting job due now (for when the TV comes back)."""
        with self._lock:
            self.db.execute(
                "UPDATE jobs SET next_attempt_at=? WHERE status=?", (self.clock(), PENDING)
            )
            self.db.commit()

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self.db.execute("SELECT status, COUNT(*) n FROM jobs GROUP BY status").fetchall()
        out = {PENDING: 0, DONE: 0, FAILED: 0}
        out.update({r["status"]: r["n"] for r in rows})
        return out

    def close(self) -> None:
        with self._lock:
            self.db.close()
