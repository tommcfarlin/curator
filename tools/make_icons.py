"""Draw the app icons into curator/static. Run on a Mac: python tools/make_icons.py curator/static

The icon is the framed picture emoji, U+1F5BC, from the Apple Color Emoji font.
Apple's emoji art is licensed for use on Apple devices. That is fine for a private
home app. Before the repo goes public, draw the same icon from Twemoji (CC BY 4.0)
or Noto Emoji (Apache 2.0) instead.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

EMOJI = "\U0001F5BC️"
FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"
BG_TOP, BG_BOTTOM = (255, 255, 255), (229, 229, 234)  # Apple system grays


def emoji_image() -> Image.Image:
    font = ImageFont.truetype(FONT, 160)  # the only size this bitmap font has
    im = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((120, 120), EMOJI, font=font, embedded_color=True, anchor="mm")
    return im.crop(im.getbbox())


def icon(n: int, fill: float) -> Image.Image:
    """A square icon. `fill` is the share of the width the emoji takes."""
    S = 1024
    bg = Image.new("RGB", (S, S))
    d = ImageDraw.Draw(bg)
    for y in range(S):
        t = y / (S - 1)
        d.line([(0, y), (S, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    e = emoji_image()
    w = int(S * fill)
    h = round(e.height * w / e.width)
    e = e.resize((w, h), Image.LANCZOS)
    bg.paste(e, ((S - w) // 2, (S - h) // 2), e)
    return bg.resize((n, n), Image.LANCZOS)


def main(out: Path) -> None:
    icon(180, 0.70).save(out / "apple-touch-icon.png")
    icon(192, 0.70).save(out / "icon-192.png")
    icon(512, 0.70).save(out / "icon-512.png")
    icon(512, 0.56).save(out / "icon-maskable-512.png")  # Android crops this to a circle
    icon(64, 0.84).save(out / "favicon.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
