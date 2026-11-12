"""Accounting and book invariants.

`assert_invariants` can run after every exchange operation (Exchange(check_invariants=True)).
It recomputes everything from scratch, so it does not trust the running totals it checks.
"""

from __future__ import annotations

from .events import Side
from .exchange import Exchange


class InvariantError(AssertionError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InvariantError(message)


def assert_invariants(exchange: Exchange) -> None:
    accounts = exchange.accounts

    # 1. Closed market: nothing is created or destroyed.
    _require(
        sum(a.cash for a in accounts.values()) == exchange.total_cash,
        "total cash changed",
    )
    _require(
        sum(a.shares for a in accounts.values()) == exchange.total_shares,
        "total shares changed",
    )

    # 2. Reservations equal exactly what the open orders commit.
    committed_cash = {trader_id: 0 for trader_id in accounts}
    committed_shares = {trader_id: 0 for trader_id in accounts}
    resting = 0
    for side in Side:
        previous = None
        for order in exchange.book.orders(side):
            resting += 1
            _require(1 <= order.remaining <= order.quantity, f"order {order.order_id} size")
            _require(
                order.expires_at is None or order.expires_at > exchange.time,
                f"order {order.order_id} is past its expiry",
            )
            if previous is not None:
                better = previous.price > order.price if side is Side.BUY else previous.price < order.price
                same_price_older = previous.price == order.price and previous.order_id < order.order_id
                _require(better or same_price_older, f"priority broken at order {order.order_id}")
            previous = order
            if side is Side.BUY:
                committed_cash[order.trader_id] += order.price * order.remaining
            else:
                committed_shares[order.trader_id] += order.remaining
    _require(resting == len(exchange.book), "book index out of step with price levels")

    # 3. Available + reserved = total, and neither part is negative.
    for trader_id, account in accounts.items():
        _require(account.reserved_cash == committed_cash[trader_id], f"trader {trader_id} cash reservation")
        _require(account.reserved_shares == committed_shares[trader_id], f"trader {trader_id} share reservation")
        _require(0 <= account.reserved_cash <= account.cash, f"trader {trader_id} cash overcommitted")
        _require(0 <= account.reserved_shares <= account.shares, f"trader {trader_id} shares overcommitted")

    # 4. A crossed book would mean a trade was missed.
    best_bid = exchange.book.best_price(Side.BUY)
    best_ask = exchange.book.best_price(Side.SELL)
    if best_bid is not None and best_ask is not None:
        _require(best_bid < best_ask, f"book is crossed: bid {best_bid} >= ask {best_ask}")
