"""Event records.

The exchange appends one record for everything that happens. Analysis reads this log and
nothing else, so a saved log is enough to rebuild trades, quotes and balances.

Every record carries `seq`, a number from one global counter. `seq` is the total order of
the log, and an order's id is the `seq` of its acceptance, which makes it the time-priority
key as well.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


@dataclass(frozen=True, slots=True)
class AccountOpened:
    seq: int
    time: int
    trader_id: int
    cash: int
    shares: int


@dataclass(frozen=True, slots=True)
class OrderAccepted:
    seq: int
    time: int
    order_id: int
    trader_id: int
    side: Side
    price: int
    quantity: int
    expires_at: int | None


@dataclass(frozen=True, slots=True)
class OrderRejected:
    seq: int
    time: int
    trader_id: int
    side: Any
    price: Any
    quantity: Any
    reason: str


@dataclass(frozen=True, slots=True)
class Trade:
    seq: int
    time: int
    price: int
    quantity: int
    buy_order_id: int
    sell_order_id: int
    buyer_id: int
    seller_id: int
    aggressor: Side  # side of the incoming order


@dataclass(frozen=True, slots=True)
class OrderCancelled:
    seq: int
    time: int
    order_id: int
    trader_id: int
    remaining: int


@dataclass(frozen=True, slots=True)
class OrderExpired:
    seq: int
    time: int
    order_id: int
    trader_id: int
    remaining: int


@dataclass(frozen=True, slots=True)
class CancelRejected:
    seq: int
    time: int
    order_id: Any
    trader_id: int
    reason: str


Event = (
    AccountOpened
    | OrderAccepted
    | OrderRejected
    | Trade
    | OrderCancelled
    | OrderExpired
    | CancelRejected
)

_TYPES = {
    cls.__name__: cls
    for cls in (
        AccountOpened,
        OrderAccepted,
        OrderRejected,
        Trade,
        OrderCancelled,
        OrderExpired,
        CancelRejected,
    )
}
_SIDE_FIELDS = {"OrderAccepted": ("side",), "Trade": ("aggressor",)}


def to_record(event: Event) -> dict[str, Any]:
    """Event -> plain dict that json can write."""
    record = {"type": type(event).__name__, **asdict(event)}
    for key, value in record.items():
        if isinstance(value, Side):
            record[key] = value.value
    return record


def from_record(record: dict[str, Any]) -> Event:
    """Inverse of to_record."""
    data = dict(record)
    name = data.pop("type")
    for key in _SIDE_FIELDS.get(name, ()):
        data[key] = Side(data[key])
    return _TYPES[name](**data)


def write_jsonl(events: Iterable[Event], path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(to_record(event), sort_keys=True) + "\n")


def read_jsonl(path: str | Path) -> list[Event]:
    with open(path, encoding="utf-8") as handle:
        return [from_record(json.loads(line)) for line in handle if line.strip()]
