"""End-to-end tests: the real SamsungTV client and the real samsungtvws library,
against a simulated Frame (tests/sim_tv.py). No real TV is involved."""
import io
import logging
import stat

import pytest
from PIL import Image

from curator.config import Settings
from curator.library import Library
from curator.queue import DONE, RetryQueue
from curator.tv import SamsungTV, TVUnavailable
from curator.web import create_app
from curator.worker import process_one

from .sim_tv import TOKEN, SimFrame, SimTVServer


@pytest.fixture
def sim():
    with SimTVServer() as srv:
        yield srv


def client(sim, tmp_path, **kw):
    return SamsungTV("127.0.0.1", sim.port, tmp_path / "config" / "token.txt", timeout=5, **kw)


def jpeg(tmp_path, color="red"):
    p = tmp_path / "photo.jpg"
    Image.new("RGB", (384, 216), color).save(p, "JPEG")
    return p


def test_first_connection_pairs_and_saves_private_token(sim, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    tv = client(sim, tmp_path)
    assert not tv.is_paired()
    items = tv.list_art()
    assert tv.is_paired()
    tok = tmp_path / "config" / "token.txt"
    assert tok.read_text() == TOKEN
    assert stat.S_IMODE(tok.stat().st_mode) == 0o600
    assert TOKEN not in caplog.text  # never logged
    assert [i.id for i in items] == ["SAM-S00001", "SAM-S00002", "SAM-S00003"]
    assert [i.current for i in items] == [True, False, False]


def test_saved_token_is_sent_on_the_real_tv_port(tmp_path):
    """On port 8002 (the real TV) the library must send the saved token, or the TV asks
    for Allow again on every call. The simulator uses plain ws, so check the URL itself."""
    tok = tmp_path / "token.txt"
    tok.write_text("ABC123")
    art = SamsungTV("192.168.1.20", 8002, tok)._new_art()
    url = art._format_websocket_url("com.samsung.art-app")
    assert url.startswith("wss://192.168.1.20:8002/api/v2/channels/com.samsung.art-app")
    assert "token=ABC123" in url and "name=" in url


def test_deny_on_the_tv_gives_clear_message(tmp_path):
    with SimTVServer(SimFrame(allow=False)) as srv:
        with pytest.raises(TVUnavailable) as e:
            client(srv, tmp_path).list_art()
    assert "Allow" in str(e.value) and not (tmp_path / "config" / "token.txt").exists()


def test_upload_select_thumbnail_delete(sim, tmp_path):
    tv = client(sim, tmp_path)
    src = jpeg(tmp_path)
    cid = tv.upload(src)
    assert sim.frame.pieces[cid].data == src.read_bytes()
    assert ("uploaded", cid, "none", "jpg") in sim.frame.log  # no mat, JPEG
    tv.select(cid)
    assert [i.id for i in tv.list_art() if i.current] == [cid]
    with Image.open(io.BytesIO(tv.thumbnail(cid))) as im:
        assert im.format == "JPEG"
    tv.delete(cid)
    assert cid not in sim.frame.pieces


def test_select_unknown_photo_is_an_error(sim, tmp_path):
    with pytest.raises(TVUnavailable):
        client(sim, tmp_path).select("NOPE")


def test_tv_off_is_unavailable(tmp_path):
    with SimTVServer() as srv:
        port = srv.port
    tv = SamsungTV("127.0.0.1", port, tmp_path / "t.txt", timeout=2)
    assert tv.is_available() is False
    with pytest.raises(TVUnavailable):
        tv.list_art()


def test_full_app_flow_with_real_client(sim, tmp_path):
    """Phone upload -> queue -> worker -> TV -> On the TV list, with the real client."""
    s = Settings(data_dir=tmp_path / "data", width=384, height=216)
    tv = client(sim, tmp_path)
    q, lib = RetryQueue(":memory:"), Library(":memory:")
    app = create_app(s, tv, q, lib, None)
    c = app.test_client()
    buf = io.BytesIO()
    Image.new("RGB", (800, 450), "blue").save(buf, "PNG")
    r = c.post("/api/upload", data={"file": (io.BytesIO(buf.getvalue()), "Beach.png"), "show_now": "1", "by": "Tom"},
               content_type="multipart/form-data")
    assert r.status_code == 201
    assert process_one(q, tv, lib, s.thumbs_dir) is True
    assert q.get(r.json["job"]).status == DONE
    art = {a["name"]: a for a in c.get("/api/art").json["art"]}
    assert art["Beach"]["mine"] and art["Beach"]["current"] and art["Beach"]["chosen_by"] == "Tom"
    cid = art["Beach"]["id"]
    assert c.get(f"/api/art/{cid}/thumb").status_code == 200
    assert c.delete(f"/api/art/{cid}").status_code == 200
    assert cid not in sim.frame.pieces


def test_probe_steps_against_simulator(sim, tmp_path, capsys):
    from curator import probe

    cfg = tmp_path / "local.toml"
    cfg.write_text(f'[tv]\nhost = "127.0.0.1"\nport = {sim.port}\ntoken_file = "{tmp_path}/token.txt"\n'
                   f'[storage]\ndata_dir = "{tmp_path}/data"\n')
    run = lambda *a: probe.main(["--config", str(cfg), *a])
    assert run() == 0
    out = capsys.readouterr().out
    assert "Press Allow" in out and "Pieces on the TV: 3" in out and "MY-C0004 = 3" in out
    assert (tmp_path / "token.txt").exists() and list((tmp_path / "data" / "probe").glob("*-list.json"))
    assert run("--upload-test") == 0
    out = capsys.readouterr().out
    cid = out.split("Content id: ")[1].split()[0]
    assert sim.frame.current != cid  # uploaded, not shown
    assert run("--show", cid) == 0 and sim.frame.current == cid
    assert run("--delete", cid) == 0 and cid not in sim.frame.pieces


def test_probe_reports_tv_off(tmp_path, capsys):
    from curator import probe

    with SimTVServer() as srv:
        port = srv.port
    cfg = tmp_path / "local.toml"
    cfg.write_text(f'[tv]\nhost = "127.0.0.1"\nport = {port}\ntoken_file = "{tmp_path}/t.txt"\n'
                   f'[storage]\ndata_dir = "{tmp_path}/data"\n')
    assert probe.main(["--config", str(cfg)]) == 1
    assert "does not answer" in capsys.readouterr().out
