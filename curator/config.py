"""Settings from a TOML file. Relative paths count from the project folder."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    tv_host: str = "192.168.1.20"
    tv_port: int = 8002
    tv_name: str = "Curator"
    tv_mac: str = ""   # optional. Curator learns it while the TV is on.
    token_file: Path = ROOT / "config" / "token.txt"
    web_bind: str = "127.0.0.1"
    web_port: int = 8080
    data_dir: Path = ROOT / "data"
    width: int = 3840
    height: int = 2160
    jpeg_quality: int = 92
    max_upload_mb: int = 25

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "curator.sqlite3"

    @property
    def prepared_dir(self) -> Path:
        return self.data_dir / "prepared"

    @property
    def thumbs_dir(self) -> Path:
        return self.data_dir / "thumbs"

    @property
    def incoming_dir(self) -> Path:
        return self.data_dir / "incoming"


def _path(value: str, base: Path) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else base / p


def load(path: str | Path | None = None, base: Path = ROOT) -> Settings:
    """Load settings. A missing file gives the defaults."""
    if path is None or not Path(path).exists():
        return Settings()
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    tv, web, st, im = (raw.get(k, {}) for k in ("tv", "web", "storage", "image"))
    d = Settings()
    return Settings(
        tv_host=tv.get("host", d.tv_host),
        tv_port=int(tv.get("port", d.tv_port)),
        tv_name=tv.get("name", d.tv_name),
        tv_mac=str(tv.get("mac", d.tv_mac)),
        token_file=_path(tv["token_file"], base) if "token_file" in tv else d.token_file,
        web_bind=web.get("bind", d.web_bind),
        web_port=int(web.get("port", d.web_port)),
        data_dir=_path(st["data_dir"], base) if "data_dir" in st else d.data_dir,
        width=int(im.get("width", d.width)),
        height=int(im.get("height", d.height)),
        jpeg_quality=int(im.get("jpeg_quality", d.jpeg_quality)),
        max_upload_mb=int(web.get("max_upload_mb", d.max_upload_mb)),
    )
