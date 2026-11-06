from curator.queue import DONE, FAILED, PENDING
from curator.tv import FakeTV
from curator.worker import process_one
from PIL import Image


def make_job(env, name="a.jpg"):
    p = env.s.prepared_dir
    p.mkdir(parents=True, exist_ok=True)
    f = p / name
    Image.new("RGB", (32, 18)).save(f, "JPEG")
    return env.q.enqueue(f, "My photo")


def test_success_uploads_selects_and_records(env):
    jid = make_job(env)
    assert process_one(env.q, env.tv, env.lib, env.s.thumbs_dir) is True
    assert env.q.get(jid).status == DONE
    piece = env.lib.list_pieces()[0]
    assert piece.name == "My photo" and env.lib.has(piece.content_id)
    assert [i for i in env.tv.list_art() if i.current][0].id == piece.content_id


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
