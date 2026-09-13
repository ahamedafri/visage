from PIL import Image

from visage.assets import AvatarAssets, MouthState

SIZE = (16, 16)


def _make_face(tmp_path, *, with_blink: bool) -> None:
    Image.new("RGBA", SIZE, (255, 255, 0, 255)).save(tmp_path / "face.png")
    if with_blink:
        Image.new("RGBA", SIZE, (0, 255, 0, 255)).save(tmp_path / "face_blink.png")
    # transparent mouth overlays so composited output stays distinguishable
    # by the face color alone
    Image.new("RGBA", SIZE, (0, 0, 0, 0)).save(tmp_path / "mouth_closed.png")
    Image.new("RGBA", SIZE, (0, 0, 0, 0)).save(tmp_path / "mouth_open.png")


def test_blink_variant_differs_from_normal_when_blink_art_present(tmp_path):
    _make_face(tmp_path, with_blink=True)
    assets = AvatarAssets.load(tmp_path)

    assert assets.has_blink_art
    normal = assets.video_frame(MouthState.CLOSED, blinking=False)
    blink = assets.video_frame(MouthState.CLOSED, blinking=True)
    assert bytes(normal.data) != bytes(blink.data)


def test_blinking_is_ignored_when_no_blink_art_present(tmp_path):
    _make_face(tmp_path, with_blink=False)
    assets = AvatarAssets.load(tmp_path)

    assert not assets.has_blink_art
    normal = assets.video_frame(MouthState.CLOSED, blinking=False)
    # blinking=True must not raise, and must fall back to the normal frame
    requested_blink = assets.video_frame(MouthState.CLOSED, blinking=True)
    assert bytes(normal.data) == bytes(requested_blink.data)


def test_mismatched_face_blink_size_raises(tmp_path):
    _make_face(tmp_path, with_blink=True)
    Image.new("RGBA", (8, 8), (0, 255, 0, 255)).save(tmp_path / "face_blink.png")

    try:
        AvatarAssets.load(tmp_path)
        assert False, "expected a ValueError for mismatched face_blink.png size"
    except ValueError as e:
        assert "face_blink.png" in str(e)
