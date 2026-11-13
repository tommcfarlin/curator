"""Draw the app icons into curator/static: python tools/make_icons.py curator/static

The icon is a framed landscape (a sun over hills), drawn here with Pillow.
It uses no font or outside artwork, so it is under the same license as Curator.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024          # drawing size; the icons are scaled down from this
BG = (28, 28, 30)  # the dark gray of the app header


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def picture(w: int, h: int) -> Image.Image:
    """The landscape inside the frame: a dusk sky, a sun and three hills."""
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    top, bottom = (250, 178, 122), (150, 104, 150)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(top, bottom, y / (h - 1)))
    r = int(w * 0.13)
    cx, cy = int(w * 0.68), int(h * 0.36)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 226, 170))
    hills = [
        (0.58, (104, 76, 134), [(0, 0.10), (0.25, 0.0), (0.5, 0.08), (0.8, -0.02), (1, 0.06)]),
        (0.70, (70, 52, 104), [(0, 0.0), (0.3, 0.10), (0.6, -0.02), (1, 0.08)]),
        (0.82, (40, 30, 66), [(0, 0.06), (0.4, -0.04), (0.75, 0.06), (1, 0.0)]),
    ]
    for base, color, pts in hills:
        poly = [(int(x * w), int((base + dy) * h)) for x, dy in pts]
        d.polygon([(0, h)] + poly + [(w, h)], fill=color)
    return im


def master(frame_share: float) -> Image.Image:
    """The full icon at S x S. `frame_share` is the share of the width the frame takes."""
    im = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(im)
    fw = int(S * frame_share)
    fh = int(fw * 0.80)
    x0, y0 = (S - fw) // 2, (S - fh) // 2
    border = int(fw * 0.075)
    d.rounded_rectangle([x0, y0, x0 + fw, y0 + fh], radius=int(fw * 0.04), fill=(236, 236, 240))
    mat = int(fw * 0.02)
    inner = (x0 + border, y0 + border, x0 + fw - border, y0 + fh - border)
    d.rectangle([inner[0] - mat, inner[1] - mat, inner[2] + mat, inner[3] + mat], fill=(200, 200, 206))
    im.paste(picture(inner[2] - inner[0], inner[3] - inner[1]), inner[:2])
    return im


def main(out: Path) -> None:
    regular, maskable, favicon = master(0.74), master(0.58), master(0.92)
    regular.resize((180, 180), Image.LANCZOS).save(out / "apple-touch-icon.png")
    regular.resize((192, 192), Image.LANCZOS).save(out / "icon-192.png")
    regular.resize((512, 512), Image.LANCZOS).save(out / "icon-512.png")
    maskable.resize((512, 512), Image.LANCZOS).save(out / "icon-maskable-512.png")  # Android crops it
    favicon.resize((64, 64), Image.LANCZOS).save(out / "favicon.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
