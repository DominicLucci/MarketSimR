"""Limit order book with price-time priority.

The book only stores and ranks resting orders. It moves no money: settlement and
reservations live in the exchange.
"""

from __future__ import annotations

from bisect import insort
from collections import deque
from dataclasses import dataclass
from typing import Iterator

from .events import Side


@dataclass(slots=True)
class Order:
    order_id: int  # seq of the acceptance event; lower id = arrived earlier
    trader_id: int
    side: Side
    price: int  # limit price in ticks
    quantity: int  # original size
    remaining: int  # unfilled size
    submitted_at: int
    expires_at: int | None  # first step at which the order is no longer live


class OrderBook:
    def __init__(self) -> None:
        self._levels: dict[Side, dict[int, deque[Order]]] = {Side.BUY: {}, Side.SELL: {}}
        self._prices: dict[Side, list[int]] = {Side.BUY: [], Side.SELL: []}  # ascending
        self._orders: dict[int, Order] = {}

    def __len__(self) -> int:
        return len(self._orders)

    def __contains__(self, order_id: object) -> bool:
        return order_id in self._orders

    def get(self, order_id: int) -> Order | None:
        return self._orders.get(order_id)

    def add(self, order: Order) -> None:
        levels = self._levels[order.side]
        if order.price not in levels:
            levels[order.price] = deque()
            insort(self._prices[order.side], order.price)
        levels[order.price].append(order)  # back of the queue at its price
        self._orders[order.order_id] = order

    def remove(self, order_id: int) -> Order:
        order = self._orders.pop(order_id)
        queue = self._levels[order.side][order.price]
        if queue[0] is order:
            queue.popleft()
        else:
            queue.remove(order)
        if not queue:
            del self._levels[order.side][order.price]
            self._prices[order.side].remove(order.price)
        return order

    def best_price(self, side: Side) -> int | None:
        prices = self._prices[side]
        if not prices:
            return None
        return prices[-1] if side is Side.BUY else prices[0]

    def best(self, side: Side) -> Order | None:
        """The resting order that trades first on this side."""
        price = self.best_price(side)
        return None if price is None else self._levels[side][price][0]

    def size_at_best(self, side: Side) -> int:
        price = self.best_price(side)
        if price is None:
            return 0
        return sum(order.remaining for order in self._levels[side][price])

    def orders(self, side: Side) -> Iterator[Order]:
        """Resting orders on one side, in the order they would trade."""
        prices = self._prices[side]
        for price in reversed(prices) if side is Side.BUY else prices:
            yield from self._levels[side][price]

    def orders_of(self, trader_id: int) -> list[Order]:
        return [o for o in self._orders.values() if o.trader_id == trader_id]
