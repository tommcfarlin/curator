"""The TV side. `TV` is the small interface the rest of Curator uses.

`FakeTV` is for development and tests. The real client for `samsungtvws`
comes later, after the supervised first connection.
"""
from __future__ import annotations

import io
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from PIL import Image


class TVUnavailable(Exception):
    """The TV is off, unreachable, or refused the connection."""


@dataclass(frozen=True)
class ArtItem:
    id: str
    name: Optional[str]
    current: bool


class TV(Protocol):
    def is_available(self) -> bool: ...
    def list_art(self) -> list[ArtItem]: ...
    def upload(self, path: Path) -> str: ...
    def select(self, content_id: str) -> None: ...
    def delete(self, content_id: str) -> None: ...
    def thumbnail(self, content_id: str) -> Optional[bytes]: ...


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
