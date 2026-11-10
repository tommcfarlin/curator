"""Takes jobs from the retry queue and sends them to the TV."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from .library import Library
from .queue import RetryQueue
from .tv import TV, TVUnavailable

log = logging.getLogger("curator.worker")

# A "show" request that waited longer than this is dropped. A photo that
# appears on the TV an hour after the request is a surprise, not a feature.
SHOW_MAX_AGE = 600.0
SHOW_EXPIRED = "The TV did not answer for 10 minutes. Choose the photo again."


def process_one(queue: RetryQueue, tv: TV, library: Library, thumbs_dir: Path) -> bool:
    """Run the next due job. Return True if the job finished (so call again)."""
    job = queue.next_due()
    if job is None:
        return False
    if job.kind == "show":
        return _show(queue, tv, library, job)
    path = Path(job.path)
    if not path.exists():
        queue.mark_failed(job.id, "The prepared image file is missing.")
        return True
    try:
        content_id = tv.upload(path)
        if job.show_now:
            tv.select(content_id)
    except TVUnavailable as exc:
        queue.mark_failed_attempt(job.id, str(exc))
        return False
    except Exception as exc:  # unknown TV errors: retry, then give up
        log.exception("upload failed")
        queue.mark_failed_attempt(job.id, f"{type(exc).__name__}: {exc}")
        return False
    library.add(content_id, job.name or path.stem, thumbs_dir / path.name)
    if job.show_now:
        library.set_mark(content_id, job.by)
    queue.mark_done(job.id)
    return True


def _show(queue: RetryQueue, tv: TV, library: Library, job) -> bool:
    """Tell the TV to show a photo that is already on it."""
    # attempts > 0 keeps a request that the user sent again with Retry.
    if job.attempts > 0 and queue.clock() - job.created_at > SHOW_MAX_AGE:
        queue.mark_failed(job.id, SHOW_EXPIRED)
        return True
    try:
        tv.select(job.target)
    except KeyError:
        queue.mark_failed(job.id, "That photo is no longer on the TV.")
        return True
    except TVUnavailable as exc:
        queue.mark_failed_attempt(job.id, str(exc))
        return False
    except Exception as exc:
        log.exception("show failed")
        queue.mark_failed_attempt(job.id, f"{type(exc).__name__}: {exc}")
        return False
    library.set_mark(job.target, job.by)
    queue.mark_done(job.id)
    return True


class Worker:
    def __init__(self, queue, tv, library, thumbs_dir: Path, interval: float = 5.0):
        self.queue, self.tv, self.library = queue, tv, library
        self.thumbs_dir, self.interval = Path(thumbs_dir), interval
        self._wake = threading.Event()
        self._tv_was_online = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="curator-worker", daemon=True)

    def start(self):
        self._thread.start()

    def wake(self):
        self._wake.set()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def retry_if_tv_came_back(self) -> bool:
        """When the TV starts to answer again, run the waiting jobs at once.

        It asks the TV only while jobs wait, so an idle Curator sends nothing.
        """
        if not self.queue.has_pending():
            self._tv_was_online = False
            return False
        online = bool(self.tv.is_available())
        came_back = online and not self._tv_was_online
        self._tv_was_online = online
        if came_back:
            self.queue.retry_now()
            self._wake.set()
        return came_back

    def _run(self):
        while not self._stop.is_set():
            try:
                while process_one(self.queue, self.tv, self.library, self.thumbs_dir):
                    pass
            except Exception:
                log.exception("worker loop error")
            try:
                self.retry_if_tv_came_back()
            except Exception:
                log.exception("TV check failed")
            self._wake.wait(self.interval)
            self._wake.clear()
