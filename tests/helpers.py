"""Small helpers shared by the engine tests. Every exchange here checks its invariants
after each operation, so any test also exercises the accounting checks."""

from __future__ import annotations

from marketsim.events import OrderRejected, Side, Trade
from marketsim.exchange import Exchange

BUY, SELL = Side.BUY, Side.SELL


def exchange_with(*accounts: tuple[int, int, int]) -> Exchange:
    """Build an exchange from (trader_id, cash_in_ticks, shares) tuples."""
    exchange = Exchange(check_invariants=True)
    for trader_id, cash, shares in accounts:
        exchange.open_account(trader_id, cash, shares)
    return exchange


def trades(exchange: Exchange) -> list[tuple[int, int, int, int]]:
    """(quantity, price, buyer, seller) for every trade, in order."""
    return [
        (e.quantity, e.price, e.buyer_id, e.seller_id)
        for e in exchange.events
        if isinstance(e, Trade)
    ]


def last_rejection(exchange: Exchange) -> str | None:
    event = exchange.events[-1]
    return event.reason if isinstance(event, OrderRejected) else None


def resting(exchange: Exchange, side: Side) -> list[tuple[int, int, int]]:
    """(trader, price, remaining) for resting orders, in the order they would trade."""
    return [(o.trader_id, o.price, o.remaining) for o in exchange.book.orders(side)]
