from PIL import Image, ImageDraw

from visage.assets import AvatarAssets, MouthState

SIZE = (16, 16)


def _corner_pixel(assets: AvatarAssets, state: MouthState) -> tuple[int, int, int]:
    frame = assets.video_frame(state)
    data = bytes(frame.data)
    return data[0], data[1], data[2]  # top-left pixel, RGB24


def _make_overlay_set(tmp_path) -> None:
    # face: transparent canvas with an opaque circle in the middle
    face = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(face).ellipse((4, 4, 12, 12), fill=(255, 200, 0, 255))
    face.save(tmp_path / "face.png")
    Image.new("RGBA", SIZE, (0, 0, 0, 0)).save(tmp_path / "mouth_closed.png")
    Image.new("RGBA", SIZE, (0, 0, 0, 0)).save(tmp_path / "mouth_open.png")


def test_overlay_mode_transparent_corner_is_black_by_default(tmp_path):
    _make_overlay_set(tmp_path)
    assets = AvatarAssets.load(tmp_path)
    assert _corner_pixel(assets, MouthState.CLOSED) == (0, 0, 0)


def test_overlay_mode_background_fills_transparent_corner(tmp_path):
    _make_overlay_set(tmp_path)
    assets = AvatarAssets.load(tmp_path, background=(30, 60, 90))
    assert _corner_pixel(assets, MouthState.CLOSED) == (30, 60, 90)


def test_full_frame_mode_background_fills_transparent_corner(tmp_path):
    for name in ("full_closed.png", "full_open.png"):
        img = Image.new("RGBA", SIZE, (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((4, 4, 12, 12), fill=(255, 200, 0, 255))
        img.save(tmp_path / name)

    default = AvatarAssets.load_full_frames(tmp_path)
    assert _corner_pixel(default, MouthState.CLOSED) == (0, 0, 0)

    colored = AvatarAssets.load_full_frames(tmp_path, background=(10, 20, 30))
    assert _corner_pixel(colored, MouthState.CLOSED) == (10, 20, 30)
