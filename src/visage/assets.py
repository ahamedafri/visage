"""Loading and compositing of avatar art assets.

An asset set is a folder containing:
  - ``face.png``   — the base face/head, RGBA, defines the canvas size
  - ``mouth_<state>.png`` — one RGBA overlay per :class:`MouthState`, same
    canvas size as ``face.png``, transparent everywhere except the mouth

v1 (amplitude-only lip-sync, see ``video_generator.py``) only needs
``mouth_closed.png`` and ``mouth_open.png``. The layout intentionally leaves
room to add more states later (e.g. Rhubarb visemes) without changing the
loading/compositing contract.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from livekit import rtc
from PIL import Image


class MouthState(str, Enum):
    """Named mouth shapes. v1 only uses CLOSED/OPEN (amplitude-based)."""

    CLOSED = "closed"
    OPEN = "open"


class AvatarAssets:
    """Pre-composited (face + mouth) frames, ready to hand to ``rtc.VideoFrame``."""

    def __init__(self, width: int, height: int, frames_rgb: dict[MouthState, bytes]) -> None:
        self._width = width
        self._height = height
        self._frames_rgb = frames_rgb

    @property
    def resolution(self) -> tuple[int, int]:
        return self._width, self._height

    @classmethod
    def load(cls, assets_dir: str | Path, states: tuple[MouthState, ...] = (
        MouthState.CLOSED,
        MouthState.OPEN,
    )) -> "AvatarAssets":
        assets_dir = Path(assets_dir)
        face_path = assets_dir / "face.png"
        if not face_path.exists():
            raise FileNotFoundError(
                f"missing {face_path} — an asset folder needs a face.png "
                "(RGBA) plus one mouth_<state>.png per MouthState"
            )

        face = Image.open(face_path).convert("RGBA")
        width, height = face.size

        frames_rgb: dict[MouthState, bytes] = {}
        for state in states:
            mouth_path = assets_dir / f"mouth_{state.value}.png"
            if not mouth_path.exists():
                raise FileNotFoundError(
                    f"missing {mouth_path} — expected one mouth image per MouthState "
                    f"({', '.join(s.value for s in states)})"
                )
            mouth = Image.open(mouth_path).convert("RGBA")
            if mouth.size != face.size:
                raise ValueError(
                    f"{mouth_path} is {mouth.size}, but face.png is {face.size} — "
                    "mouth overlays must match the face canvas size exactly"
                )
            composited = Image.alpha_composite(face, mouth).convert("RGB")
            frames_rgb[state] = composited.tobytes()

        return cls(width, height, frames_rgb)

    def video_frame(self, state: MouthState) -> rtc.VideoFrame:
        """A fresh ``rtc.VideoFrame`` for the given mouth state.

        Built fresh from cached bytes each call (cheap — no re-compositing)
        so callers never share a mutable frame instance across pushes.
        """
        data = self._frames_rgb.get(state)
        if data is None:
            raise KeyError(f"no frame loaded for mouth state {state!r}")
        return rtc.VideoFrame(
            width=self._width,
            height=self._height,
            type=rtc.VideoBufferType.RGB24,
            data=data,
        )
