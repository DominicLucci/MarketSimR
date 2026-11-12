"""Order scripts: a list of commands that can be replayed through the exchange.

The same commands always produce the same event log, which is what makes a run replayable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .events import Event, Side
from .exchange import Exchange


@dataclass(frozen=True, slots=True)
class Open:
    trader_id: int
    cash: int
    shares: int


@dataclass(frozen=True, slots=True)
class Submit:
    trader_id: int
    side: Side
    price: int
    quantity: int
    expires_at: int | None = None


@dataclass(frozen=True, slots=True)
class Cancel:
    trader_id: int
    order_id: int


@dataclass(frozen=True, slots=True)
class Advance:
    time: int


Command = Open | Submit | Cancel | Advance
Observer = Callable[[Command, Exchange, list[Event]], None]


def apply(exchange: Exchange, command: Command) -> None:
    match command:
        case Open(trader_id, cash, shares):
            exchange.open_account(trader_id, cash, shares)
        case Submit(trader_id, side, price, quantity, expires_at):
            exchange.submit_limit(trader_id, side, price, quantity, expires_at)
        case Cancel(trader_id, order_id):
            exchange.cancel(trader_id, order_id)
        case Advance(time):
            exchange.advance_to(time)
        case _:
            raise TypeError(f"not a command: {command!r}")


def run_script(
    commands: Iterable[Command],
    check_invariants: bool = True,
    observer: Observer | None = None,
) -> Exchange:
    """Replay commands through a fresh exchange. `observer` sees each command's new events."""
    exchange = Exchange(check_invariants=check_invariants)
    for command in commands:
        before = len(exchange.events)
        apply(exchange, command)
        if observer is not None:
            observer(command, exchange, exchange.events[before:])
    return exchange
