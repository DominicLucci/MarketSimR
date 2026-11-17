"""Calibrated trust: the fixed-point search and the per-share settings that carry it."""

import pytest

import json

from marketsim.calibrate import bisect_fixed_point, calibrate, calibration_configs, produced_error, store
from marketsim.config import MODEL_VERSION, SimConfig
from marketsim.experiment import (
    BASELINE, DESIGNS, SHARES, calibrated_variant_names, design_shares, load_trust_table, resolved_variants, run_grid,
)

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


def test_stored_trust_covers_every_calibrated_variant_at_every_share():
    table = load_trust_table()
    assert table["model_version"] == MODEL_VERSION and table["seeds"] == [1000, 1019]
    for design in DESIGNS:
        names = calibrated_variant_names(design)
        assert set(table["trust"].get(design, {})) == set(names), design
        for name in names:
            assert set(table["trust"][design][name]) == set(design_shares(design)), (design, name)


def test_resolved_variants_fill_in_trust_and_refuse_a_stale_table():
    table = {"model_version": MODEL_VERSION, "seeds": [1000, 1019],
             "trust": {"scheduled_news": {n: {s: 40.0 + s for s in SHARES} for n in calibrated_variant_names("scheduled_news")}}}
    variants = resolved_variants("scheduled_news", table)
    assert variants["main"] == {"by_share": {s: {"price_sd": 40.0 + s} for s in SHARES}}
    assert variants["pull_on_news"]["cancel_on_news"] is True and "trust" not in variants["pull_on_news"]
    assert variants["no_learning"] == {"learn_from_prices": False}
    with pytest.raises(ValueError, match="model"):
        resolved_variants("scheduled_news", {**table, "model_version": "0.2.0-pilot"})
    with pytest.raises(ValueError, match="no calibrated trust"):
        resolved_variants("informed_share", table)


def test_each_calibrated_variant_is_calibrated_under_its_own_rules():
    configs = calibration_configs("informed_share")
    assert set(configs) == set(calibrated_variant_names("informed_share"))
    assert configs["main"].learn_from_prices and configs["main"].urgency_scale == BASELINE["urgency_scale"]
    assert configs["fixed_margin"].urgency_scale == 0 and configs["strong_urgency"].urgency_scale == 5
    assert configs["short_lived_orders"].order_lifetime == 20 and configs["narrow_gap"].sigma_informed == 50.0


def test_store_replaces_one_designs_entries_and_voids_other_model_versions(tmp_path):
    path = tmp_path / "trust.json"
    path.write_text(json.dumps({"model_version": "0.2.0-pilot", "seeds": [1000, 1019], "trust": {"x": {"main": {"0.0": 1.0}}}}))
    store("scheduled_news", {"main": {0.0: {"price_sd": 41.5}, 0.75: {"price_sd": 30.2}}}, path)
    data = json.loads(path.read_text())
    assert data == {"model_version": MODEL_VERSION, "seeds": [1000, 1019], "trust": {"scheduled_news": {"main": {"0.0": 41.5, "0.75": 30.2}}}}
    store("scheduled_news", {"pull_on_news": {0.0: {"price_sd": 50.0}}}, path)  # adds, keeps main
    assert set(json.loads(path.read_text())["trust"]["scheduled_news"]) == {"main", "pull_on_news"}


def test_run_grid_refuses_learning_without_a_stated_trust():
    with pytest.raises(ValueError, match="sets no trust"):
        run_grid(SMALL.with_(n_steps=50), [0], {"x": {"learn_from_prices": True}})
    with pytest.raises(ValueError, match="resolve"):
        run_grid(SMALL.with_(n_steps=50), [0], {"x": {"trust": "calibrated"}})


def test_parallel_runs_equal_a_plain_loop():
    variants = {"a": {}, "b": {"learn_from_prices": True, "price_sd": 40.0, "urgency_scale": 10}}
    one = run_grid(SMALL.with_(n_steps=300), [0, 1], variants, jobs=1)
    two = run_grid(SMALL.with_(n_steps=300), [0, 1], variants, jobs=2)
    assert one[0].equals(two[0]) and one[1].equals(two[1])
