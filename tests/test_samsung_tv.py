"""Tests for the real TV client, using a fake `samsungtvws` art object. No network."""
import socket
import threading

import pytest

from curator.tv import SamsungTV, TVUnavailable


class FakeArt:
    def __init__(self, fail=None):
        self.fail = fail
        self.calls = []
        self.closed = False

    def open(self):
        if self.fail == "open":
            raise ConnectionRefusedError("refused")
        self.calls.append("open")

    def close(self):
        self.closed = True

    def available(self):
        self.calls.append("available")
        return [{"content_id": "MY_F0001", "content_name": "Sunrise"},
                {"content_id": "MY-C0002", "category_id": "MY-C0002"},
                {"no_id": True}]

    def get_current(self):
        return {"content_id": "MY-C0002"}

    def upload(self, path, **kw):
        self.calls.append(("upload", path, kw))
        return "MY_F0099"

    def select_image(self, cid, show=True):
        self.calls.append(("select", cid, show))

    def delete(self, cid):
        self.calls.append(("delete", cid))
        return True

    def get_thumbnail(self, cid):
        return bytearray(b"jpegbytes") if cid != "none" else None


def make(art):
    return SamsungTV("192.168.1.20", art_factory=lambda: art)


def test_list_art_maps_items_and_current():
    art = FakeArt()
    items = make(art).list_art()
    assert [i.id for i in items] == ["MY_F0001", "MY-C0002"]
    assert items[0].name == "Sunrise" and items[1].name is None
    assert [i.current for i in items] == [False, True]
    assert art.closed


def test_upload_uses_no_mat_and_jpeg(tmp_path):
    art = FakeArt()
    p = tmp_path / "a.jpg"
    p.write_bytes(b"x")
    assert make(art).upload(p) == "MY_F0099"
    call = [c for c in art.calls if isinstance(c, tuple)][0]
    assert call[2] == {"matte": "none", "portrait_matte": "none", "file_type": "jpg"}


def test_select_delete_thumbnail():
    art = FakeArt()
    tv = make(art)
    tv.select("MY_F0001")
    tv.delete("MY_F0001")
    assert ("select", "MY_F0001", True) in art.calls
    assert ("delete", "MY_F0001") in art.calls
    assert tv.thumbnail("x") == b"jpegbytes"
    assert tv.thumbnail("none") is None


def test_connection_errors_become_tv_unavailable():
    art = FakeArt(fail="open")
    with pytest.raises(TVUnavailable):
        make(art).list_art()
    assert art.closed


def test_library_errors_become_tv_unavailable():
    art = FakeArt()
    art.available = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    with pytest.raises(TVUnavailable) as e:
        make(art).list_art()
    assert "RuntimeError" in str(e.value)


def test_is_available_checks_port_only():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert SamsungTV("127.0.0.1", port, art_factory=lambda: None).is_available()
    finally:
        srv.close()
    assert not SamsungTV("127.0.0.1", port, art_factory=lambda: None).is_available()


def test_calls_are_serialized():
    seen = []
    lock_held = threading.Event()

    class Slow(FakeArt):
        def available(self):
            seen.append("start")
            lock_held.wait(0.2)
            seen.append("end")
            return []

    tv = SamsungTV("h", art_factory=lambda: Slow())
    ts = [threading.Thread(target=tv.list_art) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert seen == ["start", "end", "start", "end"]
