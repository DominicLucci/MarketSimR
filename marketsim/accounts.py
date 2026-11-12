"""Trader accounts. Totals and reservations are integers (cash in ticks, stock in shares)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Account:
    trader_id: int
    cash: int  # total cash, including the reserved part
    shares: int  # total shares, including the reserved part
    reserved_cash: int = 0  # committed to open buy orders, at their limit prices
    reserved_shares: int = 0  # committed to open sell orders

    @property
    def available_cash(self) -> int:
        return self.cash - self.reserved_cash

    @property
    def available_shares(self) -> int:
        return self.shares - self.reserved_shares
