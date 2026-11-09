from curator.queue import DONE, FAILED, PENDING, RetryQueue


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(**kw):
    c = Clock()
    return RetryQueue(":memory:", clock=c, **kw), c


def test_new_job_is_due_at_once():
    q, _ = make()
    jid = q.enqueue("a.jpg")
    assert q.next_due().id == jid


def test_duplicate_open_path_is_not_added_twice():
    q, _ = make()
    assert q.enqueue("a.jpg") == q.enqueue("a.jpg")
    assert q.counts()[PENDING] == 1


def test_done_job_is_not_due_and_path_can_be_added_again():
    q, _ = make()
    jid = q.enqueue("a.jpg")
    q.mark_done(jid)
    assert q.next_due() is None
    assert q.enqueue("a.jpg") != jid


def test_failure_delays_next_try_with_backoff():
    q, c = make(base_delay=30, max_delay=100)
    jid = q.enqueue("a.jpg")
    job = q.mark_failed_attempt(jid, "tv off")
    assert job.attempts == 1 and job.last_error == "tv off"
    assert q.next_due() is None
    c.t += 29
    assert q.next_due() is None
    c.t += 1
    assert q.next_due().id == jid
    q.mark_failed_attempt(jid, "tv off")  # delay 60
    assert q.get(jid).next_attempt_at == c.t + 60
    q.mark_failed_attempt(jid, "tv off")  # delay 120, capped to 100
    assert q.get(jid).next_attempt_at == c.t + 100


def test_gives_up_after_max_attempts_and_can_be_retried():
    q, c = make(max_attempts=2)
    jid = q.enqueue("a.jpg")
    q.mark_failed_attempt(jid, "e")
    c.t += 10_000
    job = q.mark_failed_attempt(jid, "e")
    assert job.status == FAILED
    assert q.next_due() is None
    q.retry(jid)
    assert q.get(jid).status == PENDING and q.next_due().id == jid


def test_oldest_due_job_comes_first():
    q, c = make()
    a = q.enqueue("a.jpg")
    c.t += 1
    q.enqueue("b.jpg")
    assert q.next_due().id == a


def test_jobs_survive_reopen(tmp_path):
    db = tmp_path / "sub" / "q.sqlite3"
    q = RetryQueue(db)
    q.enqueue("a.jpg")
    q.close()
    assert RetryQueue(db).next_due().path == "a.jpg"


def test_counts():
    q, _ = make()
    j = q.enqueue("a.jpg")
    q.enqueue("b.jpg")
    q.mark_done(j)
    assert q.counts() == {PENDING: 1, DONE: 1, FAILED: 0}


def test_old_database_gets_new_columns(tmp_path):
    import sqlite3
    db = tmp_path / "old.sqlite3"
    c = sqlite3.connect(db)
    c.execute("""CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL,
        name TEXT, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at REAL NOT NULL, last_error TEXT, created_at REAL NOT NULL DEFAULT 0)""")
    c.execute("INSERT INTO jobs (path, next_attempt_at) VALUES ('x', 0)")
    c.commit()
    c.close()
    q = RetryQueue(db)
    job = q.next_due()
    assert job.kind == "upload" and job.show_now == 0 and job.by is None
