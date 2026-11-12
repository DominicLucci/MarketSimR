"""The news event study, checked on price series built by hand."""

import numpy as np
import pytest

from marketsim.config import SimConfig
from marketsim.events import Trade
from marketsim.metrics import summarize
from marketsim.news import half_life, isolated_events, last_trade_path, news_steps, response_curve
from marketsim.simulation import run_simulation

W = 10  # a short window keeps the hand-built series small


def flat_with_jumps(n, jumps, start=1000.0):
    values = np.full(n, start)
    for step, size in jumps:
        values[step:] += size
    return values


def test_news_steps_and_isolation():
    values = flat_with_jumps(100, [(5, 10), (30, -20), (36, 5), (60, 8), (95, 3)])
    assert news_steps(values).tolist() == [5, 30, 36, 60, 95]
    # 30 and 36 are within 10 steps of each other; 95 has no full window left; 5 and 60 qualify.
    assert isolated_events(values, W) == [5, 60]
    assert isolated_events(flat_with_jumps(100, []), W) == []


def test_price_that_adjusts_at_once_reflects_all_the_news_from_step_zero():
    values = flat_with_jumps(60, [(20, 50)])
    curve = response_curve(values, values.copy(), W)
    assert curve["n_events"] == 1
    assert curve["reflected"].tolist() == pytest.approx([1.0] * (W + 1))
    assert half_life(curve["reflected"]) == 0


def test_price_that_never_moves_reflects_nothing():
    values = flat_with_jumps(60, [(20, -50)])
    curve = response_curve(values, np.full(60, 1000.0), W)
    assert curve["reflected"].tolist() == pytest.approx([0.0] * (W + 1))
    assert half_life(curve["reflected"]) is None


def test_gradual_adjustment_and_half_life():
    """After a jump of +40 the price closes a tenth of the gap per step, starting one step later."""
    values = flat_with_jumps(60, [(20, 40)])
    prices = np.full(60, 1000.0)
    for k in range(1, 11):
        prices[20 + k :] = 1000.0 + 4.0 * k
    curve = response_curve(values, prices, W)
    assert curve["reflected"].tolist() == pytest.approx([k / 10 for k in range(W + 1)])
    assert half_life(curve["reflected"]) == 5


def test_direction_is_measured_relative_to_the_news_and_events_pool_as_a_ratio_of_sums():
    """A fall of 30 fully reflected and a rise of 10 not reflected at all: 30 of 40 = 75%."""
    values = flat_with_jumps(120, [(20, -30), (70, 10)])
    prices = np.full(120, 1000.0)
    prices[20:] = 970.0  # follows the first news at once, ignores the second
    curve = response_curve(values, prices, W)
    assert curve["n_events"] == 2
    assert curve["reflected"].tolist() == pytest.approx([0.75] * (W + 1))


def test_missing_prices_are_skipped_not_treated_as_zero():
    values = flat_with_jumps(120, [(20, 40), (70, 40)])
    prices = values.copy()
    prices[19] = np.nan  # no price just before the first event: that event is dropped
    prices[73] = np.nan  # a gap after the second event: only that step drops out
    curve = response_curve(values, prices, W)
    assert curve["n_events"] == 1
    assert curve["reflected"][2] == pytest.approx(1.0)
    assert np.isnan(curve["reflected"][3])
    assert np.isnan(response_curve(values, np.full(120, np.nan), W)["reflected"]).all()


def test_last_trade_path_carries_the_latest_price_forward():
    trade = lambda time, price: Trade(seq=time + 1, time=time, price=price, quantity=1, buy_order_id=1, sell_order_id=2, buyer_id=1, seller_id=2, aggressor=None)
    path = last_trade_path([trade(2, 100), trade(4, 103), trade(4, 105)], 7)
    assert np.isnan(path[:2]).all()
    assert path[2:].tolist() == [100, 100, 105, 105, 105]


def test_run_summary_reports_the_new_measures():
    result = run_simulation(SimConfig(seed=0))
    summary = summarize(result)
    assert summary["news_events"] == len(isolated_events(result.value_path)) > 5
    assert 0.0 < summary["news_in_mid_40"] < 1.5
    assert summary["mid_error"] == pytest.approx(float(np.nanmean(np.abs(result.mid_path - result.value_path))))
    pairs = ("both_informed", "mixed", "neither_informed")
    assert sum(summary[f"n_trades_{p}"] for p in pairs) == summary["n_trades"]
    weighted = sum(summary[f"n_trades_{p}"] * (summary[f"price_error_{p}"] or 0.0) for p in pairs)
    assert weighted / summary["n_trades"] == pytest.approx(summary["price_error"])

    quiet = summarize(run_simulation(SimConfig(seed=0, news_prob=0.0, n_steps=500)))
    assert quiet["news_events"] == 0 and quiet["news_in_mid_10"] is None and quiet["news_half_life_mid"] is None
