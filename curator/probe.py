"""Read-only check of the real TV: python -m curator.probe

It connects once, prints the art list, and exits. It uploads nothing and
deletes nothing. The first run makes the TV show an Allow prompt.
"""
from __future__ import annotations

import argparse
import json

from . import config
from .tv import SamsungTV, TVUnavailable


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="curator.probe")
    ap.add_argument("--config", default=str(config.ROOT / "config" / "local.toml"))
    args = ap.parse_args(argv)
    s = config.load(args.config)
    tv = SamsungTV(s.tv_host, s.tv_port, s.token_file, s.tv_name)
    print(f"Port {s.tv_port} on {s.tv_host} answers: {tv.is_available()}")

    def go(art):
        return {
            "api_version": art.get_api_version(),
            "art_mode": art.get_artmode(),
            "current": art.get_current(),
            "available": art.available(),
        }

    try:
        data = tv._run(go)
    except TVUnavailable as e:
        print(f"Failed: {e}")
        return 1
    print(json.dumps(data, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
