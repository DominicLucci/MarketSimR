"""Saving a run so that someone else can regenerate and inspect it."""

from __future__ import annotations

import csv
import json
import platform
from pathlib import Path
from typing import Any

import numpy as np

from .events import write_jsonl
from .metrics import summarize, trader_outcomes
from .simulation import RunResult


def run_manifest(result: RunResult) -> dict[str, Any]:
    """The three things that determine a run, plus the environment it ran in."""
    return {
        "model_version": result.model_version,
        "config": result.config.to_dict(),
        "environment": {"python": platform.python_version(), "numpy": np.__version__},
    }


def save_run(result: RunResult, directory: str | Path) -> Path:
    """Write manifest, summary, event log, decisions, value path and trader outcomes."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(run_manifest(result), indent=2) + "\n")
    (out / "summary.json").write_text(json.dumps(summarize(result), indent=2) + "\n")
    write_jsonl(result.events, out / "events.jsonl")
    _write_csv(out / "decisions.csv", result.decisions)
    _write_csv(out / "traders.csv", trader_outcomes(result))
    _write_csv(
        out / "value_path.csv",
        [{"time": t, "value": float(v)} for t, v in enumerate(result.value_path)],
    )
    _write_csv(
        out / "quotes.csv",
        [
            {"time": t, "best_bid": bid, "bid_size": bid_size, "best_ask": ask, "ask_size": ask_size}
            for t, bid, bid_size, ask, ask_size in result.quote_samples
        ],
    )
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        if not rows:
            return
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
