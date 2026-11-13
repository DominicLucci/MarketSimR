"""Calibrated trust: the fixed-point search and the per-share settings that carry it."""

import pytest

from marketsim.calibrate import bisect_fixed_point, calibrate, produced_error
from marketsim.config import SimConfig
from marketsim.experiment import CALIBRATED_PRICE_SD, DESIGNS, SHARES, calibrated, run_grid

SMALL = SimConfig(n_steps=600)


def test_bisection_finds_the_crossing_of_a_decreasing_map():
    # f(s) = 1200 / s crosses s at sqrt(1200) = 34.64; slope there is -1, where s <- f(s) would cycle
    point, trace = bisect_fixed_point(lambda s: 1200 / s)
    assert point == pytest.approx(1200**0.5, abs=0.1)
    assert trace[:2] == [(10.0, 120.0), (200.0, 6.0)]


def test_bisection_refuses_a_bracket_with_no_crossing():
    with pytest.raises(ValueError, match="no crossing"):
        bisect_fixed_point(lambda s: s / 2)  # f(low) < low: prices would be better than trusted everywhere


def test_calibrated_trust_is_self_consistent_on_a_small_market():
    seeds = (1000, 1001)
    found = calibrate(SMALL, [0.25], seeds)[0.25]["price_sd"]
    produced = produced_error(SMALL.with_(informed_share=0.25), found, seeds)
    assert produced == pytest.approx(found, rel=0.05)


def test_per_share_settings_reach_each_run():
    variant = {"x": {"learn_from_prices": True, "by_share": {s: {"price_sd": 20.0 + 10 * i} for i, s in enumerate(SHARES)}}}
    runs, _ = run_grid(SMALL.with_(n_steps=200), [0], variant)
    for i, share in enumerate(SHARES):  # same as running that share alone with that trust
        alone, _ = run_grid(SMALL.with_(n_steps=200), [0], {"x": {"learn_from_prices": True, "price_sd": 20.0 + 10 * i}})
        row = alone[alone["informed_share"] == share].reset_index(drop=True)
        assert runs[runs["informed_share"] == share].reset_index(drop=True).equals(row)


def test_per_share_settings_must_cover_every_share():
    partial = {"x": {"learn_from_prices": True, "by_share": {0.0: {"price_sd": 40.0}}}}
    with pytest.raises(ValueError, match="every share"):
        run_grid(SMALL.with_(n_steps=50), [0], partial)


def test_stored_calibration_covers_both_designs_and_every_share():
    assert set(CALIBRATED_PRICE_SD) == set(DESIGNS)
    for design in DESIGNS:
        assert set(CALIBRATED_PRICE_SD[design]) == set(SHARES)
        assert DESIGNS[design]["variants"]["learn_calibrated"] == calibrated(design)
