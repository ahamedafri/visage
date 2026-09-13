"""A small, pure, deterministic idle-blink timer.

Phase 2b scope decision: blinking only. Idle head-sway was considered too
(see README roadmap) but needs off-canvas padding + transform logic that's
a bigger lift for the visual payoff versus a simple, well-understood
blink — deferred rather than half-built.

No wall-clock/asyncio dependency: callers advance the clock by exactly the
duration of audio they just processed (one video-frame window), which
keeps this trivially unit-testable and frame-accurate to the actual video
output instead of drifting against real time.
"""

from __future__ import annotations

import random


class BlinkDriver:
    def __init__(
        self,
        *,
        min_interval: float = 2.5,
        max_interval: float = 6.0,
        blink_duration: float = 0.15,
        rng: random.Random | None = None,
    ) -> None:
        """
        Args:
            min_interval/max_interval: seconds between the end of one blink
                and the start of the next, randomized per-blink so it doesn't
                look mechanical.
            blink_duration: how long the eyes stay closed per blink.
            rng: inject a seeded `random.Random()` for deterministic tests;
                defaults to a fresh, unseeded one.
        """
        self._min_interval = min_interval
        self._max_interval = max_interval
        self._blink_duration = blink_duration
        self._rng = rng if rng is not None else random.Random()

        self._time_to_next_blink = self._sample_interval()
        self._time_in_current_blink: float | None = None  # None = not blinking

    def _sample_interval(self) -> float:
        return self._rng.uniform(self._min_interval, self._max_interval)

    def advance(self, dt: float) -> bool:
        """Advance the internal clock by `dt` seconds. Returns True if the
        eyes should be closed for the window that just elapsed."""
        if self._time_in_current_blink is not None:
            self._time_in_current_blink += dt
            if self._time_in_current_blink >= self._blink_duration:
                self._time_in_current_blink = None
                self._time_to_next_blink = self._sample_interval()
                return False
            return True

        self._time_to_next_blink -= dt
        if self._time_to_next_blink <= 0:
            self._time_in_current_blink = 0.0
            return True

        return False
