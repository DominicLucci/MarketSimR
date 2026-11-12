"""The first case from the handoff, checked value by value."""

from marketsim.events import OrderAccepted, OrderCancelled, Trade
from marketsim.example import BUYER, SELLER, run

from .helpers import BUY, SELL, exchange_with, trades


def test_example_script_reproduces_the_handoff_table():
    exchange = run(verbose=False)
    kinds = [type(e).__name__ for e in exchange.events]
    assert kinds == [
        "AccountOpened",
        "AccountOpened",
        "OrderAccepted",
        "OrderAccepted",
        "Trade",
        "OrderCancelled",
    ]
    assert [e.seq for e in exchange.events] == [1, 2, 3, 4, 5, 6]


def test_each_step_of_the_example():
    ex = exchange_with((SELLER, 0, 5), (BUYER, 5000, 0))
    seller, buyer = ex.accounts[SELLER], ex.accounts[BUYER]

    ask = ex.submit_limit(SELLER, SELL, 1000, 3)
    assert (seller.shares, seller.reserved_shares, seller.available_shares) == (5, 3, 2)

    bid = ex.submit_limit(BUYER, BUY, 1010, 2)
    # One trade of two shares at the resting price of $10.00, not the $10.10 limit.
    assert trades(ex) == [(2, 1000, BUYER, SELLER)]
    trade = ex.events[-1]
    assert isinstance(trade, Trade)
    assert (trade.buy_order_id, trade.sell_order_id, trade.aggressor) == (bid, ask, BUY)

    # Buyer reserved $20.20, spent $20.00 and got $0.20 back as available cash.
    assert (buyer.cash, buyer.reserved_cash, buyer.available_cash, buyer.shares) == (3000, 0, 3000, 2)
    # Seller has $20.00, three shares, one still reserved for the rest of the order.
    assert (seller.cash, seller.shares, seller.reserved_shares) == (2000, 3, 1)
    assert ex.book.get(ask).remaining == 1
    assert ex.book.get(bid) is None  # fully filled, nothing rests

    assert ex.cancel(SELLER, ask) is True
    assert isinstance(ex.events[-1], OrderCancelled) and ex.events[-1].remaining == 1
    assert (seller.shares, seller.reserved_shares, seller.available_shares) == (3, 0, 3)
    assert len(ex.book) == 0

    assert buyer.cash + seller.cash == 5000
    assert buyer.shares + seller.shares == 5


def test_reservation_is_made_at_the_limit_before_matching():
    """A buyer who can afford the trade price but not its own limit is turned away."""
    ex = exchange_with((SELLER, 0, 5), (BUYER, 2010, 0))
    ex.submit_limit(SELLER, SELL, 1000, 3)
    assert ex.submit_limit(BUYER, BUY, 1010, 2) is None  # needs 2020, has 2010
    assert trades(ex) == []
    accepted = [e for e in ex.events if isinstance(e, OrderAccepted)]
    assert len(accepted) == 1
