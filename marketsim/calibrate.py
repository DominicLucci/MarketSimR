"""Calibrated trust: the self-consistent version of learning from prices.

With learn_from_prices on, every trader believes the mid-quote is typically `price_sd` ticks
away from the value. Calibration chooses `price_sd`, separately at each informed share, so
that this belief is correct: the root-mean-square gap between mid-quote and value that the
market produces when everyone trusts prices at `price_sd` equals `price_sd` itself.

    python -m marketsim.calibrate                          # random news
    python -m marketsim.calibrate --design scheduled_news
    python -m marketsim.calibrate --check                  # the stored values still hold

Why bisection and not repeated substitution: the produced error f(s) falls steeply as trust
s falls, with a slope near -1 around the fixed point at low informed shares, so
s <- f(s) oscillates. g(s) = f(s) - s is positive at small s (prices trusted too much drift
away from value) and negative at large s, and crosses zero once in the scanned range, so
bisection on g finds the fixed point without tuning.

Calibration uses its own seeds (CALIBRATION_SEEDS), disjoint from the experiment's seeds
0..29, so the trust is fixed before the experiment runs and is not fitted to the runs it
is then judged on. The calibrated values are stored in experiment.py; `--check` reruns the
search and confirms they still match.
"""

from __future__ import annotations

import argparse
from typing import Callable, Iterable

import numpy as np

from .config import SimConfig
from .simulation import RunResult, run_simulation

CALIBRATION_SEEDS = tuple(range(1000, 1020))
LOW, HIGH = 10.0, 200.0  # bracket in ticks; f(LOW) > LOW and f(HIGH) < HIGH at every share scanned
TOLERANCE = 0.1  # ticks; the stored value is rounded to this


def mid_rmse(result: RunResult) -> tuple[float, int]:
    """Sum of squared mid-quote errors and number of quoted steps (so seeds can be pooled)."""
    mid = result.mid_path
    quoted = ~np.isnan(mid)
    gaps = mid[quoted] - result.value_path[quoted]
    return float(np.sum(gaps**2)), int(quoted.sum())


def produced_error(config: SimConfig, price_sd: float, seeds: Iterable[int]) -> float:
    """RMS mid-quote error, pooled over seeds, when every trader trusts prices at price_sd."""
    total, count = 0.0, 0
    for seed in seeds:
        squares, n = mid_rmse(run_simulation(config.with_(seed=seed, learn_from_prices=True, price_sd=price_sd)))
        total, count = total + squares, count + n
    if count == 0:
        raise ValueError("no step had a two-sided quote; trust cannot be calibrated")
    return float(np.sqrt(total / count))


def bisect_fixed_point(
    f: Callable[[float], float], low: float = LOW, high: float = HIGH, tolerance: float = TOLERANCE
) -> tuple[float, list[tuple[float, float]]]:
    """Find s with f(s) = s on [low, high], where f(low) > low and f(high) < high.

    Returns the midpoint of the final bracket and every (s, f(s)) evaluated, in order.
    """
    trace = []
    f_low, f_high = f(low), f(high)
    trace += [(low, f_low), (high, f_high)]
    if not (f_low > low and f_high < high):
        raise ValueError(f"no crossing bracketed: f({low}) = {f_low:.2f}, f({high}) = {f_high:.2f}")
    while high - low > tolerance:
        middle = (low + high) / 2
        value = f(middle)
        trace.append((middle, value))
        if value > middle:
            low = middle
        else:
            high = middle
    return (low + high) / 2, trace


def calibrate(base: SimConfig, shares: Iterable[float], seeds: Iterable[int] = CALIBRATION_SEEDS) -> dict[float, dict]:
    """Calibrated price_sd for each informed share, rounded to TOLERANCE, with its search trace."""
    seeds = tuple(seeds)
    out = {}
    for share in shares:
        config = base.with_(informed_share=share)
        point, trace = bisect_fixed_point(lambda s: produced_error(config, s, seeds))
        out[share] = {"price_sd": round(point, 1), "trace": trace}
    return out


def main(argv: list[str] | None = None) -> dict[float, float]:
    from .experiment import CALIBRATED_PRICE_SD, DESIGNS, design_shares

    parser = argparse.ArgumentParser(description="Calibrate trust in prices at each informed share.")
    parser.add_argument("--design", choices=sorted(DESIGNS), default="informed_share")
    parser.add_argument("--check", action="store_true", help="confirm the values stored in experiment.py")
    args = parser.parse_args(argv)

    base = SimConfig(**DESIGNS[args.design]["base"])
    found = calibrate(base, design_shares(args.design))
    values = {share: entry["price_sd"] for share, entry in found.items()}
    print(f"calibrated price_sd (ticks), design {args.design}, seeds {CALIBRATION_SEEDS[0]}..{CALIBRATION_SEEDS[-1]}")
    for share, entry in found.items():
        produced = produced_error(base.with_(informed_share=share), entry["price_sd"], CALIBRATION_SEEDS)
        print(f"  {share:>4.0%}: {entry['price_sd']:6.1f}  (produces {produced:.1f}; {len(entry['trace'])} evaluations)")
    if args.check:
        stored = CALIBRATED_PRICE_SD[args.design]
        wrong = {s: (stored.get(s), v) for s, v in values.items() if abs(stored.get(s, float("nan")) - v) > 1e-9}
        if wrong:
            raise SystemExit(f"stored calibration does NOT match a fresh search (stored, fresh): {wrong}")
        print("stored values match a fresh search")
    return values


if __name__ == "__main__":
    main()
