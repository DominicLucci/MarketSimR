"""Cancellation, expiry and the clock."""

import pytest

from marketsim.events import CancelRejected, OrderExpired

from .helpers import BUY, SELL, exchange_with, resting, trades

A, B, C = 1, 2, 3


def test_order_can_trade_on_the_step_before_it_expires():
    ex = exchange_with((A, 0, 1), (B, 5000, 0))
    ex.submit_limit(A, SELL, 1000, 1, expires_at=5)
    ex.advance_to(4)
    ex.submit_limit(B, BUY, 1000, 1)
    assert trades(ex) == [(1, 1000, B, A)]


def test_order_is_gone_at_its_expiry_step_before_anyone_acts():
    ex = exchange_with((A, 0, 1), (B, 5000, 0))
    ask = ex.submit_limit(A, SELL, 1000, 1, expires_at=5)
    ex.advance_to(5)
    expired = ex.events[-1]
    assert isinstance(expired, OrderExpired)
    assert (expired.order_id, expired.remaining, expired.time) == (ask, 1, 5)
    assert ex.accounts[A].reserved_shares == 0
    ex.submit_limit(B, BUY, 1000, 1)
    assert trades(ex) == []
    assert resting(ex, BUY) == [(B, 1000, 1)]


def test_expiry_releases_only_the_unfilled_part():
    ex = exchange_with((A, 5000, 0), (B, 0, 5))
    ex.submit_limit(A, BUY, 1000, 3, expires_at=2)
    ex.submit_limit(B, SELL, 1000, 1)
    assert ex.accounts[A].reserved_cash == 2000
    ex.advance_to(2)
    account = ex.accounts[A]
    assert (account.cash, account.reserved_cash, account.shares) == (4000, 0, 1)
    assert ex.events[-1].remaining == 2


def test_orders_expiring_together_leave_in_arrival_order():
    ex = exchange_with((A, 0, 5), (B, 0, 5))
    first = ex.submit_limit(A, SELL, 1005, 1, expires_at=3)
    second = ex.submit_limit(B, SELL, 1000, 1, expires_at=3)
    later = ex.submit_limit(A, SELL, 1001, 1, expires_at=4)
    ex.advance_to(3)
    expired = [e.order_id for e in ex.events if isinstance(e, OrderExpired)]
    assert expired == [first, second]
    assert later in ex.book


def test_cancel_releases_the_reservation():
    ex = exchange_with((A, 5000, 0))
    bid = ex.submit_limit(A, BUY, 1000, 3)
    assert ex.accounts[A].available_cash == 2000
    assert ex.cancel(A, bid) is True
    assert ex.accounts[A].available_cash == 5000
    assert len(ex.book) == 0


def test_cancel_is_refused_for_dead_orders_and_other_traders():
    ex = exchange_with((A, 0, 5), (B, 5000, 0))
    ask = ex.submit_limit(A, SELL, 1000, 1)

    assert ex.cancel(B, ask) is False
    assert isinstance(ex.events[-1], CancelRejected) and ex.events[-1].reason == "not_owner"
    assert ask in ex.book

    ex.submit_limit(B, BUY, 1000, 1)  # fills the ask completely
    assert ex.cancel(A, ask) is False
    assert ex.events[-1].reason == "unknown_order"
    assert ex.cancel(A, 12345) is False


def test_cancelled_order_does_not_expire_later():
    ex = exchange_with((A, 0, 5))
    ask = ex.submit_limit(A, SELL, 1000, 1, expires_at=3)
    ex.cancel(A, ask)
    ex.advance_to(10)
    assert not any(isinstance(e, OrderExpired) for e in ex.events)


def test_clock_only_moves_forward():
    ex = exchange_with((A, 0, 5))
    ex.advance_to(3)
    ex.advance_to(3)  # staying put is allowed
    with pytest.raises(ValueError):
        ex.advance_to(2)
    with pytest.raises(ValueError):
        ex.advance_to(3.5)
    assert ex.time == 3
