import io

import pytest
from PIL import Image

from curator.config import Settings
from curator.library import Library
from curator.queue import RetryQueue
from curator.tv import FakeTV
from curator.web import create_app
from curator.worker import Worker


@pytest.fixture
def env(tmp_path):
    s = Settings(data_dir=tmp_path / "data", width=320, height=180)
    tv = FakeTV()
    q = RetryQueue(":memory:")
    lib = Library(":memory:")
    w = Worker(q, tv, lib, s.thumbs_dir)  # not started: tests call process_one
    app = create_app(s, tv, q, lib, w)
    return type("Env", (), dict(s=s, tv=tv, q=q, lib=lib, w=w, app=app, client=app.test_client()))


def png_bytes(size=(640, 360), color=(200, 40, 40)):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()
