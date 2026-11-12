"""How fast prices take in news: an event study around each change in the underlying value.

For a news event at step T the value moves from V[T-1] to V[T]. Take a price series P
(the mid-quote, or the last trade price). k steps later, the share of the news the price
has taken in is

    sign(V[T] - V[T-1]) * (P[T+k] - P[T-1])  /  |V[T] - V[T-1]|

0 means the price has not moved, 1 means it has moved by the full amount. A single event is
noisy and small jumps would dominate a plain average of ratios, so a run reports the ratio
of sums over its events: total price movement in the direction of the news, divided by
the total size of the news.

Only isolated events are used: no other news within `window` steps before or after, and
the whole window inside the run. Otherwise the price would still be reacting to earlier
news, or would start reacting to later news, inside the window being measured.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .events import Trade

WINDOW = 40
HORIZONS = (5, 10, 20, 40)


def news_steps(values: np.ndarray) -> np.ndarray:
    """Steps at which the value differs from the step before."""
    return np.flatnonzero(np.diff(values) != 0) + 1


def isolated_events(values: np.ndarray, window: int = WINDOW) -> list[int]:
    steps = news_steps(values)
    keep = []
    for i, step in enumerate(steps):
        inside = step + window <= len(values) - 1
        quiet_before = i == 0 or step - steps[i - 1] > window
        quiet_after = i == len(steps) - 1 or steps[i + 1] - step > window
        if inside and quiet_before and quiet_after:
            keep.append(int(step))
    return keep


def response_curve(values: np.ndarray, prices: np.ndarray, window: int = WINDOW) -> dict[str, Any]:
    """Share of news reflected in `prices` 0..window steps after isolated news events.

    `prices` has one entry per step and NaN where no price exists. An event is skipped if
    there is no price just before it; a later step with no price drops out of that step's
    sums only.
    """
    moved = np.zeros(window + 1)
    news = np.zeros(window + 1)
    n_events = 0
    for step in isolated_events(values, window):
        before = prices[step - 1]
        if np.isnan(before):
            continue
        n_events += 1
        jump = values[step] - values[step - 1]
        after = prices[step : step + window + 1]
        have = ~np.isnan(after)
        moved[have] += np.sign(jump) * (after[have] - before)
        news[have] += abs(jump)
    with np.errstate(invalid="ignore", divide="ignore"):
        reflected = np.where(news > 0, moved / news, np.nan)
    return {"n_events": n_events, "reflected": reflected}


def half_life(reflected: np.ndarray) -> int | None:
    """First step at which at least half the news is reflected, or None within the window."""
    reached = np.flatnonzero(np.nan_to_num(reflected, nan=-np.inf) >= 0.5)
    return int(reached[0]) if len(reached) else None


def last_trade_path(events: list, n_steps: int) -> np.ndarray:
    """Price of the most recent trade at or before each step; NaN before the first trade."""
    path = np.full(n_steps, np.nan)
    for event in events:
        if isinstance(event, Trade):
            path[event.time] = event.price  # a later trade in the same step overwrites
    last = np.nan
    for step in range(n_steps):
        if np.isnan(path[step]):
            path[step] = last
        else:
            last = path[step]
    return path
