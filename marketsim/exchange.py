"""The exchange: order entry, price-time matching, settlement, cancellation and expiry.

Rules (see docs/model_rules.md for the reasoning):

* Limit orders only. An incoming order trades against the best-priced resting orders on
  the other side while their prices are acceptable, oldest first at an equal price.
* Each fill happens at the resting order's price.
* A buy reserves `limit price x quantity` of cash; a sell reserves its shares. An order the
  account cannot fully fund is rejected whole.
* Any unfilled remainder rests on the book until it is filled, cancelled or expired.
* An order with `expires_at = T` can trade during steps before T and is removed at the
  start of step T, before anyone acts.
* An order priced to cross the same trader's own resting order is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from typing import Any

from .accounts import Account
from .book import Order, OrderBook
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


@dataclass(frozen=True, slots=True)
class Quotes:
    """The public top of the book: best prices and the shares resting at them."""

    best_bid: int | None
    bid_size: int
    best_ask: int | None
    ask_size: int

    @property
    def spread(self) -> int | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2


def _is_int(value: Any) -> bool:
    return type(value) is int  # excludes bool and floats


class Exchange:
    def __init__(self, check_invariants: bool = False) -> None:
        self.accounts: dict[int, Account] = {}
        self.book = OrderBook()
        self.time = 0
        self.events: list[Event] = []
        self.total_cash = 0  # fixed after the accounts are opened: the market is closed
        self.total_shares = 0
        self._seq = 0
        self._expiries: list[tuple[int, int]] = []  # heap of (expires_at, order_id)
        self._check = check_invariants

    # ------------------------------------------------------------------ helpers

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _emit(self, cls: type, **fields: Any) -> Event:
        event = cls(seq=self._next_seq(), time=self.time, **fields)
        self.events.append(event)
        return event

    def _done(self) -> None:
        if self._check:
            from .checks import assert_invariants

            assert_invariants(self)

    def _release(self, order: Order) -> None:
        """Give back the reservation held for an order's unfilled remainder."""
        account = self.accounts[order.trader_id]
        if order.side is Side.BUY:
            account.reserved_cash -= order.price * order.remaining
        else:
            account.reserved_shares -= order.remaining

    # ----------------------------------------------------------------- accounts

    def open_account(self, trader_id: int, cash: int, shares: int) -> None:
        if trader_id in self.accounts:
            raise ValueError(f"trader {trader_id} already has an account")
        if not (_is_int(cash) and _is_int(shares)) or cash < 0 or shares < 0:
            raise ValueError("cash and shares must be non-negative integers")
        self.accounts[trader_id] = Account(trader_id, cash, shares)
        self.total_cash += cash
        self.total_shares += shares
        self._emit(AccountOpened, trader_id=trader_id, cash=cash, shares=shares)
        self._done()

    # -------------------------------------------------------------------- clock

    def advance_to(self, time: int) -> None:
        """Move the clock forward and remove every order whose expiry time has come."""
        if not _is_int(time) or time < self.time:
            raise ValueError(f"time must be an integer >= {self.time}, got {time!r}")
        self.time = time
        while self._expiries and self._expiries[0][0] <= time:
            _, order_id = heappop(self._expiries)
            order = self.book.get(order_id)
            if order is None:  # already filled or cancelled
                continue
            self.book.remove(order_id)
            self._release(order)
            self._emit(
                OrderExpired,
                order_id=order_id,
                trader_id=order.trader_id,
                remaining=order.remaining,
            )
        self._done()

    # ------------------------------------------------------------------- orders

    def submit_limit(
        self,
        trader_id: int,
        side: Side,
        price: int,
        quantity: int,
        expires_at: int | None = None,
    ) -> int | None:
        """Enter a limit order. Returns its order id, or None if it was rejected."""
        reason = self._rejection_reason(trader_id, side, price, quantity, expires_at)
        if reason is not None:
            self._emit(
                OrderRejected,
                trader_id=trader_id,
                side=side if isinstance(side, Side) else repr(side),
                price=price,
                quantity=quantity,
                reason=reason,
            )
            self._done()
            return None

        account = self.accounts[trader_id]
        order_id = self._next_seq()
        order = Order(order_id, trader_id, side, price, quantity, quantity, self.time, expires_at)
        if side is Side.BUY:
            account.reserved_cash += price * quantity
        else:
            account.reserved_shares += quantity
        self.events.append(
            OrderAccepted(
                seq=order_id,
                time=self.time,
                order_id=order_id,
                trader_id=trader_id,
                side=side,
                price=price,
                quantity=quantity,
                expires_at=expires_at,
            )
        )

        self._match(order)

        if order.remaining > 0:
            self.book.add(order)
            if expires_at is not None:
                heappush(self._expiries, (expires_at, order_id))
        self._done()
        return order_id

    def _rejection_reason(
        self, trader_id: Any, side: Any, price: Any, quantity: Any, expires_at: Any
    ) -> str | None:
        account = self.accounts.get(trader_id)
        if account is None:
            return "unknown_trader"
        if not isinstance(side, Side):
            return "invalid_side"
        if not _is_int(price) or price < 1:
            return "invalid_price"
        if not _is_int(quantity) or quantity < 1:
            return "invalid_quantity"
        if expires_at is not None and (not _is_int(expires_at) or expires_at <= self.time):
            return "invalid_expiry"
        if side is Side.BUY and account.available_cash < price * quantity:
            return "insufficient_cash"
        if side is Side.SELL and account.available_shares < quantity:
            return "insufficient_shares"
        for own in self.book.orders_of(trader_id):
            if own.side is side:
                continue
            crosses = own.price <= price if side is Side.BUY else own.price >= price
            if crosses:
                return "would_self_trade"
        return None

    def _match(self, order: Order) -> None:
        """Fill the incoming order against the other side of the book while prices allow."""
        other = order.side.opposite
        while order.remaining > 0:
            resting = self.book.best(other)
            if resting is None:
                break
            if order.side is Side.BUY and resting.price > order.price:
                break
            if order.side is Side.SELL and resting.price < order.price:
                break

            quantity = min(order.remaining, resting.remaining)
            price = resting.price  # the resting order sets the price
            buy, sell = (order, resting) if order.side is Side.BUY else (resting, order)
            buyer, seller = self.accounts[buy.trader_id], self.accounts[sell.trader_id]

            # The buyer reserved at its own limit. Releasing limit x quantity while paying
            # price x quantity returns any difference to available cash.
            buyer.reserved_cash -= buy.price * quantity
            buyer.cash -= price * quantity
            buyer.shares += quantity
            seller.reserved_shares -= quantity
            seller.shares -= quantity
            seller.cash += price * quantity

            order.remaining -= quantity
            resting.remaining -= quantity
            self._emit(
                Trade,
                price=price,
                quantity=quantity,
                buy_order_id=buy.order_id,
                sell_order_id=sell.order_id,
                buyer_id=buy.trader_id,
                seller_id=sell.trader_id,
                aggressor=order.side,
            )
            if resting.remaining == 0:
                self.book.remove(resting.order_id)

    def cancel(self, trader_id: int, order_id: int) -> bool:
        """Cancel a resting order. Returns False (and logs why) if that is not possible."""
        order = self.book.get(order_id)
        reason = None
        if order is None:
            reason = "unknown_order"  # never existed, or already filled, cancelled or expired
        elif order.trader_id != trader_id:
            reason = "not_owner"
        if reason is not None:
            self._emit(CancelRejected, order_id=order_id, trader_id=trader_id, reason=reason)
            self._done()
            return False
        self.book.remove(order_id)
        self._release(order)
        self._emit(
            OrderCancelled, order_id=order_id, trader_id=trader_id, remaining=order.remaining
        )
        self._done()
        return True

    # ------------------------------------------------------------- public views

    def quotes(self) -> Quotes:
        return Quotes(
            best_bid=self.book.best_price(Side.BUY),
            bid_size=self.book.size_at_best(Side.BUY),
            best_ask=self.book.best_price(Side.SELL),
            ask_size=self.book.size_at_best(Side.SELL),
        )

    def open_orders(self, trader_id: int) -> list[Order]:
        return sorted(self.book.orders_of(trader_id), key=lambda o: o.order_id)
