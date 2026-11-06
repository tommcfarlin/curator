"""Resize and crop images to the 16:9 shape of The Frame. Offline: no network."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

FRAME_SIZE = (3840, 2160)
SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


class ImageError(Exception):
    """The file is not an image that we can read."""


def is_supported(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED


def _crop_box(w: int, h: int, target: tuple[int, int], focus: tuple[float, float]):
    """Largest box with the target aspect ratio, placed around the focus point."""
    tw, th = target
    if w * th > h * tw:  # source is wider than target: trim the sides
        cw, ch = round(h * tw / th), h
    else:  # source is taller than target: trim top and bottom
        cw, ch = w, round(w * th / tw)
    fx = min(max(focus[0], 0.0), 1.0)
    fy = min(max(focus[1], 0.0), 1.0)
    left = round((w - cw) * fx)
    top = round((h - ch) * fy)
    return (left, top, left + cw, top + ch)


def prepare_image(
    src: str | Path,
    dst: str | Path,
    size: tuple[int, int] = FRAME_SIZE,
    mode: str = "crop",
    focus: tuple[float, float] = (0.5, 0.5),
    quality: int = 92,
    matte: tuple[int, int, int] = (0, 0, 0),
) -> Path:
    """Write a JPEG of exactly `size` to `dst` and return its path.

    mode "crop": fill the frame and cut the overflow. `focus` (0..1, 0..1)
    picks which part of the image stays.
    mode "fit": show the whole image and fill the rest with `matte`.
    """
    if mode not in ("crop", "fit"):
        raise ValueError(f"unknown mode: {mode!r}")
    try:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
    except Exception as exc:  # Pillow raises many types for bad files
        raise ImageError(f"cannot read image {src}: {exc}") from exc

    if mode == "crop":
        im = im.crop(_crop_box(im.width, im.height, size, focus))
        out = im.resize(size, Image.LANCZOS)
    else:
        scale = min(size[0] / im.width, size[1] / im.height)
        new = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
        scaled = im.resize(new, Image.LANCZOS)
        out = Image.new("RGB", size, matte)
        out.paste(scaled, ((size[0] - new[0]) // 2, (size[1] - new[1]) // 2))

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, "JPEG", quality=quality, optimize=True)
    return dst


# Quality rules. The phone page uses the same numbers (design/prototype).
MIN_SIZE = (1920, 1080)  # smallest size that we call acceptable
HEAVY_TRIM = 0.35  # warn when crop mode cuts more than this share of the photo


@dataclass(frozen=True)
class Assessment:
    level: str  # "great", "good" or "too_small"
    scale: float  # how many times the photo is enlarged to fill the screen
    trimmed: float  # share of the photo that crop mode cuts off (0 to 1)

    @property
    def heavy_trim(self) -> bool:
        return self.trimmed > HEAVY_TRIM


def assess(
    width: int, height: int, mode: str = "crop", target: tuple[int, int] = FRAME_SIZE
) -> Assessment:
    """Judge how a photo of this size will look on the Frame. No distortion: we never stretch."""
    if width < 1 or height < 1:
        raise ValueError("size must be positive")
    if mode not in ("crop", "fit"):
        raise ValueError(f"unknown mode: {mode!r}")
    tw, th = target
    if mode == "crop":
        left, top, right, bottom = _crop_box(width, height, target, (0.5, 0.5))
        cw, ch = right - left, bottom - top
        scale = tw / cw
        trimmed = 1 - (cw * ch) / (width * height)
    else:
        scale = min(tw / width, th / height)
        trimmed = 0.0
    max_scale = tw / MIN_SIZE[0]
    level = "great" if scale <= 1 else "good" if scale <= max_scale + 1e-9 else "too_small"
    return Assessment(level, scale, trimmed)
