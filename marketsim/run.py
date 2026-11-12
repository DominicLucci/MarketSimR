"""Run one market from the command line.

    python -m marketsim.run --seed 1 --informed-share 0.25
    python -m marketsim.run --seed 1 --informed-share 0.25 --trace-step 200
    python -m marketsim.run --seed 1 --informed-share 0.25 --save results/run1
"""

from __future__ import annotations

import argparse

from .config import SimConfig
from .events import Trade
from .metrics import summarize
from .render import describe
from .simulation import RunResult, run_simulation
from .storage import save_run
from .units import dollars


DEFAULTS = SimConfig()


def _money(ticks: float | None) -> str:
    return "unavailable" if ticks is None else dollars(ticks)


def summary_text(result: RunResult) -> str:
    s = summarize(result)
    lines = [
        f"model {s['model_version']}   seed {s['seed']}   informed share {s['informed_share']:.0%} "
        f"({s['n_informed']} of {s['n_informed'] + s['n_uninformed']} traders)",
        f"underlying value      {dollars(s['value_start'])} -> {dollars(s['value_end'])}",
        f"orders / trades       {s['n_orders']} accepted, {s['n_rejected']} rejected, "
        f"{s['n_expired']} expired, {s['n_trades']} trades, {s['volume']} shares",
        f"price accuracy        mean |trade price - value| = {_money(s['price_error'])}",
        f"quoted spread         {_money(s['spread'])} on average when both sides are quoted "
        f"({s['share_two_sided']:.0%} of {s['n_quote_samples']} samples; "
        f"no bid {s['share_no_bid']:.0%}, no offer {s['share_no_ask']:.0%})",
        f"shares at best quotes bid {s['bid_size'] if s['bid_size'] is None else round(s['bid_size'], 2)}, "
        f"offer {s['ask_size'] if s['ask_size'] is None else round(s['ask_size'], 2)}",
        f"trading gain/trader   better informed {_money(s['trading_gain_informed'])}, "
        f"others {_money(s['trading_gain_uninformed'])}",
        f"wealth change/trader  better informed {_money(s['wealth_change_informed'])}, "
        f"others {_money(s['wealth_change_uninformed'])}",
    ]
    return "\n".join(lines)


def trace_text(result: RunResult, step: int) -> str:
    """Follow one arrival from what the trader saw to what happened to its order."""
    d = result.decisions[step]
    config = result.config
    value = float(result.value_path[step])
    sigma = config.sigma_informed if d["informed"] else config.sigma_uninformed
    lines = [
        f"step {step}: trader {d['trader']} arrives "
        f"({'better informed' if d['informed'] else 'less informed'}, signal error sd {dollars(sigma)})",
        f"  hidden from the trader: underlying value {dollars(value)}",
        f"  sees: signal {dollars(d['signal'])} (error {dollars(d['signal'] - value)}), "
        f"holds {d['shares']} shares, target {d['target']}, "
        f"best bid {_money(d['best_bid'])}, best offer {_money(d['best_ask'])}",
    ]
    if d["estimate"] != d["signal"]:
        lines.append(f"  blends its signal with the mid-quote: estimate {dollars(d['estimate'])}")
    if d["side"] is None:
        lines.append(f"  decides: no order ({d['reason']})")
        return "\n".join(lines)
    gap = d["target"] - d["shares"]
    direction = "minus" if d["side"] == "buy" else "plus"
    rounding = "down" if d["side"] == "buy" else "up"
    lines.append(
        f"  decides: {d['reason']} by {abs(gap)}, so {d['side']} {d['quantity']} at estimate {direction} "
        f"margin {dollars(config.margin)}, rounded {rounding} = {dollars(d['price'])}"
    )
    if d["order_id"] is None:
        lines.append("  result: order rejected")
        return "\n".join(lines)
    lines.append("  result:")
    mine = [
        e
        for e in result.events
        if getattr(e, "order_id", None) == d["order_id"]
        or (isinstance(e, Trade) and d["order_id"] in (e.buy_order_id, e.sell_order_id))
    ]
    lines += ["    " + describe(e) for e in mine]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> RunResult:
    parser = argparse.ArgumentParser(description="Run one simulated market.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--informed-share", type=float, default=DEFAULTS.informed_share)
    parser.add_argument("--steps", type=int, default=DEFAULTS.n_steps)
    parser.add_argument("--trace-step", type=int, help="explain the decision made at this step")
    parser.add_argument("--save", help="directory to write the run to")
    args = parser.parse_args(argv)

    config = SimConfig(seed=args.seed, informed_share=args.informed_share, n_steps=args.steps)
    result = run_simulation(config)
    print(summary_text(result))
    if args.trace_step is not None:
        print()
        print(trace_text(result, args.trace_step))
    if args.save:
        print(f"\nsaved to {save_run(result, args.save)}")
    return result


if __name__ == "__main__":
    main()
