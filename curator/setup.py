"""Write config/local.toml for this home. Run it once on the Pi.

  python -m curator.setup                      ask the questions
  python -m curator.setup --tv-host 10.0.0.20  no questions (for scripts and AI agents)

It finds Samsung TVs on the home network by asking every address for port 8002.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .tv import hosts_with_port
from .web import lan_address

TEMPLATE = """\
# Written by `python -m curator.setup`. Git ignores this file.
[tv]
host = "{tv_host}"
port = 8002
# The pairing token is saved here after you press Allow on the TV.
token_file = "config/token.txt"
name = "Curator"

[web]
# The address Curator listens on. Use the home network address of this computer.
# "0.0.0.0" listens on every network, VPNs included.
bind = "{bind}"
port = {port}

[storage]
data_dir = "data"
"""


def tv_name(host: str) -> str:
    """The model name the TV reports, or "" if it does not say."""
    try:
        from samsungtvws import SamsungTVWS

        dev = SamsungTVWS(host, timeout=3).rest_device_info().get("device") or {}
        return " ".join(x for x in (dev.get("name"), dev.get("modelName")) if x)
    except Exception:
        return ""


def find_tvs(near: str) -> list[tuple[str, str]]:
    return [(h, tv_name(h)) for h in hosts_with_port(near, 8002)]


def ask(prompt: str, default: str) -> str:
    answer = input(f"{prompt} [{default}]: ").strip()
    return answer or default


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m curator.setup")
    ap.add_argument("--tv-host", help="the TV address. Without it, the wizard searches and asks.")
    ap.add_argument("--bind", help="the address to listen on (default: this computer's home address)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--config", default=str(config.ROOT / "config" / "local.toml"))
    ap.add_argument("--force", action="store_true", help="replace an existing file")
    args = ap.parse_args(argv)

    out = Path(args.config)
    if out.exists() and not args.force:
        print(f"{out} exists. Use --force to replace it.")
        return 1

    here = lan_address()
    bind = args.bind or here or "0.0.0.0"
    tv_host = args.tv_host
    interactive = tv_host is None
    if interactive:
        if here:
            print(f"Searching {here.rsplit('.', 1)[0]}.x for Samsung TVs. Turn the TV on first...")
            tvs = find_tvs(here)
        else:
            tvs = []
        for i, (h, name) in enumerate(tvs, 1):
            print(f"  {i}. {h}  {name}")
        if not tvs:
            print("No TV answered. Make sure that the TV is on and on the same network.")
        default = tvs[0][0] if tvs else ""
        choice = ask("TV address, or a number from the list", default)
        if choice.isdigit() and 1 <= int(choice) <= len(tvs):
            choice = tvs[int(choice) - 1][0]
        tv_host = choice
        bind = ask("Address for Curator to listen on", bind)
    if not tv_host:
        print("Curator needs the TV address.", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(TEMPLATE.format(tv_host=tv_host, bind=bind, port=args.port))
    print(f"Wrote {out}.")
    print(f"After install, open http://{bind if bind != '0.0.0.0' else (here or 'this-computer')}:{args.port} on a phone.")
    print("Tip: reserve fixed addresses for the TV and this computer on your router.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
