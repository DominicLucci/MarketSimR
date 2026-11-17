"""Run independent tasks on several processor cores.

Every run is a pure function of its settings, so running them in parallel cannot change a
result: `pmap` returns results in the order of its inputs, exactly as a plain loop would.
The number of worker processes is the machine's core count, or MARKETSIM_JOBS if set
(MARKETSIM_JOBS=1 runs everything in this process, which is easier to debug).
"""

from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def workers() -> int:
    setting = os.environ.get("MARKETSIM_JOBS")
    if setting:
        return max(1, int(setting))
    return os.cpu_count() or 1


def pmap(fn: Callable[[T], R], items: Iterable[T], jobs: int | None = None) -> list[R]:
    """[fn(x) for x in items], spread over worker processes. `fn` must be a module-level
    function so that worker processes can find it."""
    items = list(items)
    jobs = workers() if jobs is None else jobs
    if jobs <= 1 or len(items) < 2:
        return [fn(item) for item in items]
    # fork is fast and safe here on Linux; elsewhere start clean worker processes.
    context = get_context("fork" if sys.platform.startswith("linux") else "spawn")
    chunk = max(1, len(items) // (jobs * 8))
    with ProcessPoolExecutor(max_workers=min(jobs, len(items)), mp_context=context) as pool:
        return list(pool.map(fn, items, chunksize=chunk))
