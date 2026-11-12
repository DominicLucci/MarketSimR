"""The one simulation runner. The command line, the experiments and the dashboard all call
`run_simulation`, so they cannot disagree about what a run is.

Information boundary: the underlying value lives here and in the analysis. A trader only
ever receives a `TraderView`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .config import MODEL_VERSION, SimConfig
from .events import Event, Side
from .exchange import Exchange
from .traders import TraderView, decide
from .world import arrival_schedule, informed_traders, trader_luck, value_path


@dataclass(slots=True)
class RunResult:
    config: SimConfig
    model_version: str
    value_path: np.ndarray  # underlying value at each step, ticks
    arrivals: np.ndarray  # arriving trader at each step
    informed: frozenset[int]
    events: list[Event]
    decisions: list[dict[str, Any]]  # one row per arrival: inputs and resulting action
    quote_samples: list[tuple[int, int | None, int, int | None, int]]  # time, bid, size, ask, size
    final_accounts: dict[int, tuple[int, int]] = field(default_factory=dict)  # cash, shares
    # Mid-quote at the end of every step (after the arriving trader acts); NaN when a side is missing.
    mid_path: np.ndarray = field(default_factory=lambda: np.empty(0))


def run_simulation(
    config: SimConfig,
    value_override: np.ndarray | None = None,
    check_invariants: bool = False,
) -> RunResult:
    """Run one market.

    `value_override` replaces the generated value path. It exists for the information-access
    check, which changes future values and requires earlier orders to stay the same.
    """
    values = value_path(config) if value_override is None else np.asarray(value_override, dtype=float)
    if values.shape != (config.n_steps,) or not np.all(values > 0):
        raise ValueError("value path must be positive with one entry per step")
    arrivals = arrival_schedule(config)
    informed = informed_traders(config)
    luck = [trader_luck(config, i) for i in range(config.n_traders)]

    exchange = Exchange(check_invariants=check_invariants)
    for trader_id in range(config.n_traders):
        exchange.open_account(trader_id, config.initial_cash, config.initial_shares)

    decisions: list[dict[str, Any]] = []
    quote_samples: list[tuple[int, int | None, int, int | None, int]] = []
    mid_path = np.full(config.n_steps, np.nan)

    for time in range(config.n_steps):
        value = float(values[time])  # 1. the value updates first
        exchange.advance_to(time)  # 2. expired orders leave
        if config.cancel_on_news and time > 0 and values[time] != values[time - 1]:
            resting = list(exchange.book.orders(Side.BUY)) + list(exchange.book.orders(Side.SELL))
            for order in sorted(resting, key=lambda o: o.order_id):  # everyone pulls their quote
                exchange.cancel(order.trader_id, order.order_id)

        # 3. one trader arrives, replaces any order it still has resting, and acts
        trader_id = int(arrivals[time])
        for stale in exchange.open_orders(trader_id):
            exchange.cancel(trader_id, stale.order_id)

        z, need = luck[trader_id].draw(config.max_need)
        is_informed = trader_id in informed
        sigma = config.sigma_informed if is_informed else config.sigma_uninformed
        account = exchange.accounts[trader_id]
        view = TraderView(
            time=time,
            signal=value + sigma * z,
            target_shares=config.initial_shares + need,
            cash=account.cash,
            shares=account.shares,
            available_cash=account.available_cash,
            available_shares=account.available_shares,
            quotes=exchange.quotes(),
        )
        intent, reason = decide(view, config.margin, config.max_order_size)
        order_id = None
        if intent is not None:
            order_id = exchange.submit_limit(
                trader_id,
                intent.side,
                intent.price,
                intent.quantity,
                expires_at=time + config.order_lifetime,
            )
        decisions.append(
            {
                "time": time,
                "trader": trader_id,
                "informed": is_informed,
                "signal": view.signal,
                "shares": view.shares,
                "target": view.target_shares,
                "best_bid": view.quotes.best_bid,
                "best_ask": view.quotes.best_ask,
                "side": None if intent is None else intent.side.value,
                "price": None if intent is None else intent.price,
                "quantity": None if intent is None else intent.quantity,
                "reason": reason,
                "order_id": order_id,
            }
        )

        # 4. quotes are recorded: the mid every step, the full top of book on a fixed clock
        q = exchange.quotes()
        if q.mid is not None:
            mid_path[time] = q.mid
        if time % config.quote_sample_every == 0:
            quote_samples.append((time, q.best_bid, q.bid_size, q.best_ask, q.ask_size))

    return RunResult(
        config=config,
        model_version=MODEL_VERSION,
        value_path=values,
        arrivals=arrivals,
        informed=informed,
        events=exchange.events,
        decisions=decisions,
        quote_samples=quote_samples,
        final_accounts={i: (a.cash, a.shares) for i, a in exchange.accounts.items()},
        mid_path=mid_path,
    )
