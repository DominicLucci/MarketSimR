"""The saved experiments: vary the share of better-informed traders under the frozen
baseline, and compare it with variants that each change one rule.

    python -m marketsim.experiment                          # writes results/informed_share
    python -m marketsim.experiment --design scheduled_news  # or robustness, news_sign
    python -m marketsim.experiment --check                  # regenerate and compare

For every seed, all informed shares are run on the same value path, the same arrival
schedule and the same per-trader luck, so settings are compared within a seed. The summary
is the average within-seed difference from the 0% baseline with a 95% interval across
seeds. Individual trades inside a run share one market history and are not treated as
independent observations; the seed is the unit.

The frozen baseline (`BASELINE`, model 1.0.0; docs/model_rules.md section 8):

* traders learn from prices, trusting the mid-quote as much as it deserves at that informed
  share (trust calibrated by marketsim/calibrate.py, separately for each variant);
* a trader's margin shrinks with its distance from its inventory target (urgency_scale 10,
  the largest gap a trader can have);
* resting orders are not refreshed when news arrives, and nobody trades beyond its target.

Variants change one thing each: no_learning, fixed_margin (the pilot's fixed $0.20),
strong_urgency (full urgency at 5 shares), narrow_gap, short_lived_orders, pull_on_news.
A variant marked {"trust": "calibrated"} gets the trust stored for it, at each share, in
marketsim/calibrated_trust.json. A variant may also carry "by_share": {share: {...}},
applied only at that share. Each design also runs the equal-information control.
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
from .parallel import pmap
from .simulation import run_simulation

SHARES = (0.0, 0.10, 0.25, 0.50, 0.75)
BASELINE_SHARE = 0.0

# The frozen baseline. Every design starts from these rules; variants change one thing.
BASELINE: dict[str, Any] = {"learn_from_prices": True, "urgency_scale": 10}
# Marks a variant whose trust in prices is calibrated at each share (marketsim/calibrate.py).
CALIBRATED: dict[str, Any] = {"trust": "calibrated"}
TRUST_TABLE = Path(__file__).with_name("calibrated_trust.json")


def load_trust_table(path: Path = TRUST_TABLE) -> dict[str, Any]:
    """The stored calibrated trust: {"model_version", "seeds", "trust": {design: {variant:
    {share: price_sd}}}}, with shares as floats. Empty if nothing has been stored."""
    if not Path(path).exists():
        return {"model_version": None, "seeds": [], "trust": {}}
    data = json.loads(Path(path).read_text())
    data["trust"] = {
        design: {variant: {float(s): float(v) for s, v in shares.items()} for variant, shares in variants.items()}
        for design, variants in data["trust"].items()
    }
    return data


NEWS_SIGN_TRUST = (15, 30, 60, 120, 240, 480)  # price_sd in ticks
NEWS_SIGN_LIFETIMES = (20, 80)

VARIANTS: dict[str, dict[str, Any]] = {
    "main": {**CALIBRATED},
    "no_learning": {"learn_from_prices": False},
    "fixed_margin": {"urgency_scale": 0, **CALIBRATED},
    "strong_urgency": {"urgency_scale": 5, **CALIBRATED},
    "narrow_gap": {"sigma_informed": 50.0, **CALIBRATED},
    "short_lived_orders": {"order_lifetime": 20, **CALIBRATED},
}
# Measures that exist at every share, compared with the 0% baseline within a seed.
MARKET_MEASURES = (
    "price_error", "mid_error", "spread", "volume", "n_trades", "bid_size", "ask_size", "share_two_sided",
    "effective_spread", "price_impact", "realized_spread",
    "impact_immediate", "impact_later", "depth_near_mid", "need_met",
    *(f"news_in_mid_{h}" for h in HORIZONS), *(f"news_in_trades_{h}" for h in HORIZONS), "news_half_life_mid",
)
# Measures reported as levels. Some are unavailable when a group is empty.
LEVEL_MEASURES = MARKET_MEASURES + (
    "price_error_both_informed",
    "price_error_mixed",
    "price_error_neither_informed",
    "need_met_informed",
    "need_met_uninformed",
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
    "informed_share": {"out": "results/informed_share", "base": dict(BASELINE), "variants": VARIANTS},
    # News arrives every 100 steps with a fixed size of 0.5% in a random direction, so every
    # event is isolated and equally large. Built to measure the news response precisely.
    "scheduled_news": {
        "out": "results/scheduled_news",
        "base": {**BASELINE, "news_every": 100},
        "variants": {
            "main": {**CALIBRATED},
            "no_learning": {"learn_from_prices": False},
            "fixed_margin": {"urgency_scale": 0, **CALIBRATED},
            "short_lived_orders": {"order_lifetime": 20, **CALIBRATED},
            "pull_on_news": {"cancel_on_news": True, **CALIBRATED},
        },
    },
    # Robustness: the scheduled-news market at twice the size and length, a finer share grid
    # up to everyone better informed, and seeds 100..129, which no other result has used.
    "robustness": {
        "out": "results/robustness",
        "base": {**BASELINE, "news_every": 100, "n_traders": 80, "n_steps": 8_000},
        "shares": (0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0),
        "first_seed": 100,
        "variants": {"main": {**CALIBRATED}, "no_learning": {"learn_from_prices": False}},
    },
    # What decides the sign of the news-speed result: fixed trust in prices from heavy
    # (price_sd $0.15) to light ($4.80), and no learning (the limit of no trust), crossed with
    # 20- and 80-step orders. Scheduled news; otherwise the baseline rules.
    "news_sign": {
        "out": "results/news_sign",
        "base": {**BASELINE, "news_every": 100},
        "variants": {
            f"{name}_life{life}": {**settings, "order_lifetime": life}
            for life in NEWS_SIGN_LIFETIMES
            for name, settings in [
                *((f"trust{t}", {"price_sd": float(t)}) for t in NEWS_SIGN_TRUST),
                ("no_learning", {"learn_from_prices": False}),
            ]
        },
    },
}


def calibrated_variant_names(design: str) -> list[str]:
    return [name for name, spec in DESIGNS[design]["variants"].items() if spec.get("trust") == "calibrated"]


def resolved_variants(design: str, table: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """The design's variants with calibrated trust filled in from the stored table."""
    table = load_trust_table() if table is None else table
    out = {}
    for name, spec in DESIGNS[design]["variants"].items():
        settings = {k: v for k, v in spec.items() if k != "trust"}
        if spec.get("trust") == "calibrated":
            if table["model_version"] != MODEL_VERSION:
                raise ValueError(
                    f"stored trust is for model {table['model_version']}, the code is {MODEL_VERSION}: "
                    f"run python -m marketsim.calibrate --design {design} --write"
                )
            stored = table["trust"].get(design, {}).get(name)
            if stored is None:
                raise ValueError(f"no calibrated trust stored for {design}/{name}: run python -m marketsim.calibrate --design {design} --write")
            settings["by_share"] = {share: {"price_sd": value} for share, value in stored.items()}
        out[name] = settings
    return out


def design_shares(design: str) -> tuple[float, ...]:
    return tuple(DESIGNS[design].get("shares", SHARES))


def baseline_config(informed_share: float, design: str = "informed_share", **changes: Any) -> SimConfig:
    """The frozen baseline at one informed share with its calibrated trust: exactly what the
    design's main variant runs. Only shares on the design's grid have a calibrated trust."""
    base = SimConfig(**DESIGNS[design]["base"])
    base.with_(informed_share=informed_share)  # a share that is not a whole number of traders fails here
    by_share = resolved_variants(design)["main"]["by_share"]
    if informed_share not in by_share:
        raise ValueError(f"no calibrated trust at informed share {informed_share}: choose one of {sorted(by_share)}")
    return base.with_(informed_share=informed_share, **by_share[informed_share], **changes)


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


def _run_one(task: tuple[str, SimConfig]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One run: its summary row and its news-response curve in long form."""
    variant, config = task
    result = run_simulation(config)
    row = {"variant": variant, **summarize(result)}
    informed, others = row["trading_gain_informed"], row["trading_gain_uninformed"]
    row["gain_gap"] = None if informed is None or others is None else informed - others
    in_mid = response_curve(result.value_path, result.mid_path)["reflected"]
    in_trades = response_curve(result.value_path, last_trade_path(result.events, config.n_steps))["reflected"]
    curve = [
        {"variant": variant, "seed": config.seed, "informed_share": config.informed_share, "steps_after_news": k,
         "in_mid": in_mid[k], "in_trades": in_trades[k]}
        for k in range(WINDOW + 1)
    ]
    return row, curve


def run_grid(
    base: SimConfig,
    seeds: list[int],
    variants: dict[str, dict[str, Any]],
    shares: tuple[float, ...] = SHARES,
    jobs: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every variant x seed x informed share, spread over processor cores.

    Returns one row per run, and the news-response curve of every run in long form
    (one row per run and number of steps after news). Variants must already be resolved
    (see resolved_variants); a variant that learns from prices must say how much it trusts
    them, so the default price_sd is never used by accident.
    """
    tasks = []
    for variant, settings in variants.items():
        if "trust" in settings:
            raise ValueError(f"variant {variant}: resolve its calibrated trust first (resolved_variants)")
        overrides = {k: v for k, v in settings.items() if k != "by_share"}
        by_share = settings.get("by_share", {})
        if "by_share" in settings and set(by_share) != set(shares):
            raise ValueError(f"variant {variant}: per-share settings must cover every share {shares}")
        learning = overrides.get("learn_from_prices", base.learn_from_prices)
        if learning and "price_sd" not in overrides and not all("price_sd" in by_share.get(s, {}) for s in shares):
            raise ValueError(f"variant {variant}: learns from prices but sets no trust (price_sd or calibrated)")
        for seed in seeds:
            for share in shares:
                tasks.append((variant, base.with_(seed=seed, informed_share=share, **overrides, **by_share.get(share, {}))))
    results = pmap(_run_one, tasks, jobs)
    rows = [row for row, _ in results]
    curves = [point for _, curve in results for point in curve]
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
            for share in sorted(group["informed_share"].unique()):
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


def equal_information_control(base: SimConfig, seeds: list[int], shares: tuple[float, ...] = SHARES) -> dict[str, Any]:
    """Give both groups the same precision. The 'better informed' label must then be inert.

    Trust in prices is held at the base setting for every share here: calibrated trust
    differs by share, which would itself change the runs and hide what is being tested."""
    equal = base.with_(sigma_informed=base.sigma_uninformed)
    mismatched = []
    for seed in seeds:
        prints = {share: _fingerprint(run_simulation(equal.with_(seed=seed, informed_share=share)).events) for share in shares}
        if len(set(prints.values())) != 1:
            mismatched.append(seed)
    return {
        "description": "both groups get sigma_uninformed and one trust in prices; event logs compared across informed shares",
        "seeds": seeds,
        "shares": list(shares),
        "runs": len(seeds) * len(shares),
        "identical_within_every_seed": not mismatched,
        "seeds_with_differences": mismatched,
    }


def run_experiment(
    base: SimConfig, n_seeds: int, out_dir: str | Path, chart: bool = True, design: str = "informed_share"
) -> Path:
    """Run one design. `base` must already include the design's own base settings."""
    variants = resolved_variants(design)
    shares = design_shares(design)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    first = DESIGNS[design].get("first_seed", 0)
    seeds = list(range(first, first + n_seeds))

    control = equal_information_control(base, seeds[:CONTROL_SEEDS], shares)
    (out / "control.json").write_text(json.dumps(control, indent=2) + "\n")
    if not control["identical_within_every_seed"]:
        raise SystemExit(f"equal-information control failed for seeds {control['seeds_with_differences']}")

    runs, curves = run_grid(base, seeds, variants, shares)
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
        + ("" if base.n_steps == DESIGNS[design]["base"].get("n_steps", SimConfig().n_steps) else f" --steps {base.n_steps}"),
        "design": design,
        "model_version": MODEL_VERSION,
        "base_config": base_settings,
        "seeds": seeds,
        "informed_shares": list(shares),
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

        if design == "news_sign":
            from .charts import news_sign_chart

            stored = load_trust_table()["trust"].get("scheduled_news", {}).get("main", {})
            band = (min(stored.values()), max(stored.values())) if stored else None
            news_sign_chart(paired, n_seeds, out / "news_sign.png", calibrated=band)
        elif design == "informed_share":
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
    design = json.loads((out / "manifest.json").read_text()).get("design")
    if design == "news_sign":
        rows = paired[(paired["measure"] == "news_in_mid_10") & (paired["informed_share"] == max(SHARES))]
        lines = ["news reflected 10 steps after it arrives: 75% minus 0% better informed, mean [95% interval]"]
        for _, row in rows.iterrows():
            lines.append(f"  {row['variant']:>22}: {row['mean_difference']:+.3f} [{row['ci_low']:+.3f}, {row['ci_high']:+.3f}]")
        return "\n".join(lines)
    if design in ("scheduled_news", "robustness"):
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
    parser = argparse.ArgumentParser(description="Informed-share experiments with paired seeds.")
    parser.add_argument("--seeds", type=int, default=30, help="number of seeds (0..N-1)")
    parser.add_argument("--steps", type=int, help="steps per run (default: the design's own)")
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

    settings = dict(DESIGNS[args.design]["base"])
    if args.steps is not None:
        settings["n_steps"] = args.steps
    base = SimConfig(**settings)
    out = run_experiment(base, args.seeds, args.out, chart=not args.no_chart, design=args.design)
    print(results_text(out))
    print(f"\nwrote {out}/")
    return out


if __name__ == "__main__":
    main()
