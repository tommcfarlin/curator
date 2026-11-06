import pytest
from PIL import Image

from frameart.imaging import FRAME_SIZE, ImageError, _crop_box, is_supported, prepare_image


def make(path, size, color=(200, 30, 30)):
    Image.new("RGB", size, color).save(path)
    return path


def test_wide_image_is_cropped_to_exact_frame_size(tmp_path):
    src = make(tmp_path / "a.png", (6000, 2000))
    out = prepare_image(src, tmp_path / "o.jpg")
    with Image.open(out) as im:
        assert im.size == FRAME_SIZE and im.format == "JPEG"


def test_tall_phone_photo_is_cropped(tmp_path):
    src = make(tmp_path / "a.png", (1080, 2400))
    out = prepare_image(src, tmp_path / "o.jpg")
    with Image.open(out) as im:
        assert im.size == FRAME_SIZE


def test_small_image_is_scaled_up(tmp_path):
    src = make(tmp_path / "a.png", (160, 90))
    with Image.open(prepare_image(src, tmp_path / "o.jpg")) as im:
        assert im.size == FRAME_SIZE


def test_focus_moves_the_crop_window():
    assert _crop_box(1000, 2000, (16, 9), (0.5, 0.0))[1] == 0
    assert _crop_box(1000, 2000, (16, 9), (0.5, 1.0))[3] == 2000
    assert _crop_box(1000, 2000, (16, 9), (0.5, 9.0))[3] == 2000  # clamped


def test_focus_picks_the_right_content(tmp_path):
    im = Image.new("RGB", (400, 800), (0, 0, 255))
    im.paste((255, 0, 0), (0, 0, 400, 100))  # red band at the top
    im.save(tmp_path / "a.png")
    top = prepare_image(tmp_path / "a.png", tmp_path / "t.jpg", size=(160, 90), focus=(0.5, 0))
    bot = prepare_image(tmp_path / "a.png", tmp_path / "b.jpg", size=(160, 90), focus=(0.5, 1))
    with Image.open(top) as t, Image.open(bot) as b:
        assert t.getpixel((80, 5))[0] > 200
        assert b.getpixel((80, 5))[2] > 200


def test_fit_mode_keeps_whole_image_with_matte(tmp_path):
    src = make(tmp_path / "a.png", (1000, 1000))
    out = prepare_image(src, tmp_path / "o.jpg", size=(160, 90), mode="fit")
    with Image.open(out) as im:
        assert im.size == (160, 90)
        assert im.getpixel((2, 45)) == (0, 0, 0) or max(im.getpixel((2, 45))) < 20
        assert im.getpixel((80, 45))[0] > 150


def test_exif_rotation_is_applied(tmp_path):
    im = Image.new("RGB", (200, 100), (255, 0, 0))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees: stored landscape, shown portrait
    im.save(tmp_path / "a.jpg", exif=exif)
    out = prepare_image(tmp_path / "a.jpg", tmp_path / "o.jpg", size=(90, 160), mode="fit")
    with Image.open(out) as o:
        assert o.size == (90, 160)
        assert o.getpixel((45, 80))[0] > 150  # fills the frame: image was rotated to portrait


def test_bad_file_raises_image_error(tmp_path):
    bad = tmp_path / "x.jpg"
    bad.write_bytes(b"not an image")
    with pytest.raises(ImageError):
        prepare_image(bad, tmp_path / "o.jpg")


def test_unknown_mode_raises(tmp_path):
    src = make(tmp_path / "a.png", (10, 10))
    with pytest.raises(ValueError):
        prepare_image(src, tmp_path / "o.jpg", mode="stretch")


def test_is_supported():
    assert is_supported("a.JPG") and is_supported("b.png") and not is_supported("c.txt")


def test_output_dir_is_created(tmp_path):
    src = make(tmp_path / "a.png", (32, 18))
    out = prepare_image(src, tmp_path / "deep" / "er" / "o.jpg", size=(32, 18))
    assert out.exists()
