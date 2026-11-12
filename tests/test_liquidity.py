"""The spread decomposition and the pull-quotes-on-news option."""

from types import SimpleNamespace

import numpy as np
import pytest

from marketsim.config import SimConfig
from marketsim.events import OrderCancelled, Side, Trade
from marketsim.metrics import IMPACT_HORIZON, spread_decomposition, summarize
from marketsim.news import news_steps
from marketsim.simulation import run_simulation


def trade(time, price, aggressor):
    return Trade(seq=time + 1, time=time, price=price, quantity=1, buy_order_id=1, sell_order_id=2, buyer_id=1, seller_id=2, aggressor=aggressor)


def test_decomposition_on_two_hand_worked_trades():
    """Quotes are 990 / 1010 (mid 1000) before both trades.
    A buy lifts the offer at 1010 and the mid is 1006 ten steps later:
        effective 2(1010-1000)=20, impact 2(1006-1000)=12, realized 2(1010-1006)=8.
    A sell hits the bid at 990 and the mid is 997 ten steps later:
        effective 2(1000-990)=20, impact 2(1000-997)=6, realized 2(997-990)=14."""
    mid = np.full(30, 1000.0)
    mid[0 + IMPACT_HORIZON], mid[1 + IMPACT_HORIZON] = 1006.0, 997.0
    quotes = {"best_bid": 990, "best_ask": 1010}
    fake = SimpleNamespace(
        events=[trade(0, 1010, Side.BUY), trade(1, 990, Side.SELL)],
        decisions=[dict(quotes) for _ in range(30)],
        mid_path=mid,
    )
    result = spread_decomposition(fake)
    assert result == {"effective_spread": 20.0, "price_impact": 9.0, "realized_spread": 11.0, "n_trades_decomposed": 2}


def test_trades_without_the_needed_quotes_are_left_out():
    mid = np.full(30, 1000.0)
    mid[5 + IMPACT_HORIZON] = np.nan
    decisions = [{"best_bid": 990, "best_ask": 1010} for _ in range(30)]
    decisions[3] = {"best_bid": None, "best_ask": 1010}
    fake = SimpleNamespace(
        events=[trade(3, 1010, Side.BUY), trade(5, 1010, Side.BUY), trade(25, 1010, Side.BUY), trade(7, 1010, Side.BUY)],
        decisions=decisions,
        mid_path=mid,
    )
    assert spread_decomposition(fake)["n_trades_decomposed"] == 1  # only the trade at step 7
    empty = spread_decomposition(SimpleNamespace(events=[], decisions=decisions, mid_path=mid))
    assert empty["effective_spread"] is None and empty["n_trades_decomposed"] == 0


def test_parts_add_up_on_a_real_run():
    summary = summarize(run_simulation(SimConfig(seed=2, n_steps=1500)))
    assert summary["n_trades_decomposed"] > 100
    assert summary["effective_spread"] == pytest.approx(summary["realized_spread"] + summary["price_impact"])
    assert summary["effective_spread"] > 0  # the incoming side pays to trade


def test_pulling_quotes_on_news_empties_the_book_at_each_news_step():
    config = SimConfig(seed=4, n_steps=700, news_every=100, cancel_on_news=True)
    result = run_simulation(config, check_invariants=True)
    for step in news_steps(result.value_path):
        seen = result.decisions[step]  # what the arriving trader saw, after the pull
        assert seen["best_bid"] is None and seen["best_ask"] is None
    pulled = [e for e in result.events if isinstance(e, OrderCancelled) and e.time in set(news_steps(result.value_path).tolist())]
    assert len(pulled) > 20
    # Off by default, and the option changes the market when on.
    assert SimConfig().cancel_on_news is False
    assert run_simulation(config.with_(cancel_on_news=False)).events != result.events
