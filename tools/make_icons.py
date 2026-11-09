"""Draw the app icons into curator/static. Run: python tools/make_icons.py curator/static"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
out = Path(sys.argv[1])
def icon(n, pad_ratio=0.0):
    S = 1024
    im = Image.new("RGB", (S, S), (28, 28, 30))
    d = ImageDraw.Draw(im)
    p = int(S * (0.16 + pad_ratio))
    w = S - 2 * p
    h = int(w * 9 / 16)
    y0 = (S - h) // 2
    # frame
    d.rounded_rectangle([p, y0, p + w, y0 + h], radius=int(S * .03), fill=(245, 241, 232))
    m = int(w * .07)
    ix0, iy0, ix1, iy1 = p + m, y0 + m, p + w - m, y0 + h - m
    # picture: sky gradient, sun, hills
    for y in range(iy0, iy1):
        t = (y - iy0) / (iy1 - iy0)
        c = tuple(int(a + (b - a) * t) for a, b in zip((10, 132, 255), (255, 183, 120)))
        d.line([(ix0, y), (ix1, y)], fill=c)
    r = int((iy1 - iy0) * .16)
    cx, cy = ix0 + int((ix1 - ix0) * .7), iy0 + int((iy1 - iy0) * .38)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 236, 170))
    d.polygon([(ix0, iy1), (ix0, iy0 + (iy1-iy0)*.62), (ix0 + (ix1-ix0)*.35, iy0 + (iy1-iy0)*.45),
               (ix0 + (ix1-ix0)*.65, iy0 + (iy1-iy0)*.7), (ix1, iy0 + (iy1-iy0)*.55), (ix1, iy1)], fill=(36, 138, 61))
    # stand
    d.rounded_rectangle([S//2 - int(S*.09), y0 + h + int(S*.04), S//2 + int(S*.09), y0 + h + int(S*.065)],
                        radius=int(S*.012), fill=(142, 142, 147))
    return im.resize((n, n), Image.LANCZOS)
icon(180).save(out / "apple-touch-icon.png")
icon(192).save(out / "icon-192.png")
icon(512).save(out / "icon-512.png")
icon(512, pad_ratio=0.06).save(out / "icon-maskable-512.png")
