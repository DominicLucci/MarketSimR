"""Reservations and order validation."""

import pytest

from marketsim.exchange import Exchange

from .helpers import BUY, SELL, exchange_with, last_rejection, resting, trades

A, B = 1, 2


def test_cash_committed_to_one_bid_cannot_fund_another():
    ex = exchange_with((A, 2000, 0))
    first = ex.submit_limit(A, BUY, 1500, 1)
    assert ex.accounts[A].available_cash == 500
    assert ex.submit_limit(A, BUY, 600, 1) is None
    assert last_rejection(ex) == "insufficient_cash"
    ex.cancel(A, first)
    assert ex.submit_limit(A, BUY, 600, 1) is not None


def test_shares_committed_to_one_offer_cannot_back_another():
    ex = exchange_with((A, 0, 3))
    ex.submit_limit(A, SELL, 1000, 2)
    assert ex.submit_limit(A, SELL, 1001, 2) is None
    assert last_rejection(ex) == "insufficient_shares"
    assert ex.submit_limit(A, SELL, 1001, 1) is not None
    assert ex.accounts[A].available_shares == 0


def test_unfundable_order_is_rejected_whole_not_trimmed():
    ex = exchange_with((A, 2500, 0), (B, 0, 5))
    ex.submit_limit(B, SELL, 1000, 5)
    assert ex.submit_limit(A, BUY, 1000, 3) is None  # could afford two, asked for three
    assert trades(ex) == []
    assert ex.accounts[A].reserved_cash == 0


@pytest.mark.parametrize(
    "price, quantity, expires_at, reason",
    [
        (0, 1, None, "invalid_price"),
        (-5, 1, None, "invalid_price"),
        (10.5, 1, None, "invalid_price"),
        (True, 1, None, "invalid_price"),
        (1000, 0, None, "invalid_quantity"),
        (1000, 1.0, None, "invalid_quantity"),
        (1000, 1, 0, "invalid_expiry"),  # the clock is at 0, so 0 is already past
        (1000, 1, 2.5, "invalid_expiry"),
    ],
)
def test_malformed_orders_are_rejected(price, quantity, expires_at, reason):
    ex = exchange_with((A, 10_000, 10))
    assert ex.submit_limit(A, BUY, price, quantity, expires_at) is None
    assert last_rejection(ex) == reason
    assert len(ex.book) == 0


def test_unknown_trader_and_bad_side_are_rejected():
    ex = exchange_with((A, 10_000, 10))
    assert ex.submit_limit(99, BUY, 1000, 1) is None
    assert last_rejection(ex) == "unknown_trader"
    assert ex.submit_limit(A, "buy", 1000, 1) is None
    assert last_rejection(ex) == "invalid_side"


def test_order_that_would_cross_own_resting_order_is_rejected():
    ex = exchange_with((A, 10_000, 5))
    ex.submit_limit(A, SELL, 1000, 1)
    assert ex.submit_limit(A, BUY, 1000, 1) is None
    assert last_rejection(ex) == "would_self_trade"
    assert ex.submit_limit(A, BUY, 999, 1) is not None  # does not cross, so it rests
    assert ex.submit_limit(A, SELL, 999, 1) is None  # would hit own bid
    assert last_rejection(ex) == "would_self_trade"
    assert trades(ex) == []


def test_proceeds_of_a_fill_are_available_at_once():
    ex = exchange_with((A, 0, 2), (B, 2000, 0))
    ex.submit_limit(A, SELL, 1000, 2)
    ex.submit_limit(B, BUY, 1000, 2)
    # B can sell the shares it just bought; A can spend the cash it just received.
    assert ex.submit_limit(B, SELL, 1100, 2) is not None
    assert ex.submit_limit(A, BUY, 900, 2) is not None
    assert resting(ex, SELL) == [(B, 1100, 2)]
    assert resting(ex, BUY) == [(A, 900, 2)]


def test_price_improvement_is_spendable_immediately():
    ex = exchange_with((A, 0, 2), (B, 2020, 0))
    ex.submit_limit(A, SELL, 1000, 2)
    ex.submit_limit(B, BUY, 1010, 2)  # reserves all 2020, pays 2000
    assert ex.accounts[B].available_cash == 20
    assert ex.submit_limit(B, BUY, 20, 1) is not None


def test_accounts_must_be_unique_and_non_negative():
    ex = Exchange(check_invariants=True)
    ex.open_account(A, 100, 1)
    with pytest.raises(ValueError):
        ex.open_account(A, 100, 1)
    with pytest.raises(ValueError):
        ex.open_account(B, -1, 0)
    with pytest.raises(ValueError):
        ex.open_account(B, 1.5, 0)
