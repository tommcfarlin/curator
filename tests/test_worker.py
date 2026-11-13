from curator.queue import DONE, FAILED, PENDING
from curator.tv import FakeTV
from curator.worker import SHOW_EXPIRED, SHOW_MAX_AGE, process_one
from PIL import Image


def make_job(env, name="a.jpg", **kw):
    p = env.s.prepared_dir
    p.mkdir(parents=True, exist_ok=True)
    f = p / name
    Image.new("RGB", (32, 18)).save(f, "JPEG")
    return env.q.enqueue(f, "My photo", **kw)


def test_upload_without_show_now_does_not_change_current(env):
    before = [i for i in env.tv.list_art() if i.current][0].id
    jid = make_job(env)
    assert process_one(env.q, env.tv, env.lib, env.s.thumbs_dir) is True
    assert env.q.get(jid).status == DONE
    assert env.lib.list_pieces() and env.lib.get_mark() is None
    assert [i for i in env.tv.list_art() if i.current][0].id == before


def test_success_uploads_selects_and_records(env):
    jid = make_job(env, show_now=True, by="Anna")
    assert process_one(env.q, env.tv, env.lib, env.s.thumbs_dir) is True
    assert env.q.get(jid).status == DONE
    piece = env.lib.list_pieces()[0]
    assert piece.name == "My photo" and env.lib.has(piece.content_id)
    assert [i for i in env.tv.list_art() if i.current][0].id == piece.content_id
    assert env.lib.get_mark().content_id == piece.content_id and env.lib.get_mark().by == "Anna"


def test_tv_off_keeps_job_waiting_then_recovers(env):
    jid = make_job(env)
    env.tv.online = False
    assert process_one(env.q, env.tv, env.lib, env.s.thumbs_dir) is False
    job = env.q.get(jid)
    assert job.status == PENDING and job.attempts == 1 and "off" in job.last_error
    env.tv.online = True
    env.q.retry_now()
    assert process_one(env.q, env.tv, env.lib, env.s.thumbs_dir) is True
    assert env.q.get(jid).status == DONE


def test_missing_file_fails_at_once(env):
    jid = env.q.enqueue("/nowhere/x.jpg", "x")
    process_one(env.q, env.tv, env.lib, env.s.thumbs_dir)
    assert env.q.get(jid).status == FAILED


def test_no_jobs_returns_false(env):
    assert process_one(env.q, env.tv, env.lib, env.s.thumbs_dir) is False


def test_show_job_selects_and_records_who(env):
    env.q.enqueue_show("SAM-3", "Green Ridge", by="Sam")
    assert process_one(env.q, env.tv, env.lib, env.s.thumbs_dir) is True
    assert [i for i in env.tv.list_art() if i.current][0].id == "SAM-3"
    assert env.lib.get_mark().by == "Sam"


def test_show_job_waits_while_tv_is_off(env):
    jid = env.q.enqueue_show("SAM-2", "Blue Hour")
    env.tv.online = False
    assert process_one(env.q, env.tv, env.lib, env.s.thumbs_dir) is False
    assert env.q.get(jid).status == PENDING and env.lib.get_mark() is None
    env.tv.online = True
    env.q.retry_now()
    assert process_one(env.q, env.tv, env.lib, env.s.thumbs_dir) is True
    assert [i for i in env.tv.list_art() if i.current][0].id == "SAM-2"


def test_show_job_for_missing_photo_fails_at_once(env):
    jid = env.q.enqueue_show("gone")
    process_one(env.q, env.tv, env.lib, env.s.thumbs_dir)
    job = env.q.get(jid)
    assert job.status == FAILED and "no longer" in job.last_error


def test_last_choice_wins(env):
    first = env.q.enqueue_show("SAM-2")
    up = make_job(env, show_now=True)
    second = env.q.enqueue_show("SAM-3")
    assert env.q.get(up).show_now == 0  # an older upload cannot take over later
    import pytest
    with pytest.raises(Exception):
        env.q.get(first)  # the older request was replaced
    while process_one(env.q, env.tv, env.lib, env.s.thumbs_dir):
        pass
    assert [i for i in env.tv.list_art() if i.current][0].id == "SAM-3"
    assert env.q.get(second).status == DONE


def test_old_show_request_is_dropped(env):
    jid = env.q.enqueue_show("SAM-2", "Blue Hour")
    env.tv.online = False
    process_one(env.q, env.tv, env.lib, env.s.thumbs_dir)
    env.tv.online = True
    now = env.q.clock()
    env.q.clock = lambda: now + SHOW_MAX_AGE + 61
    assert process_one(env.q, env.tv, env.lib, env.s.thumbs_dir) is True
    job = env.q.get(jid)
    assert job.status == FAILED and job.last_error == SHOW_EXPIRED
    assert [i for i in env.tv.list_art() if i.current][0].id == "SAM-1"
    # Retry from the phone gives the request one more try.
    env.q.retry(jid)
    assert process_one(env.q, env.tv, env.lib, env.s.thumbs_dir) is True
    assert [i for i in env.tv.list_art() if i.current][0].id == "SAM-2"


def test_old_upload_still_goes_to_the_tv(env):
    jid = make_job(env)
    env.tv.online = False
    process_one(env.q, env.tv, env.lib, env.s.thumbs_dir)
    env.tv.online = True
    now = env.q.clock()
    env.q.clock = lambda: now + SHOW_MAX_AGE + 61
    assert process_one(env.q, env.tv, env.lib, env.s.thumbs_dir) is True
    assert env.q.get(jid).status == DONE


def test_waiting_jobs_run_when_the_tv_comes_back(env):
    assert env.w.retry_if_tv_came_back() is False  # nothing waits, so no TV check
    jid = make_job(env)
    env.tv.online = False
    process_one(env.q, env.tv, env.lib, env.s.thumbs_dir)
    assert env.w.retry_if_tv_came_back() is False
    assert env.q.next_due() is None
    env.tv.online = True
    assert env.w.retry_if_tv_came_back() is True
    assert env.q.next_due().id == jid
    assert env.w.retry_if_tv_came_back() is False  # only on the change
