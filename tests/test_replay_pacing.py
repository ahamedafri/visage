from visage.assets import Viseme
from visage.rhubarb import VisemeCue, plan_viseme_sequence

CUES = [
    VisemeCue(start=0.00, end=0.05, viseme=Viseme.X),
    VisemeCue(start=0.05, end=0.27, viseme=Viseme.D),
    VisemeCue(start=0.27, end=0.31, viseme=Viseme.C),
    VisemeCue(start=0.31, end=0.43, viseme=Viseme.B),
    VisemeCue(start=0.43, end=0.47, viseme=Viseme.X),
]
VIDEO_FPS = 25.0  # window i starts at t = i / 25 = i * 0.04s


def test_plan_viseme_sequence_matches_cue_windows():
    # window -> t -> expected cue:
    #  0 -> 0.00 -> X [0.00, 0.05)
    #  1 -> 0.04 -> X [0.00, 0.05)
    #  2 -> 0.08 -> D [0.05, 0.27)
    #  6 -> 0.24 -> D [0.05, 0.27)
    #  7 -> 0.28 -> C [0.27, 0.31)
    #  8 -> 0.32 -> B [0.31, 0.43)
    # 10 -> 0.40 -> B [0.31, 0.43)
    # 11 -> 0.44 -> X [0.43, 0.47)
    num_windows = 12
    result = plan_viseme_sequence(CUES, num_windows, VIDEO_FPS)

    assert len(result) == num_windows
    assert result[0] == Viseme.X
    assert result[1] == Viseme.X
    assert result[2] == Viseme.D
    assert result[6] == Viseme.D
    assert result[7] == Viseme.C
    assert result[8] == Viseme.B
    assert result[10] == Viseme.B
    assert result[11] == Viseme.X


def test_plan_viseme_sequence_trailing_silence_past_last_cue():
    # windows well past the last cue's end (0.47s) should fall back to X
    num_windows = 20  # up to t = 19/25 = 0.76s
    result = plan_viseme_sequence(CUES, num_windows, VIDEO_FPS)
    assert result[-1] == Viseme.X
    assert result[15] == Viseme.X  # t=0.60, past 0.47


def test_plan_viseme_sequence_empty_cues_is_all_silence():
    result = plan_viseme_sequence([], 5, VIDEO_FPS)
    assert result == [Viseme.X] * 5
