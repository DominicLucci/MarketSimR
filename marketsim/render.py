"""Plain-text views of events, the book and the accounts."""

from __future__ import annotations

from .events import (
    AccountOpened,
    CancelRejected,
    Event,
    OrderAccepted,
    OrderCancelled,
    OrderExpired,
    OrderRejected,
    Side,
    Trade,
)
from .exchange import Exchange
from .units import dollars


def describe(event: Event) -> str:
    head = f"#{event.seq:<3} t={event.time:<3} "
    match event:
        case AccountOpened():
            body = f"account   trader {event.trader_id} opens with {dollars(event.cash)} and {event.shares} shares"
        case OrderAccepted():
            expiry = "" if event.expires_at is None else f", expires at t={event.expires_at}"
            body = (
                f"order     #{event.order_id} trader {event.trader_id} {event.side.value} "
                f"{event.quantity} @ {dollars(event.price)}{expiry}"
            )
        case OrderRejected():
            body = f"rejected  trader {event.trader_id} order ({event.reason})"
        case Trade():
            body = (
                f"trade     {event.quantity} @ {dollars(event.price)}  "
                f"buyer {event.buyer_id} (order #{event.buy_order_id}), "
                f"seller {event.seller_id} (order #{event.sell_order_id})"
            )
        case OrderCancelled():
            body = f"cancelled #{event.order_id} trader {event.trader_id}, {event.remaining} unfilled"
        case OrderExpired():
            body = f"expired   #{event.order_id} trader {event.trader_id}, {event.remaining} unfilled"
        case CancelRejected():
            body = f"cancel of #{event.order_id} by trader {event.trader_id} refused ({event.reason})"
        case _:
            body = repr(event)
    return head + body


def book_text(exchange: Exchange) -> str:
    lines = ["  side  price      size  order  trader"]
    asks = list(exchange.book.orders(Side.SELL))
    bids = list(exchange.book.orders(Side.BUY))
    for order in reversed(asks):  # highest ask on top, best ask just above the bids
        lines.append(
            f"  ask   {dollars(order.price):>8} {order.remaining:>5}  #{order.order_id:<4}  {order.trader_id}"
        )
    for order in bids:
        lines.append(
            f"  bid   {dollars(order.price):>8} {order.remaining:>5}  #{order.order_id:<4}  {order.trader_id}"
        )
    if not asks and not bids:
        lines.append("  (empty)")
    return "\n".join(lines)


def accounts_text(exchange: Exchange) -> str:
    lines = ["  trader  total cash  reserved  total shares  reserved"]
    for trader_id in sorted(exchange.accounts):
        a = exchange.accounts[trader_id]
        lines.append(
            f"  {trader_id:<6}  {dollars(a.cash):>10}  {dollars(a.reserved_cash):>8}  "
            f"{a.shares:>12}  {a.reserved_shares:>8}"
        )
    return "\n".join(lines)
