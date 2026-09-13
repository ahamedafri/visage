"""Optional real-binary end-to-end check for Rhubarb Lip Sync integration.

Unlike scripts/smoke_test.py (synthetic sine-tone audio, no real binary
needed), this exercises the ACTUAL `rhubarb` executable against a real
speech WAV file you provide — a synthetic tone won't produce meaningful
viseme output since Rhubarb's recognizers expect actual speech formants.

No fixture is bundled with this repo (recording/sourcing one wasn't done
automatically here — point this at any short real speech WAV you have, or
easiest: a short clip of your own agent's actual TTS output).

Usage:
    python scripts/smoke_test_rhubarb.py path/to/speech.wav

If `rhubarb` isn't found on this machine (see README for install steps),
this exits cleanly (code 0) with a note — it never fails a machine that
simply hasn't installed the optional binary.
"""

from __future__ import annotations

import asyncio
import sys
import wave
from pathlib import Path

from visage.rhubarb import RhubarbNotFoundError, find_rhubarb_executable, run_rhubarb


async def main() -> int:
    try:
        executable = find_rhubarb_executable()
    except RhubarbNotFoundError as e:
        print(f"rhubarb not found — skipping real end-to-end check.\n{e}")
        return 0

    print(f"found rhubarb at: {executable}")

    if len(sys.argv) < 2:
        print(
            "\nUsage: python scripts/smoke_test_rhubarb.py path/to/speech.wav\n"
            "(needs a short real speech WAV — a synthetic tone won't produce "
            "meaningful viseme output)"
        )
        return 0

    wav_path = Path(sys.argv[1])
    if not wav_path.exists():
        print(f"no such file: {wav_path}")
        return 1

    with wave.open(str(wav_path), "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        pcm_bytes = wf.readframes(wf.getnframes())

    if sample_width != 2:
        print(f"expected 16-bit PCM, got sample width {sample_width} bytes — convert first")
        return 1

    print(f"running rhubarb on {wav_path} ({sample_rate}Hz, {channels}ch)...")
    cues = await run_rhubarb(executable, pcm_bytes, sample_rate=sample_rate, channels=channels)

    print(f"\n{len(cues)} viseme cues:")
    for cue in cues:
        print(f"  {cue.start:6.2f}s - {cue.end:6.2f}s : {cue.viseme.value}")

    distinct = {cue.viseme for cue in cues}
    if len(distinct) <= 1:
        print(
            f"\nWARNING: only {len(distinct)} distinct viseme(s) seen — "
            "expected several for real speech. Check the input audio."
        )
        return 1

    print(f"\nOK — {len(distinct)} distinct visemes seen.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
