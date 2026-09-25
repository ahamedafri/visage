# Contributing to visage

Thanks for considering it — this is a small, young project, so contributions
of any size are genuinely useful right now.

## Setup

```bash
git clone https://github.com/ahamedafri/visage.git
cd visage
python -m venv .venv
.venv/Scripts/activate   # or `source .venv/bin/activate` on macOS/Linux
pip install -e ".[dev]"
pytest -q
```

That's the whole loop — no external services, no API keys, no GPU. The test
suite (currently 37 tests) runs in well under a minute and needs nothing
beyond what `pip install -e ".[dev]"` gives you: **not** the real `rhubarb`
binary, **not** a LiveKit server. Both of those are exercised by opt-in
scripts instead (see below), on purpose, so CI and every contributor's
first run stay fast and dependency-free.

## Testing philosophy

- **Drive the real classes, not mocks.** Tests construct actual
  `ImageAvatarVideoGenerator`/`RhubarbVisemeVideoGenerator`/`AvatarAssets`
  instances and push real (synthetic) audio through them — see
  `tests/test_rhubarb_fallback.py` or `tests/test_idle_heartbeat.py` for the
  pattern. Prefer this over mocking internals.
- **Synthetic fixtures, not real assets, for `AvatarAssets` tests.** Tiny
  solid-color Pillow images in `tmp_path` (see `tests/test_assets_blink.py`)
  — fast, no binary files to review in diffs, and precise about what's
  actually being checked (a specific pixel, a specific error message).
- **Manual verification scripts are separate from the automated suite**,
  and never required for `pytest` to pass:
  - `scripts/smoke_test.py` — full pipeline, synthetic audio only, no
    LiveKit room or rhubarb binary.
  - `scripts/smoke_test_rhubarb.py` — needs the real `rhubarb` binary
    installed; exits cleanly (code 0) if it isn't found, so it never fails
    a machine that doesn't have it.
  - `scripts/live_test.py` — needs a real LiveKit server (your own
    `LIVEKIT_URL`/`_API_KEY`/`_API_SECRET`); joins a real room with two
    participants and checks what actually came back through the server.
  - `scripts/render_preview.py` — regenerates the README's demo
    images/GIFs from the real generator output.

If you change generator behavior, add or update a test in the first
category before reaching for one of the manual scripts.

## Reporting a bug

Please include:
- Which generator (`ImageAvatarVideoGenerator` or `RhubarbVisemeVideoGenerator`)
- `visage.__version__` and `python --version`
- A minimal repro if possible — ideally something that fits the existing
  test patterns (synthetic audio, no real photo/room/binary needed)
- What you expected vs. what happened, including any warning/error text

## Code style

No linter/formatter is enforced yet (small project, will add one once
there's more than one contributor's style to reconcile) — just match what's
already there: type hints throughout, docstrings that explain *why* a
design choice was made where it isn't obvious from the code, and comments
that stay honest about known limitations rather than glossing over them
(see the README's "Known limitations" section for the standard to match).

## Pull requests

- Keep them focused — one change, one PR, makes review realistic.
- Update `README.md`/`CHANGELOG.md` alongside behavior changes; docs drift
  is treated as a real bug in this project, not an afterthought.
- `pytest -q` should pass locally before you open the PR; CI runs the same
  suite on Linux + Windows × Python 3.10/3.13, plus a wheel-build-and-install
  check.
