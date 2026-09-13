from visage.assets import Viseme
from visage.rhubarb import parse_rhubarb_json

# Real example JSON from Rhubarb Lip Sync's own README.
EXAMPLE_JSON = {
    "metadata": {"soundFile": "hi.wav", "duration": 0.47},
    "mouthCues": [
        {"start": 0.00, "end": 0.05, "value": "X"},
        {"start": 0.05, "end": 0.27, "value": "D"},
        {"start": 0.27, "end": 0.31, "value": "C"},
        {"start": 0.31, "end": 0.43, "value": "B"},
        {"start": 0.43, "end": 0.47, "value": "X"},
    ],
}


def test_parse_rhubarb_json_maps_codes_in_order():
    cues = parse_rhubarb_json(EXAMPLE_JSON)

    assert [c.viseme for c in cues] == [
        Viseme.X,
        Viseme.D,
        Viseme.C,
        Viseme.B,
        Viseme.X,
    ]
    assert cues[0].start == 0.00
    assert cues[0].end == 0.05
    assert cues[-1].end == 0.47


def test_parse_rhubarb_json_maps_extended_shapes_to_fallback():
    raw = {"mouthCues": [{"start": 0.0, "end": 0.1, "value": "G"}, {"start": 0.1, "end": 0.2, "value": "H"}]}
    cues = parse_rhubarb_json(raw)
    assert cues[0].viseme == Viseme.F  # G -> F (nearest rounded shape)
    assert cues[1].viseme == Viseme.C  # H -> C (nearest open-vowel shape)


def test_parse_rhubarb_json_unknown_code_falls_back_to_x():
    raw = {"mouthCues": [{"start": 0.0, "end": 0.1, "value": "Z"}]}
    cues = parse_rhubarb_json(raw)
    assert cues[0].viseme == Viseme.X


def test_parse_rhubarb_json_sorts_by_start():
    raw = {
        "mouthCues": [
            {"start": 0.5, "end": 0.6, "value": "A"},
            {"start": 0.0, "end": 0.1, "value": "X"},
        ]
    }
    cues = parse_rhubarb_json(raw)
    assert [c.start for c in cues] == [0.0, 0.5]
