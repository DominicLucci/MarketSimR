"""Randomized order streams.

Each stream is driven through the engine (with invariants checked after every operation)
and through the independent reference model. After every command the two must agree on
trades, balances, available resources and the full resting book.
"""

from __future__ import annotations

import random

import pytest

from marketsim.events import OrderAccepted, Side
from marketsim.exchange import Exchange
from marketsim.script import Advance, Cancel, Command, Open, Submit, run_script

from .helpers import trades
from .reference import ReferenceExchange

N_STREAMS = 300
COMMANDS_PER_STREAM = 200


def compare(engine: Exchange, model: ReferenceExchange, ids: dict[int, int], context: str) -> None:
    assert trades(engine) == model.trades, context
    for trader, account in engine.accounts.items():
        assert account.cash == model.cash[trader], context
        assert account.shares == model.shares[trader], context
        assert account.reserved_cash == model.committed_cash(trader), context
        assert account.reserved_shares == model.committed_shares(trader), context
    for side in Side:
        engine_side = [(ids[o.order_id], o.trader_id, o.price, o.remaining) for o in engine.book.orders(side)]
        assert engine_side == model.book(side.value), context


def random_stream(seed: int) -> list[Command]:
    """Drive both implementations with one random stream; return the commands used."""
    rng = random.Random(seed)
    engine, model = Exchange(check_invariants=True), ReferenceExchange()
    commands: list[Command] = []
    ids: dict[int, int] = {}  # engine order id -> reference order id
    owners: dict[int, int] = {}  # engine order id -> trader

    def do(command: Command) -> None:
        commands.append(command)

    traders = list(range(1, rng.randint(2, 6) + 1))
    for trader in traders:
        cash, shares = rng.choice([0, 3_000, 20_000]), rng.choice([0, 3, 12])
        engine.open_account(trader, cash, shares)
        model.open(trader, cash, shares)
        do(Open(trader, cash, shares))

    for step in range(COMMANDS_PER_STREAM):
        roll = rng.random()
        if roll < 0.70:
            trader, side = rng.choice(traders), rng.choice([Side.BUY, Side.SELL])
            price, quantity = rng.randint(995, 1005), rng.randint(1, 5)
            expires_at = None if rng.random() < 0.5 else engine.time + rng.randint(1, 4)
            got = engine.submit_limit(trader, side, price, quantity, expires_at)
            want = model.submit(trader, side.value, price, quantity, expires_at)
            assert (got is None) == (want is None), f"seed {seed} step {step}: accept/reject differs"
            if got is not None:
                ids[got], owners[got] = want, trader
            do(Submit(trader, side, price, quantity, expires_at))
        elif roll < 0.85 and ids:
            order_id = rng.choice(list(ids))
            trader = owners[order_id] if rng.random() < 0.8 else rng.choice(traders)
            got = engine.cancel(trader, order_id)
            want = model.cancel(trader, ids[order_id])
            assert got == want, f"seed {seed} step {step}: cancel differs"
            do(Cancel(trader, order_id))
        else:
            time = engine.time + rng.randint(0, 3)
            engine.advance_to(time)
            model.advance(time)
            do(Advance(time))
        compare(engine, model, ids, f"seed {seed} step {step}")

    random_stream.last = engine  # type: ignore[attr-defined]
    return commands


@pytest.mark.parametrize("block", range(10))
def test_engine_matches_reference_model(block):
    per_block = N_STREAMS // 10
    for seed in range(block * per_block, (block + 1) * per_block):
        random_stream(seed)


def test_random_streams_actually_exercise_the_rules():
    """Guard against a generator that quietly stops producing interesting cases."""
    counts: dict[str, int] = {}
    partial_fills = 0
    for seed in range(40):
        random_stream(seed)
        engine: Exchange = random_stream.last  # type: ignore[attr-defined]
        filled: dict[int, int] = {}
        for event in engine.events:
            name = type(event).__name__
            key = f"{name}:{event.reason}" if hasattr(event, "reason") else name
            counts[key] = counts.get(key, 0) + 1
            if name == "Trade":
                for order_id in (event.buy_order_id, event.sell_order_id):
                    filled[order_id] = filled.get(order_id, 0) + event.quantity
        sizes = {e.order_id: e.quantity for e in engine.events if isinstance(e, OrderAccepted)}
        partial_fills += sum(1 for order_id, got in filled.items() if got < sizes[order_id])
    for key in (
        "Trade",
        "OrderCancelled",
        "OrderExpired",
        "OrderRejected:insufficient_cash",
        "OrderRejected:insufficient_shares",
        "OrderRejected:would_self_trade",
        "CancelRejected:unknown_order",
        "CancelRejected:not_owner",
    ):
        assert counts.get(key, 0) >= 20, (key, counts)
    assert partial_fills >= 100


def test_replaying_the_commands_reproduces_the_log_exactly():
    for seed in (0, 1, 2, 3, 4):
        commands = random_stream(seed)
        original: Exchange = random_stream.last  # type: ignore[attr-defined]
        replayed = run_script(commands, check_invariants=True)
        assert replayed.events == original.events
        assert replayed.accounts == original.accounts
