"""The experiment's statistics and its end-to-end output."""

import json

import pandas as pd
import pytest

from marketsim.config import SimConfig
from marketsim.experiment import SHARES, VARIANTS, mean_interval, paired_table, run_experiment


def test_mean_interval_matches_a_hand_calculation():
    # mean 3, sample sd sqrt(2.5); t(0.975, 4) = 2.7764; half-width = 2.7764 * sqrt(2.5 / 5)
    result = mean_interval(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert result["n"] == 5 and result["mean"] == pytest.approx(3.0)
    assert result["sd"] == pytest.approx(2.5**0.5)
    assert result["ci_low"] == pytest.approx(3.0 - 1.96324, abs=1e-4)
    assert result["ci_high"] == pytest.approx(3.0 + 1.96324, abs=1e-4)


def test_mean_interval_counts_only_available_values():
    assert mean_interval(pd.Series([None, None], dtype=float)) == {
        "n": 0, "mean": None, "sd": None, "ci_low": None, "ci_high": None,
    }
    one = mean_interval(pd.Series([4.0, None]))
    assert (one["n"], one["mean"], one["ci_low"]) == (1, 4.0, None)  # no interval from one seed


def test_paired_table_differences_within_seed_not_across():
    """Seeds differ wildly in level but every seed moves by exactly -1 per setting step."""
    rows = []
    for seed, level in ((0, 10.0), (1, 500.0), (2, -40.0)):
        for step, share in enumerate(SHARES):
            row = {"variant": "main", "seed": seed, "informed_share": share}
            row.update({m: level - step for m in ("price_error", "spread", "volume", "n_trades", "bid_size", "ask_size", "share_two_sided")})
            rows.append(row)
    rows[1]["spread"] = None  # seed 0 has no two-sided quotes at 10%: that pair must drop out
    table = paired_table(pd.DataFrame(rows))

    price = table[table["measure"] == "price_error"].set_index("informed_share")
    assert price["mean_difference"].tolist() == pytest.approx([-1.0, -2.0, -3.0, -4.0])
    assert price["sd_difference"].tolist() == pytest.approx([0.0] * 4)
    assert price["n_pairs"].tolist() == [3, 3, 3, 3]
    spread = table[table["measure"] == "spread"].set_index("informed_share")
    assert spread.loc[0.10, "n_pairs"] == 2 and spread.loc[0.25, "n_pairs"] == 3


def test_experiment_writes_a_complete_and_repeatable_result(tmp_path):
    base = SimConfig(n_steps=300)
    first = run_experiment(base, 2, tmp_path / "a", chart=True)
    second = run_experiment(base, 2, tmp_path / "b", chart=False)

    assert {p.name for p in first.iterdir()} == {
        "manifest.json", "control.json", "runs.csv", "levels.csv",
        "paired_differences.csv", "market_measures.png", "trader_outcomes.png",
    }
    for name in ("manifest.json", "control.json", "runs.csv", "levels.csv", "paired_differences.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name

    runs = pd.read_csv(first / "runs.csv")
    assert len(runs) == len(VARIANTS) * 2 * len(SHARES)
    # The 0% baseline is the same market in both variants: nobody has the better signal.
    baseline = runs[runs["informed_share"] == 0.0].drop(columns="variant")
    assert baseline.iloc[:2].reset_index(drop=True).equals(baseline.iloc[2:].reset_index(drop=True))

    manifest = json.loads((first / "manifest.json").read_text())
    assert manifest["runs"] == {"grid": 20, "control": 10} and manifest["seeds"] == [0, 1]
    assert manifest["base_config"]["n_steps"] == 300
    assert json.loads((first / "control.json").read_text())["identical_within_every_seed"] is True
