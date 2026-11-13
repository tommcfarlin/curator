"""The TV side. `TV` is the small interface the rest of Curator uses.

`FakeTV` is for development and tests. `SamsungTV` talks to the real Frame.
"""
from __future__ import annotations

import io
import logging
import os
import re
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from PIL import Image


def _close_quietly(art) -> None:
    try:
        art.close()
    except Exception:
        pass


class TVUnavailable(Exception):
    """The TV is off, unreachable, or refused the connection."""


# samsungtvws logs the pairing token at INFO level ("New token ..."). Keep it out of our logs.
logging.getLogger("samsungtvws").setLevel(logging.WARNING)

DENIED = ("The TV did not allow Curator. On the TV, open Settings > General > External Device "
          "Manager > Device Connection Manager > Device List, and set Curator to Allow.")


@dataclass(frozen=True)
class ArtItem:
    id: str
    name: Optional[str]
    current: bool


_MAC = re.compile(r"^[0-9a-f]{2}([:-]?[0-9a-f]{2}){5}$", re.I)


def normalize_mac(value: str) -> Optional[str]:
    """Return a hardware address as AA:BB:CC:DD:EE:FF, or None if it is not one."""
    value = (value or "").strip()
    if not _MAC.match(value):
        return None
    digits = re.sub(r"[^0-9a-f]", "", value.lower())
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2)).upper()


log = logging.getLogger("curator.tv")


def _port_answers(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def hosts_with_port(host: str, port: int, timeout: float = 0.7) -> list[str]:
    """Return the addresses near `host` (same x.y.z) where `port` answers."""
    parts = host.split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return []
    near = [".".join(parts[:3] + [str(i)]) for i in range(1, 255)]
    with ThreadPoolExecutor(max_workers=64) as pool:
        hits = list(pool.map(lambda h: _port_answers(h, port, timeout), near))
    return [h for h, ok in zip(near, hits) if ok]


class TV(Protocol):
    def is_available(self) -> bool: ...
    def list_art(self) -> list[ArtItem]: ...
    def upload(self, path: Path) -> str: ...
    def select(self, content_id: str) -> None: ...
    def delete(self, content_id: str) -> None: ...
    def thumbnail(self, content_id: str) -> Optional[bytes]: ...


class SamsungTV:
    """The real Frame, through the community `samsungtvws` library (LGPL-3.0).

    It opens one short WebSocket connection per call and closes it again.
    That is slower than a long connection, but it survives a TV that sleeps
    or restarts. Calls are serialized with a lock because the TV handles one
    art session at a time.

    The first connection makes the TV show an Allow prompt. The pairing
    token goes into `token_file`, which git ignores.

    Method names were checked against samsungtvws 3.0.7. Samsung can change
    the unofficial API in any update. Errors from the library become
    `TVUnavailable` so the retry queue handles them.
    """

    def __init__(self, host: str, port: int = 8002, token_file: Optional[Path] = None,
                 name: str = "Curator", timeout: float = 15.0, art_factory=None,
                 key_press_delay: float = 0.0, mac: str = "", mac_file: Optional[Path] = None,
                 mac_lookup=None, scan=None, mac_of=None, deadline: float = 90.0):
        self.deadline = deadline  # the longest time one TV request can take, uploads included
        self._scan = scan or hosts_with_port
        self._mac_of = mac_of or self._ask_host_for_mac
        self._search_tried = 0.0
        self.mac_setting = normalize_mac(mac)
        self.mac_file = Path(mac_file) if mac_file else None
        self._mac_lookup = mac_lookup or self._ask_tv_for_mac
        self._mac_tried = 0.0
        self.host = host
        self.port = port
        self.token_file = Path(token_file) if token_file else None
        self.name = name
        self.timeout = timeout
        self._art_factory = art_factory
        self.key_press_delay = key_press_delay
        self._lock = threading.RLock()

    # -- connection helpers -------------------------------------------------

    def _new_art(self):
        if self._art_factory:
            return self._art_factory()
        from samsungtvws.art import SamsungTVArt

        if self.token_file:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
        # key_press_delay is a pause after every command, meant for remote key presses.
        # Art requests wait for the TV's reply anyway, so the default 1 s only adds lag.
        return SamsungTVArt(host=self.host, port=self.port, timeout=self.timeout, name=self.name,
                            token_file=str(self.token_file) if self.token_file else None,
                            key_press_delay=self.key_press_delay)

    def _run(self, fn):
        """Open a connection, run `fn(art)`, close it. Map failures to TVUnavailable."""
        with self._lock:
            try:
                art = self._new_art()
            except ImportError as e:
                raise TVUnavailable(f"samsungtvws is not installed: {e}") from e
            # The library waits for its reply in a loop that skips other TV messages,
            # so its socket timeout can never fire. Close the connection at a hard limit.
            watchdog = threading.Timer(self.deadline, lambda: _close_quietly(art))
            watchdog.daemon = True
            watchdog.start()
            try:
                art.open()
                self._protect_token()
                return fn(art)
            except TVUnavailable:
                raise
            except (OSError, TimeoutError) as e:
                raise TVUnavailable(f"Cannot reach the TV: {e}") from e
            except Exception as e:  # library and websocket errors
                if type(e).__name__ == "UnauthorizedError":
                    raise TVUnavailable(DENIED) from e
                raise TVUnavailable(f"The TV did not accept the request: {type(e).__name__}: {e}") from e
            finally:
                watchdog.cancel()
                _close_quietly(art)

    def _protect_token(self) -> None:
        """The token lets anyone on the network control the TV. Only the owner may read it."""
        if self.token_file and self.token_file.exists():
            try:
                os.chmod(self.token_file, 0o600)
            except OSError:
                pass

    def is_paired(self) -> bool:
        return bool(self.token_file and self.token_file.exists() and self.token_file.read_text().strip())

    # -- the TV interface ---------------------------------------------------

    def is_available(self) -> bool:
        """A quick check that the TV port answers. It does not trigger the Allow prompt."""
        try:
            with socket.create_connection((self.host, self.port), timeout=2):
                pass
        except OSError:
            return self._find_moved_tv()
        self._learn_mac()
        return True

    def _find_moved_tv(self) -> bool:
        """The router can give the TV a new address. Search for the TV by its
        hardware address, at most one time each minute. It needs a known address
        (see `known_mac`) and a TV that is on."""
        mac = self.known_mac()
        if not mac or time.monotonic() - self._search_tried < 60:
            return False
        self._search_tried = time.monotonic()
        for host in self._scan(self.host, self.port):
            if host == self.host:
                continue
            try:
                found = normalize_mac(self._mac_of(host) or "")
            except Exception:
                continue
            if found == mac:
                log.warning("The TV moved from %s to %s. Reserve an address for the TV "
                            "on the router.", self.host, host)
                self.host = host
                return True
        return False

    # -- hardware address (finds the TV after its address changes) ------------------------------------------------------------

    def known_mac(self) -> Optional[str]:
        if self.mac_setting:
            return self.mac_setting
        if self.mac_file and self.mac_file.exists():
            return normalize_mac(self.mac_file.read_text())
        return None

    def _ask_host_for_mac(self, host: str) -> Optional[str]:
        from samsungtvws import SamsungTVWS
        info = SamsungTVWS(host, timeout=3).rest_device_info()
        return (info.get("device") or {}).get("wifiMac")

    def _ask_tv_for_mac(self) -> Optional[str]:
        return self._ask_host_for_mac(self.host)

    def _learn_mac(self) -> None:
        """While the TV is on, ask it for its hardware address once and keep it."""
        if not self.mac_file or self.known_mac() or time.monotonic() - self._mac_tried < 300:
            return
        self._mac_tried = time.monotonic()
        try:
            mac = normalize_mac(self._mac_lookup() or "")
        except Exception:
            return
        if mac:
            self.mac_file.parent.mkdir(parents=True, exist_ok=True)
            self.mac_file.write_text(mac + "\n")

    def list_art(self) -> list[ArtItem]:
        def go(art):
            items = art.available()
            cur = art.get_current() or {}
            cur_id = cur.get("content_id") if isinstance(cur, dict) else None
            # The real TV lists one photo in several categories (for example
            # M0002 and MY-C0002), so keep the first row for each content ID.
            out, seen = [], set()
            for i in items:
                cid = i.get("content_id") if isinstance(i, dict) else None
                if cid and cid not in seen:
                    seen.add(cid)
                    out.append(ArtItem(cid, i.get("content_name") or None, cid == cur_id))
            return out
        return self._run(go)

    def upload(self, path: Path) -> str:
        # No mat, as decided. Curator already prepared an exact 16:9 JPEG.
        return self._run(lambda art: art.upload(str(path), matte="none", portrait_matte="none",
                                                file_type="jpg"))

    def select(self, content_id: str) -> None:
        self._run(lambda art: art.select_image(content_id, show=True))

    def delete(self, content_id: str) -> None:
        self._run(lambda art: art.delete(content_id))

    def thumbnail(self, content_id: str) -> Optional[bytes]:
        def go(art):
            data = art.get_thumbnail(content_id)
            return bytes(data) if data else None
        return self._run(go)


_SEED = [("Evening Lake", "#2b5876", "#4e4376"), ("Blue Hour", "#355c7d", "#6c5b7b"),
         ("Green Ridge", "#134e5e", "#71b280")]


def _gradient(c1: str, c2: str, size=(480, 270)) -> bytes:
    a, b = Image.new("RGB", (1, 1), c1).getpixel((0, 0)), Image.new("RGB", (1, 1), c2).getpixel((0, 0))
    im = Image.new("RGB", size)
    px = im.load()
    for x in range(size[0]):
        for y in range(size[1]):
            t = (x / size[0] + y / size[1]) / 2
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=80)
    return out.getvalue()


class FakeTV:
    """An in-memory TV. Set `online = False` to act like a TV that is off."""

    def __init__(self, online: bool = True, seed: bool = True):
        self.online = online
        self._lock = threading.RLock()
        self._art: dict[str, tuple[str, bytes]] = {}
        self._current: Optional[str] = None
        self.uploads: list[Path] = []
        if seed:
            for i, (name, c1, c2) in enumerate(_SEED, 1):
                self._art[f"SAM-{i}"] = (name, _gradient(c1, c2))
            self._current = "SAM-1"

    def _need_online(self):
        if not self.online:
            raise TVUnavailable("The TV is off or cannot be reached.")

    def is_available(self) -> bool:
        return self.online

    def list_art(self) -> list[ArtItem]:
        with self._lock:
            self._need_online()
            return [ArtItem(i, n, i == self._current) for i, (n, _) in self._art.items()]

    def upload(self, path: Path) -> str:
        with self._lock:
            self._need_online()
            data = Path(path).read_bytes()
            cid = "MY-" + uuid.uuid4().hex[:8]
            self._art[cid] = (Path(path).stem, data)
            self.uploads.append(Path(path))
            return cid

    def select(self, content_id: str) -> None:
        with self._lock:
            self._need_online()
            if content_id not in self._art:
                raise KeyError(content_id)
            self._current = content_id

    def delete(self, content_id: str) -> None:
        with self._lock:
            self._need_online()
            self._art.pop(content_id, None)
            if self._current == content_id:
                self._current = None

    def thumbnail(self, content_id: str) -> Optional[bytes]:
        with self._lock:
            self._need_online()
            item = self._art.get(content_id)
            return item[1] if item else None
