"""Checks on the simulation layer: replay, information access, pairing and group neutrality."""

from __future__ import annotations

from dataclasses import fields

import numpy as np
import pytest

from marketsim.config import MODEL_VERSION, SimConfig
from marketsim.events import OrderAccepted, OrderCancelled, OrderExpired, Side, Trade
from marketsim.exchange import Quotes
from marketsim.metrics import summarize, trader_outcomes
from marketsim.simulation import run_simulation
from marketsim.traders import Intent, TraderView, decide
from marketsim.world import arrival_schedule, informed_traders, value_path

SMALL = SimConfig(seed=7, n_steps=600, informed_share=0.25)


def view(signal=10_012.3, target=12, shares=10, cash=100_000, available_cash=None, available_shares=None):
    return TraderView(
        time=0,
        signal=signal,
        target_shares=target,
        cash=cash,
        shares=shares,
        available_cash=cash if available_cash is None else available_cash,
        available_shares=shares if available_shares is None else available_shares,
        quotes=Quotes(None, 0, None, 0),
    )


# ------------------------------------------------------------------ decision rule


def test_buyer_bids_signal_minus_margin_rounded_down():
    intent, reason = decide(view(signal=10_012.3, target=12, shares=10), margin=20, max_order_size=5)
    assert intent == Intent(Side.BUY, 9_992, 2) and reason == "below target"


def test_seller_offers_signal_plus_margin_rounded_up():
    intent, reason = decide(view(signal=10_012.3, target=3, shares=10), margin=20, max_order_size=5)
    assert intent == Intent(Side.SELL, 10_033, 5) and reason == "above target"  # gap 7, capped at 5


def test_no_order_at_target_or_without_resources():
    assert decide(view(target=10, shares=10), 20, 5) == (None, "at target")
    assert decide(view(target=12, shares=10, cash=5_000), 20, 5)[0] is None  # cannot afford one share
    assert decide(view(target=8, shares=10, available_shares=0), 20, 5)[0] is None


def test_order_size_respects_available_cash():
    intent, _ = decide(view(signal=1_020.0, target=15, shares=10, cash=2_500), margin=20, max_order_size=5)
    assert intent == Intent(Side.BUY, 1_000, 2)  # wants 5, can fund 2 at its own limit


def test_trader_view_cannot_carry_the_underlying_value():
    assert {f.name for f in fields(TraderView)} == {
        "time",
        "signal",
        "target_shares",
        "cash",
        "shares",
        "available_cash",
        "available_shares",
        "quotes",
    }


# ------------------------------------------------------------------------- replay


def test_same_version_config_and_seed_reproduce_the_run_exactly():
    first = run_simulation(SMALL, check_invariants=True)
    second = run_simulation(SimConfig.from_dict(SMALL.to_dict()))
    assert first.model_version == second.model_version == MODEL_VERSION
    assert first.events == second.events
    assert first.final_accounts == second.final_accounts
    assert first.decisions == second.decisions
    assert summarize(first) == summarize(second)


def test_different_seeds_give_different_markets():
    assert run_simulation(SMALL).events != run_simulation(SMALL.with_(seed=8)).events


# -------------------------------------------------------------- information access


def test_orders_do_not_depend_on_future_values():
    """Change the value path after step 300. Everything up to step 299 must be unchanged."""
    cut = 300
    base = run_simulation(SMALL)
    altered_path = base.value_path.copy()
    altered_path[cut:] *= 1.5
    altered = run_simulation(SMALL, value_override=altered_path)

    assert [e for e in base.events if e.time < cut] == [e for e in altered.events if e.time < cut]
    assert base.decisions[:cut] == altered.decisions[:cut]
    # And the change is large enough to matter afterwards, so the check is not vacuous.
    assert base.decisions[cut:] != altered.decisions[cut:]


# ----------------------------------------------------------------------- pairing


def test_value_path_is_positive_and_independent_of_everything_but_the_seed():
    path = value_path(SMALL)
    assert path[0] == SMALL.initial_value and np.all(path > 0)
    assert len(set(path.tolist())) > 3  # some news arrived
    changed = SMALL.with_(informed_share=0.75, margin=5.0, sigma_uninformed=300.0, order_lifetime=5, max_need=2)
    assert np.array_equal(value_path(changed), path)
    assert np.array_equal(arrival_schedule(changed), arrival_schedule(SMALL))
    # A longer run extends the same history instead of drawing a new one.
    longer = SMALL.with_(n_steps=900)
    assert np.array_equal(value_path(longer)[:600], path)
    assert np.array_equal(arrival_schedule(longer)[:600], arrival_schedule(SMALL))


def test_informed_sets_are_nested_as_the_share_grows():
    sets = [informed_traders(SMALL.with_(informed_share=s)) for s in (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)]
    assert [len(s) for s in sets] == [0, 4, 10, 20, 30, 40]
    assert all(small <= large for small, large in zip(sets, sets[1:]))


def test_each_trader_keeps_the_same_luck_across_settings():
    low = run_simulation(SMALL.with_(informed_share=0.25))
    high = run_simulation(SMALL.with_(informed_share=0.5))
    assert np.array_equal(low.value_path, high.value_path)
    switched = 0
    for a, b in zip(low.decisions, high.decisions):
        assert (a["time"], a["trader"], a["target"]) == (b["time"], b["trader"], b["target"])
        value = float(low.value_path[a["time"]])
        if a["informed"] == b["informed"]:
            assert a["signal"] == b["signal"]
        else:  # newly informed: same standardized error, smaller scale
            switched += 1
            z_low = (a["signal"] - value) / SMALL.sigma_uninformed
            z_high = (b["signal"] - value) / SMALL.sigma_informed
            assert z_low == pytest.approx(z_high, abs=1e-9)
    assert switched > 0


def test_group_label_is_irrelevant_when_information_is_equal():
    """Equal-information control: with one signal precision, relabelling changes nothing."""
    equal = SMALL.with_(sigma_informed=60.0, sigma_uninformed=60.0)
    runs = [run_simulation(equal.with_(informed_share=s)) for s in (0.0, 0.1, 0.75)]
    assert runs[0].informed != runs[2].informed
    assert runs[0].events == runs[1].events == runs[2].events
    assert runs[0].final_accounts == runs[2].final_accounts


# ----------------------------------------------------------------------- outcomes


def test_trading_gains_sum_to_zero_and_nothing_leaks():
    result = run_simulation(SMALL, check_invariants=True)
    outcomes = trader_outcomes(result)
    assert sum(o["trading_gain"] for o in outcomes) == pytest.approx(0.0, abs=1e-6)
    assert sum(cash for cash, _ in result.final_accounts.values()) == SMALL.n_traders * SMALL.initial_cash
    assert sum(shares for _, shares in result.final_accounts.values()) == SMALL.n_traders * SMALL.initial_shares


def test_each_trader_has_at_most_one_live_order():
    result = run_simulation(SMALL)
    live: dict[int, int] = {}  # order id -> trader
    remaining: dict[int, int] = {}
    for event in result.events:
        if isinstance(event, OrderAccepted):
            assert event.trader_id not in live.values()
            live[event.order_id], remaining[event.order_id] = event.trader_id, event.quantity
        elif isinstance(event, Trade):
            for order_id in (event.buy_order_id, event.sell_order_id):
                remaining[order_id] -= event.quantity
                if remaining[order_id] == 0:
                    live.pop(order_id, None)
        elif isinstance(event, (OrderCancelled, OrderExpired)):
            live.pop(event.order_id, None)


def test_summary_matches_an_independent_recount():
    result = run_simulation(SMALL)
    summary = summarize(result)
    trades = [e for e in result.events if isinstance(e, Trade)]
    assert summary["n_trades"] == len(trades) > 0
    error = sum(abs(t.price - result.value_path[t.time]) for t in trades) / len(trades)
    assert summary["price_error"] == pytest.approx(error)
    assert summary["n_quote_samples"] == 60
    assert summary["share_no_bid"] + summary["share_two_sided"] <= 1.0 + 1e-12
    informed_gain = np.mean([o["trading_gain"] for o in trader_outcomes(result) if o["informed"]])
    assert summary["trading_gain_informed"] == pytest.approx(informed_gain)


def test_missing_measures_are_reported_as_unavailable():
    nobody_informed = summarize(run_simulation(SMALL.with_(informed_share=0.0)))
    assert nobody_informed["trading_gain_informed"] is None
    assert nobody_informed["trading_gain_uninformed"] == pytest.approx(0.0, abs=1e-6)
    everyone_informed = summarize(run_simulation(SMALL.with_(informed_share=1.0)))
    assert everyone_informed["wealth_change_uninformed"] is None

    # A margin far wider than any disagreement leaves a market with quotes but no trades.
    no_trades = summarize(run_simulation(SMALL.with_(margin=5_000.0, news_prob=0.0)))
    assert no_trades["n_trades"] == 0 and no_trades["volume"] == 0
    assert no_trades["price_error"] is None
    assert no_trades["spread"] is not None


def test_config_rejects_shares_that_split_a_trader():
    with pytest.raises(ValueError):
        SimConfig(n_traders=40, informed_share=0.33)
    with pytest.raises(ValueError):
        SimConfig.from_dict({"sede": 1})
