from PIL import Image

from visage.assets import AvatarAssets, MouthState

SIZE = (16, 16)


def _make_full_frames(tmp_path, *, with_blink_for=()) -> None:
    Image.new("RGB", SIZE, (255, 0, 0)).save(tmp_path / "full_closed.png")
    Image.new("RGB", SIZE, (0, 0, 255)).save(tmp_path / "full_open.png")
    if MouthState.CLOSED in with_blink_for:
        Image.new("RGB", SIZE, (0, 255, 0)).save(tmp_path / "full_closed_blink.png")
    if MouthState.OPEN in with_blink_for:
        Image.new("RGB", SIZE, (255, 255, 0)).save(tmp_path / "full_open_blink.png")


def test_load_full_frames_success(tmp_path):
    _make_full_frames(tmp_path)
    assets = AvatarAssets.load_full_frames(tmp_path)

    assert assets.resolution == SIZE
    assert not assets.has_blink_art
    closed = assets.video_frame(MouthState.CLOSED)
    open_ = assets.video_frame(MouthState.OPEN)
    assert bytes(closed.data) != bytes(open_.data)


def test_load_full_frames_missing_required_file_raises(tmp_path):
    Image.new("RGB", SIZE, (255, 0, 0)).save(tmp_path / "full_closed.png")
    # full_open.png intentionally missing

    try:
        AvatarAssets.load_full_frames(tmp_path)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as e:
        assert "full_open.png" in str(e)


def test_load_full_frames_mismatched_dimensions_raises(tmp_path):
    Image.new("RGB", SIZE, (255, 0, 0)).save(tmp_path / "full_closed.png")
    Image.new("RGB", (8, 8), (0, 0, 255)).save(tmp_path / "full_open.png")

    try:
        AvatarAssets.load_full_frames(tmp_path)
        assert False, "expected ValueError for mismatched dimensions"
    except ValueError as e:
        msg = str(e)
        assert "full_closed.png" in msg
        assert "full_open.png" in msg


def test_load_full_frames_per_state_blink_fallback(tmp_path):
    _make_full_frames(tmp_path, with_blink_for=(MouthState.CLOSED,))
    assets = AvatarAssets.load_full_frames(tmp_path)

    assert assets.has_blink_art
    closed_normal = assets.video_frame(MouthState.CLOSED, blinking=False)
    closed_blink = assets.video_frame(MouthState.CLOSED, blinking=True)
    assert bytes(closed_normal.data) != bytes(closed_blink.data)

    # OPEN has no blink art of its own -> falls back to its non-blink frame
    open_normal = assets.video_frame(MouthState.OPEN, blinking=False)
    open_blink = assets.video_frame(MouthState.OPEN, blinking=True)
    assert bytes(open_normal.data) == bytes(open_blink.data)


def test_blinking_ignored_when_no_full_frame_blink_art_present(tmp_path):
    _make_full_frames(tmp_path)
    assets = AvatarAssets.load_full_frames(tmp_path)

    assert not assets.has_blink_art
    normal = assets.video_frame(MouthState.CLOSED, blinking=False)
    requested_blink = assets.video_frame(MouthState.CLOSED, blinking=True)
    assert bytes(normal.data) == bytes(requested_blink.data)


def test_load_full_frames_blink_dimension_mismatch_raises(tmp_path):
    _make_full_frames(tmp_path)
    # overwrite with a mismatched-size blink variant
    Image.new("RGB", (8, 8), (0, 255, 0)).save(tmp_path / "full_closed_blink.png")

    try:
        AvatarAssets.load_full_frames(tmp_path)
        assert False, "expected ValueError for mismatched blink dimensions"
    except ValueError as e:
        assert "full_closed_blink.png" in str(e)
