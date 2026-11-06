"""Start Curator: python -m curator [--config FILE] [--fake-tv]"""
from __future__ import annotations

import argparse
import logging
import sys

from . import config
from .library import Library
from .queue import RetryQueue
from .tv import FakeTV
from .web import create_app
from .worker import Worker


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="curator")
    ap.add_argument("--config", default=str(config.ROOT / "config" / "local.toml"))
    ap.add_argument("--fake-tv", action="store_true", help="use a pretend TV (development)")
    ap.add_argument("--bind", help="override the address to listen on")
    ap.add_argument("--port", type=int, help="override the port")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    s = config.load(args.config)
    if not args.fake_tv:
        print("The real TV client is not built yet. Run with --fake-tv.", file=sys.stderr)
        return 2
    tv = FakeTV()
    queue = RetryQueue(s.db_path)
    library = Library(s.db_path)
    worker = Worker(queue, tv, library, s.thumbs_dir)
    app = create_app(s, tv, queue, library, worker)
    worker.start()
    bind, port = args.bind or s.web_bind, args.port or s.web_port
    from waitress import serve

    print(f"Curator (fake TV) on http://{bind}:{port}")
    serve(app, host=bind, port=port, threads=8)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
