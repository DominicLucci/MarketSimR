"""The spread decomposition and the pull-quotes-on-news option."""

from types import SimpleNamespace

import numpy as np
import pytest

from marketsim.config import SimConfig
from marketsim.events import OrderAccepted, OrderCancelled, OrderExpired, Side, Trade
from marketsim.metrics import IMPACT_HORIZON, need_met, spread_decomposition, summarize
from marketsim.news import news_steps
from marketsim.simulation import DEPTH_WINDOW, run_simulation


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
    assert result == {
        "effective_spread": 20.0, "price_impact": 9.0, "realized_spread": 11.0,
        "impact_immediate": 0.0, "impact_later": 9.0,  # the mid did not move on the trades' own steps
        "n_trades_decomposed": 2,
    }


def test_impact_splits_into_the_trades_own_step_and_what_follows():
    """Quotes 990 / 1010 before a buy at 1010. The mid is 1004 at the end of that step (the
    offer was used up) and 1006 ten steps later: immediate 2(1004-1000)=8, later 2(1006-1004)=4."""
    mid = np.full(30, 1000.0)
    mid[0], mid[IMPACT_HORIZON] = 1004.0, 1006.0
    fake = SimpleNamespace(events=[trade(0, 1010, Side.BUY)], decisions=[{"best_bid": 990, "best_ask": 1010}] * 30, mid_path=mid)
    result = spread_decomposition(fake)
    assert (result["impact_immediate"], result["impact_later"], result["price_impact"]) == (8.0, 4.0, 12.0)
    mid[0] = np.nan  # one-sided at the end of its own step: still in the total, out of the split
    result = spread_decomposition(fake)
    assert result["price_impact"] == 12.0 and result["impact_immediate"] is None


def test_need_met_counts_fills_from_each_arrivals_own_order():
    """Arrival 1 (better informed) is 4 shares from target and its order fills 3.
    Arrival 2 (other group) is 2 from target and fills nothing. Arrival 3 is at target."""
    fills = [
        Trade(seq=1, time=1, price=1000, quantity=2, buy_order_id=10, sell_order_id=99, buyer_id=1, seller_id=5, aggressor=Side.BUY),
        Trade(seq=2, time=2, price=1000, quantity=1, buy_order_id=10, sell_order_id=98, buyer_id=1, seller_id=6, aggressor=Side.SELL),
    ]
    decisions = [
        {"informed": True, "target": 14, "shares": 10, "order_id": 10},
        {"informed": False, "target": 8, "shares": 10, "order_id": 11},
        {"informed": False, "target": 10, "shares": 10, "order_id": None},
    ]
    result = need_met(SimpleNamespace(events=fills, decisions=decisions))
    assert result == {"need_met": 3 / 6, "need_met_informed": 3 / 4, "need_met_uninformed": 0.0}
    assert need_met(SimpleNamespace(events=[], decisions=decisions[2:]))["need_met"] is None


def test_depth_matches_a_book_rebuilt_from_the_event_log():
    """Every depth sample equals a count made independently from the event log: the orders
    resting at the end of that step, within DEPTH_WINDOW ticks of their own mid-quote."""
    result = run_simulation(SimConfig(seed=5, n_steps=400), check_invariants=True)
    assert len(result.depth_samples) > 20
    for time, bid_depth, ask_depth in result.depth_samples:
        resting: dict[int, list] = {}  # order id -> [side, price, remaining]
        for event in result.events:
            if event.time > time:
                break
            if isinstance(event, OrderAccepted):
                resting[event.order_id] = [event.side, event.price, event.quantity]
            elif isinstance(event, Trade):
                for order_id in (event.buy_order_id, event.sell_order_id):
                    if order_id in resting:
                        resting[order_id][2] -= event.quantity
            elif isinstance(event, (OrderCancelled, OrderExpired)):
                resting.pop(event.order_id, None)
        live = [o for o in resting.values() if o[2] > 0]
        bids = [o for o in live if o[0] is Side.BUY]
        asks = [o for o in live if o[0] is Side.SELL]
        mid = (max(o[1] for o in bids) + min(o[1] for o in asks)) / 2
        assert bid_depth == sum(o[2] for o in bids if o[1] >= mid - DEPTH_WINDOW)
        assert ask_depth == sum(o[2] for o in asks if o[1] <= mid + DEPTH_WINDOW)


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
    assert 0.0 <= summary["need_met"] <= 1.0 and summary["depth_near_mid"] > 0
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
