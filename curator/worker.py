"""Takes jobs from the retry queue and sends them to the TV."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from .library import Library
from .queue import RetryQueue
from .tv import TV, TVUnavailable

log = logging.getLogger("curator.worker")


def process_one(queue: RetryQueue, tv: TV, library: Library, thumbs_dir: Path) -> bool:
    """Run the next due job. Return True if the job finished (so call again)."""
    job = queue.next_due()
    if job is None:
        return False
    path = Path(job.path)
    if not path.exists():
        queue.mark_failed(job.id, "The prepared image file is missing.")
        return True
    try:
        content_id = tv.upload(path)
        tv.select(content_id)
    except TVUnavailable as exc:
        queue.mark_failed_attempt(job.id, str(exc))
        return False
    except Exception as exc:  # unknown TV errors: retry, then give up
        log.exception("upload failed")
        queue.mark_failed_attempt(job.id, f"{type(exc).__name__}: {exc}")
        return False
    library.add(content_id, job.name or path.stem, thumbs_dir / path.name)
    queue.mark_done(job.id)
    return True


class Worker:
    def __init__(self, queue, tv, library, thumbs_dir: Path, interval: float = 5.0):
        self.queue, self.tv, self.library = queue, tv, library
        self.thumbs_dir, self.interval = Path(thumbs_dir), interval
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="curator-worker", daemon=True)

    def start(self):
        self._thread.start()

    def wake(self):
        self._wake.set()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                while process_one(self.queue, self.tv, self.library, self.thumbs_dir):
                    pass
            except Exception:
                log.exception("worker loop error")
            self._wake.wait(self.interval)
            self._wake.clear()
