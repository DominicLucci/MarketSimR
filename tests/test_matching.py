"""Hand-worked matching cases: price priority, time priority, partial fills."""

from .helpers import BUY, SELL, exchange_with, resting, trades

A, B, C, TAKER = 1, 2, 3, 9
RICH = 1_000_000


def test_lower_ask_trades_first_even_if_it_arrived_later():
    ex = exchange_with((A, 0, 5), (B, 0, 5), (TAKER, RICH, 0))
    ex.submit_limit(A, SELL, 1002, 1)
    ex.submit_limit(B, SELL, 1000, 1)
    ex.submit_limit(TAKER, BUY, 1005, 2)
    assert trades(ex) == [(1, 1000, TAKER, B), (1, 1002, TAKER, A)]


def test_higher_bid_trades_first_even_if_it_arrived_later():
    ex = exchange_with((A, RICH, 0), (B, RICH, 0), (TAKER, 0, 5))
    ex.submit_limit(A, BUY, 998, 1)
    ex.submit_limit(B, BUY, 1000, 1)
    ex.submit_limit(TAKER, SELL, 990, 2)
    assert trades(ex) == [(1, 1000, B, TAKER), (1, 998, A, TAKER)]


def test_oldest_order_wins_at_the_same_price():
    ex = exchange_with((A, 0, 5), (B, 0, 5), (C, 0, 5), (TAKER, RICH, 0))
    for seller in (A, B, C):
        ex.submit_limit(seller, SELL, 1000, 1)
    ex.submit_limit(TAKER, BUY, 1000, 2)
    assert trades(ex) == [(1, 1000, TAKER, A), (1, 1000, TAKER, B)]
    assert resting(ex, SELL) == [(C, 1000, 1)]


def test_same_price_queue_on_the_bid_side():
    ex = exchange_with((A, RICH, 0), (B, RICH, 0), (TAKER, 0, 5))
    ex.submit_limit(A, BUY, 1000, 2)
    ex.submit_limit(B, BUY, 1000, 2)
    ex.submit_limit(TAKER, SELL, 1000, 3)
    assert trades(ex) == [(2, 1000, A, TAKER), (1, 1000, B, TAKER)]
    assert resting(ex, BUY) == [(B, 1000, 1)]


def test_partly_filled_order_keeps_its_place_in_the_queue():
    ex = exchange_with((A, 0, 5), (B, 0, 5), (TAKER, RICH, 0))
    ex.submit_limit(A, SELL, 1000, 3)
    ex.submit_limit(B, SELL, 1000, 3)
    ex.submit_limit(TAKER, BUY, 1000, 2)
    assert resting(ex, SELL) == [(A, 1000, 1), (B, 1000, 3)]
    ex.submit_limit(TAKER, BUY, 1000, 2)
    assert trades(ex) == [(2, 1000, TAKER, A), (1, 1000, TAKER, A), (1, 1000, TAKER, B)]
    assert resting(ex, SELL) == [(B, 1000, 2)]


def test_orders_that_do_not_cross_both_rest():
    ex = exchange_with((A, 0, 5), (B, RICH, 0))
    ex.submit_limit(A, SELL, 1001, 2)
    ex.submit_limit(B, BUY, 1000, 3)
    assert trades(ex) == []
    quotes = ex.quotes()
    assert (quotes.best_bid, quotes.bid_size, quotes.best_ask, quotes.ask_size) == (1000, 3, 1001, 2)
    assert quotes.spread == 1 and quotes.mid == 1000.5


def test_unfilled_remainder_of_incoming_order_rests_with_its_reservation():
    ex = exchange_with((A, 0, 5), (B, RICH, 0))
    ex.submit_limit(A, SELL, 1000, 2)
    ex.submit_limit(B, BUY, 1000, 5)
    assert trades(ex) == [(2, 1000, B, A)]
    assert resting(ex, BUY) == [(B, 1000, 3)]
    assert ex.accounts[B].reserved_cash == 3000


def test_sweep_stops_at_the_limit_price():
    ex = exchange_with((A, 0, 5), (TAKER, RICH, 0))
    for price in (1000, 1001, 1003):
        ex.submit_limit(A, SELL, price, 1)
    ex.submit_limit(TAKER, BUY, 1001, 3)
    assert trades(ex) == [(1, 1000, TAKER, A), (1, 1001, TAKER, A)]
    assert resting(ex, SELL) == [(A, 1003, 1)]
    assert resting(ex, BUY) == [(TAKER, 1001, 1)]
    # Paid 2001 for two shares, 1001 still reserved for the resting share.
    taker = ex.accounts[TAKER]
    assert (taker.cash, taker.reserved_cash, taker.shares) == (RICH - 2001, 1001, 2)


def test_incoming_sell_trades_at_the_resting_bid_price():
    ex = exchange_with((A, RICH, 0), (TAKER, 0, 5))
    ex.submit_limit(A, BUY, 1010, 2)
    ex.submit_limit(TAKER, SELL, 1000, 2)
    assert trades(ex) == [(2, 1010, A, TAKER)]
    assert ex.accounts[TAKER].cash == 2020
    assert ex.accounts[A].reserved_cash == 0


def test_empty_book_has_no_quotes():
    quotes = exchange_with((A, 0, 1)).quotes()
    assert (quotes.best_bid, quotes.best_ask, quotes.spread, quotes.mid) == (None, None, None, None)
    assert (quotes.bid_size, quotes.ask_size) == (0, 0)
