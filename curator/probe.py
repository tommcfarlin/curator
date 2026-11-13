"""Supervised checks of the real TV. See docs/TV-TEST.md.

  python -m curator.probe                 Step 1. Read only: pair, then list the art.
  python -m curator.probe --upload-test   Step 2. Upload one test card. It does not show it.
  python -m curator.probe --show ID       Step 3. Show one photo on the TV.
  python -m curator.probe --delete ID     Step 4. Remove a photo that the test uploaded.

The first connection makes the TV show an Allow prompt. Press Allow on the remote.
Each run saves what the TV said to data/probe/, which git ignores.
"""
from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path

from PIL import Image, ImageDraw

from . import config
from .tv import SamsungTV, TVUnavailable


def test_card(path: Path, size=(3840, 2160)) -> Path:
    """A 16:9 test card with the time on it, so it is easy to spot on the TV."""
    im = Image.new("RGB", size, (28, 28, 30))
    d = ImageDraw.Draw(im)
    w, h = size
    for i, c in enumerate([(255, 69, 58), (255, 159, 10), (48, 209, 88), (10, 132, 255), (191, 90, 242)]):
        d.rectangle([i * w // 5, h * 2 // 3, (i + 1) * w // 5, h], fill=c)
    d.rectangle([40, 40, w - 40, h - 40], outline=(255, 255, 255), width=12)
    label = f"Curator test card  {time.strftime('%Y-%m-%d %H:%M')}"
    d.text((w // 2, h // 3), label, fill=(255, 255, 255), anchor="mm", font_size=140)
    im.save(path, "JPEG", quality=92)
    return path


def summarize(data: dict) -> list[str]:
    items = data.get("available") or []
    cats = collections.Counter(i.get("category_id", "?") for i in items if isinstance(i, dict))
    cur = data.get("current") or {}
    lines = [
        f"Art API version: {data.get('api_version')}",
        f"Art Mode: {data.get('art_mode')}",
        f"Pieces on the TV: {len(items)}",
        "By category: " + ", ".join(f"{k} = {v}" for k, v in sorted(cats.items())),
        f"Showing now: {cur.get('content_id') if isinstance(cur, dict) else cur}",
    ]
    return lines


def save(out_dir: Path, name: str, data) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}.json"
    p.write_text(json.dumps(data, indent=2, default=str))
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="curator.probe", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(config.ROOT / "config" / "local.toml"))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--upload-test", action="store_true", help="upload one test card (it is not shown)")
    g.add_argument("--show", metavar="ID", help="show this content id on the TV")
    g.add_argument("--delete", metavar="ID", help="remove this content id from the TV")
    args = ap.parse_args(argv)

    s = config.load(args.config)
    tv = SamsungTV(s.tv_host, s.tv_port, s.token_file, s.tv_name)
    out_dir = s.data_dir / "probe"
    print(f"TV: {s.tv_host}:{s.tv_port}   paired before: {'yes' if tv.is_paired() else 'no'}")
    if not tv.is_available():
        print("The TV does not answer. Make sure that it is on and on the same network.")
        return 1
    if not tv.is_paired():
        print("Look at the TV now. Press Allow on the remote when the prompt appears.")

    try:
        if args.upload_test:
            s.data_dir.mkdir(parents=True, exist_ok=True)
            card = test_card(s.data_dir / "probe-test-card.jpg")
            t0 = time.monotonic()
            cid = tv.upload(card)
            secs = time.monotonic() - t0
            save(out_dir, "upload", {"content_id": cid, "seconds": round(secs, 1)})
            print(f"Uploaded the test card in {secs:.1f} s. Content id: {cid}")
            print(f"It is in My Photos on the TV. To show it: python -m curator.probe --show {cid}")
            return 0
        if args.show:
            tv.select(args.show)
            print(f"Asked the TV to show {args.show}. Look at the TV.")
            return 0
        if args.delete:
            tv.delete(args.delete)
            print(f"Asked the TV to remove {args.delete}.")
            return 0

        def go(art):
            data = {"api_version": art.get_api_version()}
            for key, fn in (("art_mode", art.get_artmode), ("current", art.get_current),
                            ("available", art.available)):
                try:
                    data[key] = fn()
                except Exception as e:  # keep going: a partial answer still helps
                    data[key] = f"error: {type(e).__name__}: {e}"
            return data

        data = tv._run(go)
    except TVUnavailable as e:
        print(f"Failed: {e}")
        return 1
    path = save(out_dir, "list", data)
    print("\n".join(summarize(data)))
    print(f"Full answer saved to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
