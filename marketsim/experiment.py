"""The first experiment: vary the share of better-informed traders.

    python -m marketsim.experiment                 # 30 seeds, writes results/informed_share
    python -m marketsim.experiment --seeds 5 --out results/scratch/quick

For every seed, all informed shares are run on the same value path, the same arrival
schedule and the same per-trader luck, so settings are compared within a seed. The summary
is the average within-seed difference from the 0% baseline with a 95% interval across
seeds. Individual trades inside a run share one market history and are not treated as
independent observations; the seed is the unit.

Three parts:

1. main                the configured gap in signal precision
2. narrow_gap          sensitivity: the better-informed error is 5x larger (a smaller gap)
3. short_lived_orders  sensitivity: resting orders expire after 20 steps instead of 80
4. control             equal information for both groups; relabelling must change nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
from scipy import stats

from .config import MODEL_VERSION, SimConfig
from .events import to_record
from .metrics import summarize
from .news import HORIZONS, WINDOW, last_trade_path, response_curve
from .simulation import run_simulation

SHARES = (0.0, 0.10, 0.25, 0.50, 0.75)
BASELINE_SHARE = 0.0
VARIANTS: dict[str, dict[str, Any]] = {
    "main": {},
    "narrow_gap": {"sigma_informed": 50.0},
    "short_lived_orders": {"order_lifetime": 20},
}
# Measures that exist at every share, compared with the 0% baseline within a seed.
MARKET_MEASURES = (
    "price_error", "mid_error", "spread", "volume", "n_trades", "bid_size", "ask_size", "share_two_sided",
    *(f"news_in_mid_{h}" for h in HORIZONS), *(f"news_in_trades_{h}" for h in HORIZONS), "news_half_life_mid",
)
# Measures reported as levels. Some are unavailable when a group is empty.
LEVEL_MEASURES = MARKET_MEASURES + (
    "price_error_both_informed",
    "price_error_mixed",
    "price_error_neither_informed",
    "trading_gain_informed",
    "trading_gain_uninformed",
    "gain_gap",
    "wealth_change_informed",
    "wealth_change_uninformed",
)
CONTROL_SEEDS = 5

# Each design is one saved experiment: settings applied to every run, the variants compared,
# and where the results live.
DESIGNS: dict[str, dict[str, Any]] = {
    # News arrives at random. The main experiment.
    "informed_share": {"out": "results/informed_share", "base": {}, "variants": VARIANTS},
    # News arrives every 100 steps with a fixed size of 0.5% in a random direction, so every
    # event is isolated and equally large. Built to measure the news response precisely.
    "scheduled_news": {
        "out": "results/scheduled_news",
        "base": {"news_every": 100},
        "variants": {"main": {}, "short_lived_orders": {"order_lifetime": 20}},
    },
}


def mean_interval(values: pd.Series) -> dict[str, Any]:
    """Mean and 95% t-interval across seeds. Unavailable values are dropped and counted out."""
    x = values.dropna().to_numpy(dtype=float)
    n = len(x)
    out: dict[str, Any] = {"n": n, "mean": None, "sd": None, "ci_low": None, "ci_high": None}
    if n == 0:
        return out
    out["mean"] = float(x.mean())
    if n >= 2:
        sd = float(x.std(ddof=1))
        half = float(stats.t.ppf(0.975, n - 1)) * sd / np.sqrt(n)
        out.update(sd=sd, ci_low=out["mean"] - half, ci_high=out["mean"] + half)
    return out


def run_grid(base: SimConfig, seeds: list[int], variants: dict[str, dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every variant x seed x informed share.

    Returns one row per run, and the news-response curve of every run in long form
    (one row per run and number of steps after news).
    """
    rows, curves = [], []
    for variant, overrides in variants.items():
        for seed in seeds:
            for share in SHARES:
                config = base.with_(seed=seed, informed_share=share, **overrides)
                result = run_simulation(config)
                row = {"variant": variant, **summarize(result)}
                informed, others = row["trading_gain_informed"], row["trading_gain_uninformed"]
                row["gain_gap"] = None if informed is None or others is None else informed - others
                rows.append(row)
                in_mid = response_curve(result.value_path, result.mid_path)["reflected"]
                in_trades = response_curve(result.value_path, last_trade_path(result.events, config.n_steps))["reflected"]
                for k in range(WINDOW + 1):
                    curves.append(
                        {"variant": variant, "seed": seed, "informed_share": share, "steps_after_news": k,
                         "in_mid": in_mid[k], "in_trades": in_trades[k]}
                    )
    return pd.DataFrame(rows), pd.DataFrame(curves)


def news_table(curves: pd.DataFrame) -> pd.DataFrame:
    """Share of news reflected k steps later: mean and 95% interval across seeds."""
    rows = []
    for (variant, share, k), group in curves.groupby(["variant", "informed_share", "steps_after_news"], sort=True):
        for series in ("in_mid", "in_trades"):
            rows.append(
                {"variant": variant, "informed_share": share, "steps_after_news": k, "series": series,
                 **mean_interval(group[series])}
            )
    return pd.DataFrame(rows)


def levels_table(runs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (variant, share), group in runs.groupby(["variant", "informed_share"], sort=True):
        for measure in LEVEL_MEASURES:
            rows.append(
                {"variant": variant, "informed_share": share, "measure": measure, **mean_interval(group[measure])}
            )
    return pd.DataFrame(rows)


def paired_table(runs: pd.DataFrame) -> pd.DataFrame:
    """Within-seed difference from the baseline share, averaged across seeds."""
    rows = []
    for variant, group in runs.groupby("variant", sort=True):
        wide = group.set_index(["seed", "informed_share"])
        for measure in MARKET_MEASURES:
            table = wide[measure].unstack("informed_share").astype(float)
            for share in SHARES:
                if share == BASELINE_SHARE:
                    continue
                difference = table[share] - table[BASELINE_SHARE]  # NaN if either side is unavailable
                rows.append(
                    {
                        "variant": variant,
                        "informed_share": share,
                        "measure": measure,
                        "baseline_share": BASELINE_SHARE,
                        **mean_interval(difference),
                    }
                )
    return pd.DataFrame(rows).rename(columns={"n": "n_pairs", "mean": "mean_difference", "sd": "sd_difference"})


def _fingerprint(events: list) -> str:
    digest = hashlib.sha256()
    for event in events:
        digest.update(json.dumps(to_record(event), sort_keys=True).encode())
    return digest.hexdigest()


def equal_information_control(base: SimConfig, seeds: list[int]) -> dict[str, Any]:
    """Give both groups the same precision. The 'better informed' label must then be inert."""
    equal = base.with_(sigma_informed=base.sigma_uninformed)
    mismatched = []
    for seed in seeds:
        prints = {share: _fingerprint(run_simulation(equal.with_(seed=seed, informed_share=share)).events) for share in SHARES}
        if len(set(prints.values())) != 1:
            mismatched.append(seed)
    return {
        "description": "both groups get sigma_uninformed; event logs compared across informed shares",
        "seeds": seeds,
        "shares": list(SHARES),
        "runs": len(seeds) * len(SHARES),
        "identical_within_every_seed": not mismatched,
        "seeds_with_differences": mismatched,
    }


def run_experiment(
    base: SimConfig, n_seeds: int, out_dir: str | Path, chart: bool = True, design: str = "informed_share"
) -> Path:
    """Run one design. `base` must already include the design's own base settings."""
    variants = DESIGNS[design]["variants"]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    seeds = list(range(n_seeds))

    control = equal_information_control(base, seeds[:CONTROL_SEEDS])
    (out / "control.json").write_text(json.dumps(control, indent=2) + "\n")
    if not control["identical_within_every_seed"]:
        raise SystemExit(f"equal-information control failed for seeds {control['seeds_with_differences']}")

    runs, curves = run_grid(base, seeds, variants)
    levels, paired, news = levels_table(runs), paired_table(runs), news_table(curves)
    runs.to_csv(out / "runs.csv", index=False)
    levels.to_csv(out / "levels.csv", index=False)
    paired.to_csv(out / "paired_differences.csv", index=False)
    news.to_csv(out / "news_response.csv", index=False)

    base_settings = base.to_dict()
    del base_settings["seed"], base_settings["informed_share"]  # these two are varied
    manifest = {
        "command": "python -m marketsim.experiment"
        + ("" if design == "informed_share" else f" --design {design}")
        + f" --seeds {n_seeds}"
        + ("" if base.n_steps == SimConfig().n_steps else f" --steps {base.n_steps}"),
        "design": design,
        "model_version": MODEL_VERSION,
        "base_config": base_settings,
        "seeds": seeds,
        "informed_shares": list(SHARES),
        "variants": variants,
        "runs": {"grid": len(runs), "control": control["runs"]},
        "unit_of_analysis": "seed; 95% t-interval of within-seed differences from the 0% baseline",
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    if chart:
        from .charts import market_chart, news_chart, outcomes_chart

        if design == "informed_share":
            market_chart(runs, paired, out / "market_measures.png")
            outcomes_chart(runs, levels, out / "trader_outcomes.png")
            news_chart(news, n_seeds, out / "news_response.png")
        else:
            news_chart(
                news, n_seeds, out / "news_response.png",
                subtitle=f"Mean over {n_seeds} seeds. The value changes by {base.news_sigma:.1%} every "
                f"{base.news_every} steps, up or down at random.",
            )
    return out


TABLES = ("runs.csv", "levels.csv", "paired_differences.csv", "news_response.csv")


def check_results(reference_dir: str | Path, tolerance: float = 1e-9) -> list[str]:
    """Regenerate the experiment and compare it with saved results. Returns the problems found.

    Numbers are compared with a small tolerance, not byte for byte, because different
    processors and library builds can differ in the last digit of a floating-point result.
    """
    reference = Path(reference_dir)
    manifest = json.loads((reference / "manifest.json").read_text())
    if manifest["model_version"] != MODEL_VERSION:
        return [f"saved results are from model {manifest['model_version']}, the code is {MODEL_VERSION}"]
    base = SimConfig.from_dict(manifest["base_config"])
    problems = []
    with tempfile.TemporaryDirectory() as scratch:
        fresh = run_experiment(
            base, len(manifest["seeds"]), scratch, chart=False, design=manifest.get("design", "informed_share")
        )
        for name in TABLES:
            try:
                pd.testing.assert_frame_equal(
                    pd.read_csv(reference / name), pd.read_csv(fresh / name), check_exact=False, rtol=tolerance, atol=tolerance
                )
            except AssertionError as error:
                problems.append(f"{name}: {str(error).splitlines()[0]}")
        if json.loads((reference / "control.json").read_text()) != json.loads((fresh / "control.json").read_text()):
            problems.append("control.json differs")
    return problems


def results_text(out: Path) -> str:
    """A compact text table of the main variant's paired differences."""
    paired = pd.read_csv(out / "paired_differences.csv")
    if json.loads((out / "manifest.json").read_text()).get("design") == "scheduled_news":
        lines = ["news half-life in steps: difference from the 0% baseline, mean [95% interval] across seeds"]
        rows = paired[paired["measure"] == "news_half_life_mid"]
        for variant, group in rows.groupby("variant", sort=True):
            lines.append(f"  {variant}")
            for _, row in group.iterrows():
                lines.append(
                    f"    {row['informed_share']:>4.0%}: {row['mean_difference']:>6.2f} "
                    f"[{row['ci_low']:.2f}, {row['ci_high']:.2f}]  n={int(row['n_pairs'])}"
                )
        return "\n".join(lines)
    main = paired[(paired["variant"] == "main") & paired["measure"].isin(["price_error", "spread", "volume"])]
    lines = ["difference from the 0% baseline, mean [95% interval] across seeds (main variant)"]
    for measure, unit in (("price_error", 100.0), ("spread", 100.0), ("volume", 1.0)):
        label = {"price_error": "price error ($)", "spread": "quoted spread ($)", "volume": "volume (shares)"}[measure]
        lines.append(f"  {label}")
        for _, row in main[main["measure"] == measure].iterrows():
            lines.append(
                f"    {row['informed_share']:>4.0%}: {row['mean_difference'] / unit:>9.2f} "
                f"[{row['ci_low'] / unit:.2f}, {row['ci_high'] / unit:.2f}]  n={int(row['n_pairs'])}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="Informed-share experiment with paired seeds.")
    parser.add_argument("--seeds", type=int, default=30, help="number of seeds (0..N-1)")
    parser.add_argument("--steps", type=int, default=SimConfig().n_steps)
    parser.add_argument("--design", choices=sorted(DESIGNS), default="informed_share")
    parser.add_argument("--out", help="results directory (default: the design's own)")
    parser.add_argument("--no-chart", action="store_true")
    parser.add_argument("--check", action="store_true", help="regenerate and compare with the results saved in --out")
    args = parser.parse_args(argv)

    args.out = args.out or DESIGNS[args.design]["out"]
    if args.check:
        problems = check_results(args.out)
        if problems:
            raise SystemExit("saved results do NOT match a fresh run:\n  " + "\n  ".join(problems))
        print(f"saved results in {args.out}/ match a fresh run")
        return Path(args.out)

    base = SimConfig(n_steps=args.steps, **DESIGNS[args.design]["base"])
    out = run_experiment(base, args.seeds, args.out, chart=not args.no_chart, design=args.design)
    print(results_text(out))
    print(f"\nwrote {out}/")
    return out


if __name__ == "__main__":
    main()
