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


def test_list_art_drops_duplicate_ids():
    """The real Frame (art API 2.03) lists one photo in several categories."""
    art = FakeArt()
    art.available = lambda: [{"content_id": "MY_F0018", "category_id": "M0002"},
                             {"content_id": "MY_F0025", "category_id": "MY-C0002"},
                             {"content_id": "MY_F0018", "category_id": "MY-C0002"}]
    art.get_current = lambda: {"content_id": "MY_F0018"}
    items = make(art).list_art()
    assert [i.id for i in items] == ["MY_F0018", "MY_F0025"]
    assert [i.current for i in items] == [True, False]


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


# -- turn on (Wake-on-LAN) ----------------------------------------------------

from curator.tv import NO_MAC, normalize_mac, send_magic_packet  # noqa: E402


def test_normalize_mac():
    assert normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac("aabbccddeeff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac("not a mac") is None and normalize_mac("") is None


def test_magic_packet_is_ff_then_mac_16_times():
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(2)
    send_magic_packet("AA:BB:CC:DD:EE:FF", targets=("127.0.0.1",), ports=(rx.getsockname()[1],))
    data, _ = rx.recvfrom(200)
    rx.close()
    assert data == b"\xff" * 6 + bytes.fromhex("AABBCCDDEEFF") * 16


def test_wake_without_a_known_address_says_what_to_do(tmp_path):
    tv = SamsungTV("192.168.1.20", mac_file=tmp_path / "mac.txt")
    with pytest.raises(TVUnavailable) as e:
        tv.wake()
    assert str(e.value) == NO_MAC


def test_wake_sends_to_broadcast_the_tv_and_the_subnet(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr("curator.tv.send_magic_packet", lambda mac, targets: sent.append((mac, list(targets))))
    SamsungTV("192.168.1.20", mac="aa:bb:cc:dd:ee:ff", mac_file=tmp_path / "m").wake()
    assert sent == [("AA:BB:CC:DD:EE:FF", ["255.255.255.255", "192.168.1.20", "192.168.1.205"])]


def test_curator_learns_the_address_while_the_tv_is_on_and_keeps_it(tmp_path):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    mac_file = tmp_path / "data" / "tv-mac.txt"
    calls = []

    def lookup():
        calls.append(1)
        return "aa:bb:cc:dd:ee:ff"

    tv = SamsungTV("127.0.0.1", port=srv.getsockname()[1], mac_file=mac_file, mac_lookup=lookup)
    assert tv.is_available() is True
    assert mac_file.read_text().strip() == "AA:BB:CC:DD:EE:FF"
    assert tv.is_available() is True and len(calls) == 1  # asked only once
    # A new client (for example after a restart) reads the saved address.
    assert SamsungTV("127.0.0.1", mac_file=mac_file).known_mac() == "AA:BB:CC:DD:EE:FF"
    srv.close()


def test_a_failed_address_lookup_does_not_break_is_available(tmp_path):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)

    def lookup():
        raise RuntimeError("no REST on this model")

    tv = SamsungTV("127.0.0.1", port=srv.getsockname()[1], mac_file=tmp_path / "m", mac_lookup=lookup)
    assert tv.is_available() is True and tv.known_mac() is None
    srv.close()


def _closed_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_finds_the_tv_at_a_new_address_by_its_hardware_address():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    port = srv.getsockname()[1]
    macs = {"127.0.0.1": "aa:bb:cc:dd:ee:ff", "127.0.0.3": "11:22:33:44:55:66"}
    scans = []

    def scan(host, p):
        scans.append((host, p))
        return ["127.0.0.3", "127.0.0.1"]

    tv = SamsungTV("127.0.0.9", port, mac="AA:BB:CC:DD:EE:FF", scan=scan, mac_of=macs.get)
    assert tv.is_available() is True and tv.host == "127.0.0.1"
    assert tv.is_available() is True and len(scans) == 1  # the new address answers
    srv.close()


def test_does_not_move_to_a_device_with_a_different_hardware_address():
    scans = []

    def scan(host, p):
        scans.append(host)
        return ["127.0.0.3"]

    tv = SamsungTV("127.0.0.1", _closed_port(), mac="AA:BB:CC:DD:EE:FF", scan=scan,
                   mac_of=lambda h: "11:22:33:44:55:66")
    assert tv.is_available() is False and tv.host == "127.0.0.1"
    assert tv.is_available() is False and len(scans) == 1  # one search each minute


def test_does_not_search_without_a_known_hardware_address():
    tv = SamsungTV("127.0.0.1", _closed_port(), scan=lambda h, p: 1 / 0)
    assert tv.is_available() is False


def test_hosts_with_port_ignores_a_name_that_is_not_an_address():
    from curator.tv import hosts_with_port
    assert hosts_with_port("tv.local", 8002) == []
