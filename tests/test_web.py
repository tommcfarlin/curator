import io

from PIL import Image

from curator.worker import process_one
from .conftest import png_bytes


def post(env, data=None, name="photo.png", **form):
    data = png_bytes() if data is None else data
    return env.client.post(
        "/api/upload", data={"file": (io.BytesIO(data), name), **form},
        content_type="multipart/form-data",
    )


def run_worker(env):
    while process_one(env.q, env.tv, env.lib, env.s.thumbs_dir):
        pass


def test_index_page_is_served(env):
    r = env.client.get("/")
    assert r.status_code == 200 and b"Curator" in r.data


def test_upload_prepares_exact_size_and_queues(env):
    r = post(env, png_bytes((1000, 2000)), mode="crop", fx="50", fy="0")
    assert r.status_code == 201
    job = env.q.get(r.json["job"])
    with Image.open(job.path) as im:
        assert im.size == (320, 180) and im.format == "JPEG"
    assert job.name == "photo"
    assert list(env.s.incoming_dir.iterdir()) == []  # temp file is gone


def test_upload_rejects_non_image(env):
    r = post(env, b"not an image", name="x.png")
    assert r.status_code == 400 and r.json["error"] == "bad_image"
    assert list(env.s.incoming_dir.iterdir()) == [] and env.q.counts()["pending"] == 0


def test_upload_rejects_missing_file_and_bad_mode(env):
    assert env.client.post("/api/upload", data={}).status_code == 400
    assert post(env, mode="stretch").status_code == 400
    assert post(env, fx="abc").status_code == 400


def test_upload_too_big(env):
    env.app.config["MAX_CONTENT_LENGTH"] = 1000
    r = post(env, png_bytes((600, 600)))
    assert r.status_code == 413 and r.json["error"] == "too_big"


def test_phone_file_name_is_never_used_as_path(env):
    r = post(env, name="../../etc/evil.png")
    assert r.status_code == 201
    assert env.q.get(r.json["job"]).name == "evil"
    assert all(p.parent == env.s.prepared_dir for p in map(__import__("pathlib").Path, [env.q.get(r.json["job"]).path]))


def test_status_states_through_the_flow(env):
    jid = post(env).json["job"]
    st = env.client.get("/api/status").json
    assert st["tv_online"] and st["fake"] and st["jobs"][0]["state"] == "sending"
    env.tv.online = False
    process_one(env.q, env.tv, env.lib, env.s.thumbs_dir)
    assert env.client.get("/api/status").json["jobs"][0]["state"] == "waiting"
    env.client.post("/api/dev/tv", json={"online": True})
    run_worker(env)
    assert env.client.get("/api/status").json["jobs"][0]["state"] == "done"
    assert env.client.get(env.client.get("/api/status").json["jobs"][0]["thumb"]).status_code == 200


def test_art_list_marks_mine_vs_samsung(env):
    post(env, name="mine.png")
    run_worker(env)
    art = env.client.get("/api/art").json["art"]
    mine = [a for a in art if a["mine"]]
    assert len(art) == 4 and len(mine) == 1 and mine[0]["name"] == "mine" and not mine[0]["current"]
    assert all(not a["mine"] for a in art if a["id"].startswith("SAM-"))


def test_cannot_delete_samsung_art(env):
    r = env.client.delete("/api/art/SAM-1")
    assert r.status_code == 403 and r.json["error"] == "not_yours"
    assert any(a.id == "SAM-1" for a in env.tv.list_art())


def test_can_delete_own_art_and_unknown_id_is_refused(env):
    post(env)
    run_worker(env)
    cid = [a for a in env.client.get("/api/art").json["art"] if a["mine"]][0]["id"]
    assert env.client.delete(f"/api/art/{cid}").status_code == 200
    assert all(a.id != cid for a in env.tv.list_art())
    assert env.client.delete("/api/art/nope").status_code == 403


def current(env):
    return [a for a in env.client.get("/api/art").json["art"] if a["current"]][0]


def test_show_is_queued_then_changes_current_piece(env):
    r = env.client.post("/api/art/SAM-2/show", json={"by": "  Anna  "})
    assert r.status_code == 202
    art = {a["id"]: a for a in env.client.get("/api/art").json["art"]}
    assert art["SAM-2"]["queued"] is True and art["SAM-1"]["current"] is True
    run_worker(env)
    c = current(env)
    assert c["id"] == "SAM-2" and c["chosen_by"] == "Anna" and c["chosen_at"]
    assert c["queued"] is False
    assert sum(a["current"] for a in env.client.get("/api/art").json["art"]) == 1


def test_upload_does_not_take_over_unless_asked(env):
    post(env)
    run_worker(env)
    assert current(env)["id"] == "SAM-1"
    post(env, show_now="1", by="Tom")
    run_worker(env)
    c = current(env)
    assert c["mine"] and c["chosen_by"] == "Tom"


def test_show_for_missing_photo_ends_as_failed_job(env):
    assert env.client.post("/api/art/zzz/show").status_code == 202
    run_worker(env)
    job = env.client.get("/api/status").json["jobs"][0]
    assert job["state"] == "failed" and job["kind"] == "show"


def test_tv_off_gives_503_for_art_calls(env):
    env.tv.online = False
    assert env.client.get("/api/art").status_code == 503
    assert env.client.post("/api/art/SAM-1/show").status_code == 202  # waits in the queue
    run_worker(env)
    job = env.client.get("/api/status").json["jobs"][0]
    assert job["state"] == "waiting" and job["kind"] == "show"


def test_art_deleted_on_tv_is_forgotten(env):
    post(env)
    run_worker(env)
    cid = env.lib.list_pieces()[0].content_id
    env.tv.delete(cid)
    env.client.get("/api/art")
    assert not env.lib.has(cid)


def test_failed_job_can_be_retried(env):
    jid = env.q.enqueue("/nowhere.jpg", "x")
    process_one(env.q, env.tv, env.lib, env.s.thumbs_dir)
    assert env.q.get(jid).status == "failed"
    assert env.client.post(f"/api/jobs/{jid}/retry").status_code == 200
    assert env.q.get(jid).status == "pending"


def test_thumb_route_rejects_bad_stem(env):
    assert env.client.get("/thumb/..%2Fsecret").status_code == 404
