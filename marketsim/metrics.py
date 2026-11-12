"""Per-run measures. All money amounts are in ticks. A measure that cannot be computed
(no trades, an empty group, no two-sided quotes) is reported as None, never as zero."""

from __future__ import annotations

from typing import Any

import numpy as np

from .events import OrderAccepted, OrderExpired, OrderRejected, Trade
from .news import HORIZONS, half_life, last_trade_path, response_curve
from .simulation import RunResult


def _mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def trader_outcomes(result: RunResult) -> list[dict[str, Any]]:
    """Wealth change per trader, with stock marked at the underlying value.

    trading_gain compares the trader with a copy of itself that never traded, both marked
    at the final value. It removes the part of the wealth change that comes from the asset
    simply being worth more or less. Trading gains sum to zero across traders.
    """
    config = result.config
    v_start, v_end = float(result.value_path[0]), float(result.value_path[-1])
    start_wealth = config.initial_cash + config.initial_shares * v_start
    hold_wealth = config.initial_cash + config.initial_shares * v_end
    rows = []
    for trader_id, (cash, shares) in sorted(result.final_accounts.items()):
        end_wealth = cash + shares * v_end
        rows.append(
            {
                "trader": trader_id,
                "informed": trader_id in result.informed,
                "final_cash": cash,
                "final_shares": shares,
                "wealth_change": end_wealth - start_wealth,
                "trading_gain": end_wealth - hold_wealth,
            }
        )
    return rows


def summarize(result: RunResult) -> dict[str, Any]:
    config = result.config
    trades = [e for e in result.events if isinstance(e, Trade)]
    errors = [abs(t.price - float(result.value_path[t.time])) for t in trades]

    samples = result.quote_samples
    two_sided = [(bid, bid_size, ask, ask_size) for _, bid, bid_size, ask, ask_size in samples if bid is not None and ask is not None]
    no_bid = sum(1 for s in samples if s[1] is None)
    no_ask = sum(1 for s in samples if s[3] is None)

    # Mid-quote error on every step: unlike the trade-based error it does not depend on
    # which trades happen to occur.
    mid = result.mid_path
    quoted = ~np.isnan(mid)
    mid_errors = np.abs(mid[quoted] - result.value_path[quoted])

    # Trade error by who was on the two sides: both better informed, one of each, neither.
    by_pair: dict[str, list[float]] = {"both": [], "mixed": [], "neither": []}
    for trade, error in zip(trades, errors):
        informed_sides = (trade.buyer_id in result.informed) + (trade.seller_id in result.informed)
        by_pair[("neither", "mixed", "both")[informed_sides]].append(error)

    # News event study: share of each value change reflected k steps later.
    in_mid = response_curve(result.value_path, mid)
    in_trades = response_curve(result.value_path, last_trade_path(result.events, config.n_steps))

    def at(curve: dict[str, Any], horizon: int) -> float | None:
        value = curve["reflected"][horizon]
        return None if np.isnan(value) else float(value)

    outcomes = trader_outcomes(result)
    by_group = {
        True: [o for o in outcomes if o["informed"]],
        False: [o for o in outcomes if not o["informed"]],
    }

    return {
        "model_version": result.model_version,
        "seed": config.seed,
        "informed_share": config.informed_share,
        "n_informed": len(by_group[True]),
        "n_uninformed": len(by_group[False]),
        # activity
        "n_orders": sum(1 for e in result.events if isinstance(e, OrderAccepted)),
        "n_rejected": sum(1 for e in result.events if isinstance(e, OrderRejected)),
        "n_expired": sum(1 for e in result.events if isinstance(e, OrderExpired)),
        "n_no_order": sum(1 for d in result.decisions if d["side"] is None),
        "n_trades": len(trades),
        "volume": sum(t.quantity for t in trades),
        # price accuracy: mean absolute gap between trade price and value at that trade
        "price_error": _mean(errors),
        "price_error_both_informed": _mean(by_pair["both"]),
        "price_error_mixed": _mean(by_pair["mixed"]),
        "price_error_neither_informed": _mean(by_pair["neither"]),
        "n_trades_both_informed": len(by_pair["both"]),
        "n_trades_mixed": len(by_pair["mixed"]),
        "n_trades_neither_informed": len(by_pair["neither"]),
        # mean absolute gap between the mid-quote and value, over every step with two-sided quotes
        "mid_error": float(mid_errors.mean()) if len(mid_errors) else None,
        "share_steps_quoted": float(quoted.mean()),
        # news: share of a value change reflected k steps later (ratio of sums over isolated events)
        "news_events": in_mid["n_events"],
        **{f"news_in_mid_{h}": at(in_mid, h) for h in HORIZONS},
        **{f"news_in_trades_{h}": at(in_trades, h) for h in HORIZONS},
        "news_half_life_mid": half_life(in_mid["reflected"]) if in_mid["n_events"] else None,
        # liquidity, from quotes sampled every quote_sample_every steps
        "n_quote_samples": len(samples),
        "share_no_bid": no_bid / len(samples),
        "share_no_ask": no_ask / len(samples),
        "share_two_sided": len(two_sided) / len(samples),
        "spread": _mean([ask - bid for bid, _, ask, _ in two_sided]),
        "bid_size": _mean([s[2] for s in samples if s[1] is not None]),
        "ask_size": _mean([s[4] for s in samples if s[3] is not None]),
        # trader outcomes: mean per trader in each group; None if the group is empty
        "wealth_change_informed": _mean([o["wealth_change"] for o in by_group[True]]),
        "wealth_change_uninformed": _mean([o["wealth_change"] for o in by_group[False]]),
        "trading_gain_informed": _mean([o["trading_gain"] for o in by_group[True]]),
        "trading_gain_uninformed": _mean([o["trading_gain"] for o in by_group[False]]),
        "value_start": float(result.value_path[0]),
        "value_end": float(result.value_path[-1]),
    }
