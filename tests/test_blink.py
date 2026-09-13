import random

from visage.blink import BlinkDriver


def test_blink_sequence_is_deterministic_with_fixed_interval():
    # min == max interval removes randomness from *when* blinks start, so
    # the exact True/False sequence is fully predictable and can be
    # asserted call-by-call.
    driver = BlinkDriver(
        min_interval=0.5, max_interval=0.5, blink_duration=0.2, rng=random.Random(0)
    )
    dt = 0.1

    results = [driver.advance(dt) for _ in range(7)]

    # 0.5s / 0.1s dt takes 5 steps to reach ~0 (float accumulation makes it
    # land just above zero on step 4, so the blink actually starts on step
    # 5); blink_duration=0.2s then spans 2 more dt-steps.
    assert results == [False, False, False, False, False, True, True]


def test_blink_recurs_after_reset():
    driver = BlinkDriver(
        min_interval=0.3, max_interval=0.3, blink_duration=0.1, rng=random.Random(0)
    )
    dt = 0.1

    # first cycle: 3 steps to blink (0.3/0.1), 1 step blinking
    first_cycle = [driver.advance(dt) for _ in range(4)]
    assert first_cycle == [False, False, True, False]

    # second cycle should look the same shape (interval is fixed)
    second_cycle = [driver.advance(dt) for _ in range(4)]
    assert second_cycle == [False, False, True, False]


def test_blink_interval_is_randomized_within_bounds():
    driver = BlinkDriver(
        min_interval=1.0, max_interval=2.0, blink_duration=0.05, rng=random.Random(42)
    )
    # sampled interval must fall within [min_interval, max_interval]
    assert 1.0 <= driver._time_to_next_blink <= 2.0
