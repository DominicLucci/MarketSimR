"""The Glosten-Milgrom benchmark: formulas checked by hand and by a second method, and the
exchange simulation checked against them."""

import numpy as np
import pandas as pd
import pytest

from marketsim import glosten_milgrom as gm


def test_belief_and_first_quotes_by_hand():
    # One net buy multiplies the odds of a high value by 1.25 / 0.75 = 5/3: P = 5/8.
    assert gm.belief_after(0, 0.25) == 0.5
    assert gm.belief_after(1, 0.25) == pytest.approx(5 / 8)
    assert gm.belief_after(-1, 0.25) == pytest.approx(3 / 8)
    # At the prior, ask = 9,900 + 200 x 0.625 = 10,025 and bid = 9,975: spread mu x gap.
    assert gm.quotes(0.5, gm.GMConfig(mu=0.25)) == (9_975, 10_025)
    assert gm.quotes(0.5, gm.GMConfig(mu=0.50)) == (9_950, 10_050)


def test_quotes_stay_one_tick_apart_when_the_dealer_is_certain():
    bid, ask = gm.quotes(1.0, gm.GMConfig(mu=0.5))
    assert (bid, ask) == (10_099, 10_100)


def test_exact_path_agrees_with_a_forward_recursion():
    config = gm.GMConfig(mu=0.25, n_steps=25)
    exact = gm.exact_path(config)
    assert exact.loc[0, "exact_spread"] == 50.0
    spread = np.zeros(config.n_steps)
    for p_buy in ((1 + config.mu) / 2, (1 - config.mu) / 2):
        dist = {0: 1.0}
        for t in range(config.n_steps):
            spread[t] += 0.5 * sum(w * (lambda b, a: a - b)(*gm.quotes(gm.belief_after(n, config.mu), config)) for n, w in dist.items())
            step: dict[int, float] = {}
            for n, w in dist.items():
                step[n + 1] = step.get(n + 1, 0.0) + w * p_buy
                step[n - 1] = step.get(n - 1, 0.0) + w * (1 - p_buy)
            dist = step
    assert exact["exact_spread"].to_numpy() == pytest.approx(spread, abs=1e-9)


def test_without_rounding_the_dealer_breaks_even():
    # Rounding to whole ticks is the only source of dealer profit: with a 1,000,000-tick gap
    # rounding is negligible and expected profit per trade, relative to the gap, vanishes.
    exact = gm.exact_path(gm.GMConfig(mu=0.25, v_low=1_000_000, v_high=2_000_000, n_steps=20))
    assert abs(exact["exact_dealer_profit"]).max() < 1.0  # under one tick on a 1,000,000-tick gap


def test_every_step_is_one_trade_with_the_dealer_at_its_quote():
    run = gm.simulate(gm.GMConfig(mu=0.25, n_steps=40, seed=3))
    assert len(run) == 40 and run.loc[0, "spread"] == 50
    assert (run["trade_price"] == np.where(run["buy"], run["ask"], run["bid"])).all()
    assert (run["spread"] >= 1).all()


def test_simulated_spread_matches_the_formula_on_average():
    config = gm.GMConfig(mu=0.5, n_steps=30)
    runs = pd.concat([gm.simulate(gm.GMConfig(mu=0.5, n_steps=30, seed=s)) for s in range(1_500)], ignore_index=True)
    per_seed = runs.groupby("seed")["spread"].mean()
    exact = gm.exact_path(config)["exact_spread"].mean()
    z = (per_seed.mean() - exact) / (per_seed.std(ddof=1) / np.sqrt(len(per_seed)))
    assert abs(z) < 4


def test_check_passes_on_fresh_output(tmp_path, monkeypatch):
    monkeypatch.setattr(gm, "MUS", (0.25,))
    monkeypatch.setattr(gm.run_benchmark, "__defaults__", ((0.25,), 20))
    out = gm.write(tmp_path / "gm", n_seeds=30, with_chart=False)
    gm.main(["--check", "--out", str(out)])
