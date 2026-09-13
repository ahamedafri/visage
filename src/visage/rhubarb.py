"""Subprocess integration with Rhubarb Lip Sync (https://github.com/DanielSWolf/rhubarb-lip-sync).

Rhubarb is a separate, MIT-licensed compiled binary — NOT a pip package.
Download it yourself from its GitHub releases page and either put it on
your `PATH` or point `RHUBARB_PATH` at it (see README).

It's a batch tool: it operates on a complete WAV file and has no streaming
mode, which is why the caller (``rhubarb_video_generator.py``) buffers a
whole utterance before invoking it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Literal, NamedTuple

from .assets import Viseme
from .wav_io import write_wav

logger = logging.getLogger("visage")

RHUBARB_RELEASES_URL = "https://github.com/DanielSWolf/rhubarb-lip-sync/releases"


class RhubarbNotFoundError(RuntimeError):
    """Raised when no rhubarb executable can be located."""


class RhubarbError(RuntimeError):
    """Raised when the rhubarb subprocess fails, times out, or returns
    output that can't be parsed."""


class VisemeCue(NamedTuple):
    start: float
    end: float
    viseme: Viseme


# Rhubarb's basic set (A-F, X) maps directly. The optional extended shapes
# (G, H) have no dedicated art in this project yet, so they fall back to the
# nearest basic shape we do have art for.
_RHUBARB_CODE_TO_VISEME: dict[str, Viseme] = {
    "X": Viseme.X,
    "A": Viseme.A,
    "B": Viseme.B,
    "C": Viseme.C,
    "D": Viseme.D,
    "E": Viseme.E,
    "F": Viseme.F,
    "G": Viseme.F,  # upper teeth on lower lip (F/V) -> nearest rounded shape
    "H": Viseme.C,  # tongue raised (L) -> nearest open-vowel shape
}


def find_rhubarb_executable(explicit_path: str | None = None) -> Path:
    """Resolution order: `explicit_path` -> `RHUBARB_PATH` env var -> `PATH`.

    Raises RhubarbNotFoundError with an actionable message if none resolve.
    """
    candidates = [explicit_path, os.environ.get("RHUBARB_PATH")]
    for candidate in candidates:
        if candidate:
            path = Path(candidate)
            if path.is_file():
                return path
            logger.debug("rhubarb candidate path does not exist: %s", path)

    for name in ("rhubarb", "rhubarb.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)

    raise RhubarbNotFoundError(
        "rhubarb executable not found. Download it from "
        f"{RHUBARB_RELEASES_URL}, then either put it on your PATH or set "
        "the RHUBARB_PATH environment variable to its full path."
    )


def parse_rhubarb_json(raw: dict) -> list[VisemeCue]:
    """Pure: Rhubarb's `-f json` output -> sorted list[VisemeCue].

    Unknown codes map to Viseme.X and are logged at debug level rather than
    raising, since a future Rhubarb version adding a new code shouldn't
    break playback.
    """
    cues: list[VisemeCue] = []
    for raw_cue in raw.get("mouthCues", []):
        code = raw_cue["value"]
        viseme = _RHUBARB_CODE_TO_VISEME.get(code)
        if viseme is None:
            logger.debug("unrecognized rhubarb mouth cue value %r, using Viseme.X", code)
            viseme = Viseme.X
        cues.append(VisemeCue(start=float(raw_cue["start"]), end=float(raw_cue["end"]), viseme=viseme))
    cues.sort(key=lambda c: c.start)
    return cues


def plan_viseme_sequence(
    cues: list[VisemeCue], num_windows: int, video_fps: float
) -> list[Viseme]:
    """Pure: pick one Viseme per video-frame window from a cue timeline.

    For window i (window_start = i / video_fps), picks the viseme of the
    cue whose [start, end) contains window_start. Windows before the first
    cue or past the last cue's end fall back to Viseme.X (silence).

    window_start is monotonically increasing and cues are start-sorted, so
    a single forward-scanning pointer suffices (no need to rescan from the
    start for every window).
    """
    result: list[Viseme] = []
    idx = 0
    for i in range(num_windows):
        t = i / video_fps
        while idx < len(cues) - 1 and cues[idx].end <= t:
            idx += 1
        if idx < len(cues) and cues[idx].start <= t < cues[idx].end:
            result.append(cues[idx].viseme)
        else:
            result.append(Viseme.X)
    return result


async def run_rhubarb(
    executable: Path,
    pcm_bytes: bytes,
    *,
    sample_rate: int,
    channels: int,
    dialog_text: str | None = None,
    recognizer: Literal["pocketSphinx", "phonetic"] = "phonetic",
    timeout: float = 15.0,
    on_process_started: Callable[[asyncio.subprocess.Process], None] | None = None,
) -> list[VisemeCue]:
    """Run rhubarb on `pcm_bytes` (raw int16 PCM for one full utterance) and
    return its viseme timeline.

    Raises RhubarbError on nonzero exit, timeout, or unparseable output.
    """
    with tempfile.TemporaryDirectory(prefix="visage_rhubarb_") as tmp_str:
        tmp = Path(tmp_str)
        wav_path = tmp / "utterance.wav"
        write_wav(wav_path, pcm_bytes, sample_rate=sample_rate, channels=channels)

        out_path = tmp / "output.json"
        argv = [str(executable), "-f", "json", "-o", str(out_path)]
        if dialog_text:
            dialog_path = tmp / "dialog.txt"
            dialog_path.write_text(dialog_text, encoding="utf-8")
            argv += ["-d", str(dialog_path)]
        elif recognizer == "phonetic":
            argv += ["-r", "phonetic"]
        argv.append(str(wav_path))

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if on_process_started is not None:
            on_process_started(proc)

        try:
            _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError as e:
            proc.kill()
            await proc.wait()
            raise RhubarbError(f"rhubarb timed out after {timeout}s") from e

        if proc.returncode != 0:
            raise RhubarbError(
                f"rhubarb exited {proc.returncode}: {stderr.decode(errors='replace')[:500]}"
            )

        try:
            raw = json.loads(out_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise RhubarbError(f"failed to read rhubarb output: {e}") from e

        return parse_rhubarb_json(raw)
