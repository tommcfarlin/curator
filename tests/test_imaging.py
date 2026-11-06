import pytest
from PIL import Image

from curator.imaging import FRAME_SIZE, ImageError, _crop_box, is_supported, prepare_image


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


from curator.imaging import assess


def test_assess_4k_is_great():
    a = assess(3840, 2160)
    assert a.level == "great" and a.scale == 1 and a.trimmed == 0


def test_assess_minimum_1080p_is_good():
    assert assess(1920, 1080).level == "good"


def test_assess_just_under_minimum_is_too_small():
    assert assess(1919, 1079).level == "too_small"


def test_assess_big_phone_photo_is_great_in_crop_mode():
    a = assess(4032, 3024)  # 4:3 photo, trimmed to 16:9
    assert a.level == "great"
    assert round(a.trimmed, 2) == 0.25 and not a.heavy_trim


def test_assess_portrait_photo_is_heavily_trimmed_in_crop_mode():
    a = assess(3024, 4032)
    assert a.heavy_trim and a.trimmed > 0.5


def test_assess_portrait_in_fit_mode_is_enlarged_by_height():
    a = assess(3024, 4032, mode="fit")
    assert a.trimmed == 0 and a.scale == 2160 / 4032 and a.level == "great"


def test_assess_small_portrait_crop_vs_fit():
    assert assess(1080, 2400, mode="crop").level == "too_small"  # 1080 wide stretched to 3840
    assert assess(1080, 2400, mode="fit").level == "great"


def test_assess_rejects_bad_input():
    with pytest.raises(ValueError):
        assess(0, 10)
    with pytest.raises(ValueError):
        assess(10, 10, mode="stretch")
