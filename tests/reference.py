"""A deliberately naive second implementation of the exchange rules.

It shares no code with the engine and is built differently on purpose: orders sit in one
flat list that is re-sorted for every match, and reservations are never stored, only
recomputed from the open orders. If the engine and this model agree on thousands of random
order streams, a bug would have to be made the same way twice to go unnoticed.
"""

from __future__ import annotations


class ReferenceExchange:
    def __init__(self) -> None:
        self.cash: dict[int, int] = {}
        self.shares: dict[int, int] = {}
        self.orders: list[dict] = []  # open orders only
        self.trades: list[tuple[int, int, int, int]] = []  # (quantity, price, buyer, seller)
        self.time = 0
        self.accepted = 0  # an order's id is its position among accepted orders

    def open(self, trader: int, cash: int, shares: int) -> None:
        self.cash[trader] = cash
        self.shares[trader] = shares

    def committed_cash(self, trader: int) -> int:
        return sum(o["price"] * o["left"] for o in self.orders if o["trader"] == trader and o["side"] == "buy")

    def committed_shares(self, trader: int) -> int:
        return sum(o["left"] for o in self.orders if o["trader"] == trader and o["side"] == "sell")

    def submit(self, trader: int, side: str, price: int, quantity: int, expires_at: int | None):
        if side == "buy":
            if self.cash[trader] - self.committed_cash(trader) < price * quantity:
                return None
            own_crossing = [o for o in self.orders if o["trader"] == trader and o["side"] == "sell" and o["price"] <= price]
        else:
            if self.shares[trader] - self.committed_shares(trader) < quantity:
                return None
            own_crossing = [o for o in self.orders if o["trader"] == trader and o["side"] == "buy" and o["price"] >= price]
        if own_crossing:
            return None

        order_id = self.accepted
        self.accepted += 1
        left = quantity
        if side == "buy":
            candidates = sorted(
                (o for o in self.orders if o["side"] == "sell" and o["price"] <= price),
                key=lambda o: (o["price"], o["id"]),
            )
        else:
            candidates = sorted(
                (o for o in self.orders if o["side"] == "buy" and o["price"] >= price),
                key=lambda o: (-o["price"], o["id"]),
            )
        for resting in candidates:
            if left == 0:
                break
            fill = min(left, resting["left"])
            buyer, seller = (trader, resting["trader"]) if side == "buy" else (resting["trader"], trader)
            self.cash[buyer] -= resting["price"] * fill
            self.cash[seller] += resting["price"] * fill
            self.shares[buyer] += fill
            self.shares[seller] -= fill
            self.trades.append((fill, resting["price"], buyer, seller))
            resting["left"] -= fill
            left -= fill
        self.orders = [o for o in self.orders if o["left"] > 0]
        if left > 0:
            self.orders.append(
                {"id": order_id, "trader": trader, "side": side, "price": price, "left": left, "expires": expires_at}
            )
        return order_id

    def cancel(self, trader: int, order_id: int) -> bool:
        for order in self.orders:
            if order["id"] == order_id and order["trader"] == trader:
                self.orders.remove(order)
                return True
        return False

    def advance(self, time: int) -> None:
        self.time = time
        self.orders = [o for o in self.orders if o["expires"] is None or o["expires"] > time]

    def book(self, side: str) -> list[tuple[int, int, int, int]]:
        """(id, trader, price, left) in the order they would trade."""
        sign = -1 if side == "buy" else 1
        ranked = sorted((o for o in self.orders if o["side"] == side), key=lambda o: (sign * o["price"], o["id"]))
        return [(o["id"], o["trader"], o["price"], o["left"]) for o in ranked]
