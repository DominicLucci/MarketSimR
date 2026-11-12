"""Time a fixed workload.

    python -m marketsim.benchmark

Workload: the default configuration (40 traders, 4,000 steps) at a 25% informed share for
seeds 0 to 4, once with the invariant checks off and once with them on. The event count is
printed so a later optimization can show it produced the same work, and the test suite
stays the judge of whether it produced the same results.
"""

from __future__ import annotations

import platform
import time

import numpy as np

from .config import MODEL_VERSION, SimConfig
from .simulation import run_simulation

SEEDS = range(5)
REPEATS = 3


def measure(check_invariants: bool) -> tuple[float, int]:
    """Best-of-REPEATS seconds for the whole workload, and the number of events it logged."""
    best, events = float("inf"), 0
    for _ in range(REPEATS):
        start = time.perf_counter()
        events = sum(
            len(run_simulation(SimConfig(seed=seed, informed_share=0.25), check_invariants=check_invariants).events)
            for seed in SEEDS
        )
        best = min(best, time.perf_counter() - start)
    return best, events


def main() -> None:
    config = SimConfig()
    steps = config.n_steps * len(SEEDS)
    print(f"model {MODEL_VERSION}; Python {platform.python_version()}, numpy {np.__version__}, {platform.machine()} {platform.system()}")
    print(f"workload: {len(SEEDS)} runs x {config.n_steps} steps x {config.n_traders} traders = {steps:,} arrivals; best of {REPEATS}")
    for label, checks in (("invariant checks off", False), ("invariant checks on ", True)):
        seconds, events = measure(checks)
        print(f"  {label}: {seconds:6.2f} s   {steps / seconds:>9,.0f} arrivals/s   {events:,} events")


if __name__ == "__main__":
    main()
