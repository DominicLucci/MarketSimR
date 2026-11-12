# Status

Updated at the end of each build session so the next session has a verifiable place to
pick up.

## Where things stand (after session 2, 2026-11-12)

| Handoff week | What exists | State |
| --- | --- | --- |
| 1 and 2 | Exchange engine: clock, price-time matching, reservations, settlement, partial fills, cancellation, expiry, event log, invariant checks, replay | Done and tested |
| 3 | Market model: underlying value with discrete news, private signals, inventory needs, two trader groups, one shared runner, decision trace, export | Runs and is tested; configuration is a pilot |
| 4 | Informed-share experiment: 5 shares x 30 seeds paired within seed, two sensitivity variants (450 grid runs), equal-information control (25 runs), tables and charts from one command | Done as a pilot result |
| 5 | Local dashboard on the shared runner, with same-seed comparison preset and export | Done and tested in a browser |
| 6 | Benchmark, README, automatic checks on a clean machine | Done; README numbers are pilot numbers |

`main` holds everything. GitHub runs the checks on every push.

## Session 2 (2026-11-12)

### Built

- **Automatic checks** (`.github/workflows/tests.yml`): clean install, tests, worked example
  and a regenerate-and-compare of the saved results, on Python 3.12 and 3.13 with the
  newest libraries and once with the exact tested versions (`requirements-tested.txt`).
- **`python -m marketsim.experiment --check`**: regenerates the experiment and compares it
  with the saved tables within a tolerance of 1e-9.
- **Corrected accuracy measures:** mid-quote error on every step, and trade price error
  split by whether both, one or neither side is better informed.
- **News event study** (`marketsim/news.py`): share of each isolated value change reflected
  in the mid-quote and in trade prices k steps later, and the half-life.
- **A third experiment variant,** `short_lived_orders` (orders expire after 20 steps),
  added because the news-speed result turned out to depend on order lifetime.

### Checks run

- `python -m pytest`: 89 passed.
- GitHub: all three jobs passed on the commit that added them. This is the first time the
  project was installed with `pip install -e ".[dev]"` on a clean machine.
- Adding the new measures left every previously saved number unchanged (old columns of
  `runs.csv` compared exactly for the two original variants).
- News event study checked on hand-built price series: instant, absent and gradual
  adjustment, opposite-sign events pooled as a ratio of sums, overlapping events excluded,
  missing prices skipped.
- New chart rendered and looked at.

### What changed in the findings

- The rise in trade price error at 75% is a change in which trades happen, not worse
  quotes: mid-quote error falls at every step up in the informed share.
- In the main configuration news reaches quotes more slowly when more traders are better
  informed (half-life 9 steps at 0%, 18 at 75%). With orders that expire after 20 steps
  most of that gap goes away.
- **A correction to keep in mind.** An unsaved 12-seed side check suggested the news-speed
  effect reverses with short-lived orders. The saved 30-seed experiment does not show a
  reversal, only a much smaller gap. Side checks on a few seeds are not reliable for the
  news measures; only saved results are quoted in the README now.

## Session 1 (2026-11-12)

Built the engine, market model, first experiment, dashboard, benchmark and README draft.
Checks at the time: 80 tests; engine identical to an independent reference model on 300
random streams x 200 commands; eight planted engine bugs each caught; exact replay;
information-access check; equal-information control; dashboard numbers equal to the batch
runner's; fresh clone runs every README command.

## Choices made without Dominic, to confirm or change

Engine:

- Tick of $0.01, integer steps, one arrival per step, limit orders only, whole-order
  rejection.
- Self-trade rule: an order that would cross the trader's own resting order is rejected.
- Expiry convention: `expires_at = T` means gone at the start of step `T`.

Market model (all in `marketsim/config.py`, reasoning in `docs/model_rules.md` 7 and 8):

- Value process: 2% chance of news per step, 0.5% log jump.
- Signal error: $0.10 for the better informed, $1.00 for the others.
- Decision rule: inventory need sets side and size; signal minus or plus a $0.20 margin
  sets the price; traders do not learn from prices.
- One live order per trader, never refreshed between arrivals; 80-step order lifetime.
- 4,000 steps, 40 traders.

Tooling:

- Dashboard on Python's built-in web server with plain JavaScript and SVG, no framework.
- 95% t-intervals across seeds (adds scipy as a dependency).
- News event study uses only isolated events and a 40-step window.

## Not done

- **The configuration has not been frozen.** README numbers are pilot results. Bump
  `MODEL_VERSION` in `marketsim/config.py` when a rule changes results.
- No source has been read or cited to motivate the model.
- The news measures are noisy: about 14 usable events per run.
- The dashboard does not show the new measures and has only been checked in headless
  Chrome at desktop width.

## Next unfinished milestone

1. Dominic reviews the four behavioural assumptions in `docs/model_rules.md` section 8.
   The newest one, that resting orders are never refreshed, now visibly drives a result.
2. A designed news experiment: scheduled, equal-sized, well-separated value changes
   instead of random ones, so the news response is estimated from many more events.
3. Liquidity measures: effective spread, realized spread and price impact, depth within a
   few ticks of the mid-quote.
4. Learning from prices as a switch, then rerun the experiment with it on and off.
