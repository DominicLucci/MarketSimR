"""Calibrated trust: the self-consistent version of learning from prices.

With learn_from_prices on, every trader believes the mid-quote is typically `price_sd` ticks
away from the value. Calibration chooses `price_sd`, separately at each informed share, so
that this belief is correct: the root-mean-square gap between mid-quote and value that the
market produces when everyone trusts prices at `price_sd` equals `price_sd` itself.

    python -m marketsim.calibrate --design informed_share           # print, store nothing
    python -m marketsim.calibrate --design informed_share --write   # store in calibrated_trust.json
    python -m marketsim.calibrate --design informed_share --check   # the stored values still hold

Every variant marked {"trust": "calibrated"} in a design is calibrated under its own rules:
a variant changes how accurate prices are, so it needs its own trust to stay
self-consistent.

Why bisection and not repeated substitution: the produced error f(s) falls steeply as trust
s falls, with a slope near -1 around the fixed point at low informed shares, so
s <- f(s) oscillates. g(s) = f(s) - s is positive at small s (prices trusted too much drift
away from value) and negative at large s, and crosses zero once in the scanned range, so
bisection on g finds the fixed point without tuning.

Calibration uses its own seeds (CALIBRATION_SEEDS), disjoint from the experiment's seeds
0..29, so the trust is fixed before the experiment runs and is not fitted to the runs it
is then judged on. The calibrated values are stored in marketsim/calibrated_trust.json,
with the model version they were made for; `--check` reruns the search and confirms they
still match.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Callable, Iterable

import numpy as np

from .config import MODEL_VERSION, SimConfig
from .parallel import pmap
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


def _calibrate_one(task: tuple[SimConfig, tuple[int, ...]]) -> dict[str, Any]:
    config, seeds = task
    point, trace = bisect_fixed_point(lambda s: produced_error(config, s, seeds))
    value = round(point, 1)
    return {"price_sd": value, "produced": produced_error(config, value, seeds), "trace": trace}


def calibrate(
    base: SimConfig, shares: Iterable[float], seeds: Iterable[int] = CALIBRATION_SEEDS, jobs: int | None = None
) -> dict[float, dict]:
    """Calibrated price_sd for each informed share, rounded to TOLERANCE, with the error it
    produces and the search trace. Shares are searched in parallel."""
    shares, seeds = tuple(shares), tuple(seeds)
    found = pmap(_calibrate_one, [(base.with_(informed_share=s), seeds) for s in shares], jobs)
    return dict(zip(shares, found))


def calibration_configs(design: str) -> dict[str, SimConfig]:
    """For each variant of the design whose trust is calibrated: the settings it runs under."""
    from .experiment import DESIGNS

    base = SimConfig(**DESIGNS[design]["base"])
    return {
        name: base.with_(**{k: v for k, v in spec.items() if k not in ("trust", "by_share")})
        for name, spec in DESIGNS[design]["variants"].items()
        if spec.get("trust") == "calibrated"
    }


def calibrate_design(design: str, variants: Iterable[str] | None = None, jobs: int | None = None) -> dict[str, dict]:
    """{variant: {share: {"price_sd", "produced", "trace"}}}; every (variant, share) pair
    is searched in parallel."""
    from .experiment import design_shares

    configs = calibration_configs(design)
    names = list(configs) if variants is None else list(variants)
    unknown = set(names) - set(configs)
    if unknown:
        raise ValueError(f"not calibrated variants of {design}: {sorted(unknown)}")
    shares = design_shares(design)
    pairs = [(name, share) for name in names for share in shares]
    found = pmap(_calibrate_one, [(configs[n].with_(informed_share=s), CALIBRATION_SEEDS) for n, s in pairs], jobs)
    out: dict[str, dict] = {name: {} for name in names}
    for (name, share), entry in zip(pairs, found):
        out[name][share] = entry
    return out


def store(design: str, found: dict[str, dict], path=None) -> None:
    """Write the found values into the trust table, replacing this design's entries. Entries
    for variants the design no longer has are dropped."""
    from .experiment import TRUST_TABLE, calibrated_variant_names

    path = TRUST_TABLE if path is None else path
    data = json.loads(path.read_text()) if path.exists() else {"trust": {}}
    if data.get("model_version") not in (None, MODEL_VERSION):
        data["trust"] = {}  # values for another model version are void
    data["model_version"] = MODEL_VERSION
    data["seeds"] = [CALIBRATION_SEEDS[0], CALIBRATION_SEEDS[-1]]
    entries = {k: v for k, v in data["trust"].get(design, {}).items() if k in calibrated_variant_names(design)}
    for name, shares in found.items():
        entries[name] = {str(share): entry["price_sd"] for share, entry in shares.items()}
    data["trust"][design] = dict(sorted(entries.items()))
    data["trust"] = dict(sorted(data["trust"].items()))
    path.write_text(json.dumps(data, indent=2) + "\n")


def main(argv: list[str] | None = None) -> dict[str, dict[float, float]]:
    from .experiment import DESIGNS, load_trust_table

    parser = argparse.ArgumentParser(description="Calibrate trust in prices at each informed share.")
    parser.add_argument("--design", choices=sorted(DESIGNS), default="informed_share")
    parser.add_argument("--variant", action="append", help="calibrate only this variant (repeatable)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="store the values in marketsim/calibrated_trust.json")
    group.add_argument("--check", action="store_true", help="confirm the stored values")
    args = parser.parse_args(argv)

    found = calibrate_design(args.design, args.variant)
    values = {name: {share: e["price_sd"] for share, e in shares.items()} for name, shares in found.items()}
    print(f"calibrated price_sd (ticks), design {args.design}, seeds {CALIBRATION_SEEDS[0]}..{CALIBRATION_SEEDS[-1]}")
    for name, shares in found.items():
        cells = "  ".join(f"{share:.0%}: {e['price_sd']:5.1f} (makes {e['produced']:5.1f})" for share, e in shares.items())
        print(f"  {name:>20}  {cells}")
    if args.write:
        store(args.design, found)
        print("stored in marketsim/calibrated_trust.json")
    if args.check:
        table = load_trust_table()
        if table["model_version"] != MODEL_VERSION:
            raise SystemExit(f"stored trust is for model {table['model_version']}, the code is {MODEL_VERSION}")
        stored = table["trust"].get(args.design, {})
        wrong = {
            f"{name} {share:.0%}": (stored.get(name, {}).get(share), value)
            for name, shares in values.items()
            for share, value in shares.items()
            if stored.get(name, {}).get(share) != value
        }
        if wrong:
            raise SystemExit(f"stored calibration does NOT match a fresh search (stored, fresh): {wrong}")
        print("stored values match a fresh search")
    return values


if __name__ == "__main__":
    main()
