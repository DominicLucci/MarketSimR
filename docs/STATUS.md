# Status

Updated at the end of each build session so the next session has a verifiable place to
pick up.

## Where things stand (after session 8, 2026-11-17)

| Handoff week | What exists | State |
| --- | --- | --- |
| 1 and 2 | Exchange engine: clock, price-time matching, reservations, settlement, partial fills, cancellation, expiry, event log, invariant checks, replay | Done and tested |
| 3 | Market model: value with discrete news, private signals, inventory needs, two trader groups, learning from prices with calibrated trust, urgency margin, one shared runner, decision trace, export | Frozen as model 1.0.0 |
| 4 | Experiments: informed share (900 grid runs), scheduled news (750), robustness (420), news-sign map (2,100), each with an equal-information control; Glosten–Milgrom benchmark | Final results for model 1.0.0 |
| 5 | Local dashboard on the shared runner, running the frozen baseline | Done and tested; does not show the newer measures |
| 6 | Benchmark, README, automatic checks on a clean machine | Done; README numbers are model 1.0.0 results |

`main` holds everything. GitHub runs the checks on every push. The pilot is at git tag
`pilot-0.2.0`.

## Session 8 (2026-11-17)

Dominic asked the build agent to take its recommended option for each open choice. The
recommendations, and the evidence for each, are in `docs/model_rules.md` section 8.

### Built

- **Urgency margin** (`urgency_scale` in `SimConfig`, `effective_margin` in
  `marketsim/traders.py`): margin x (1 - 2 x min(1, |gap| / scale)). Off by default; 10 in
  the baseline. Two traders with the same estimate cross exactly when their urgencies add up
  to at least one.
- **The frozen baseline** (`BASELINE` in `marketsim/experiment.py`): learning from prices
  with calibrated trust, urgency scale 10. `MODEL_VERSION` is `1.0.0`. `baseline_config(share)`
  builds it; the dashboard and `marketsim.run` use it (`--pilot-rules` for the old rule).
- **Variants that change one rule each:** `no_learning`, `fixed_margin` (the pilot margin),
  `strong_urgency` (scale 5), `narrow_gap`, `short_lived_orders`, `pull_on_news`.
- **Calibrated trust for every variant that learns,** stored in
  `marketsim/calibrated_trust.json` with its model version (11 variant tables across three
  designs). `python -m marketsim.calibrate --design D [--write | --check]`. An experiment
  refuses to run if the table is for another model version, and a variant that learns
  must state its trust, so the default `price_sd` is never used by accident.
- **Runs spread over processor cores** (`marketsim/parallel.py`); results are identical to
  a plain loop. `MARKETSIM_JOBS=1` turns it off.
- All four experiments rerun under the baseline; README results, model rules and charts
  rewritten. News-sign chart shades the range of the baseline's calibrated trust.
- GitHub: calibration checks moved to three parallel jobs, one per design.

### Checks run

- Before adopting the urgency margin, an exploratory comparison on separate seeds
  (2000 to 2009): full urgency at 5 shares restored trade but roughly doubled mid-quote
  error at high shares; at 10 shares trade was restored with accuracy about unchanged.
  Hence the scale of 10, with 5 kept as a variant.
- `fixed_margin` (learning, calibrated, fixed margin) reproduces the pilot's calibrated
  trust exactly in both designs, so the new per-variant calibration code agrees with the
  old one on the old rule.
- Calibrated trust is self-consistent: in every table the error it produces is within
  1 tick of the trust.
- Tests added: urgency margin by hand, the crossing property for all 100 pairs of gaps,
  urgency keeps replay, group-neutrality and equal-information controls; resolved trust,
  stale-table refusal, trust required when learning, store/void of the table, parallel
  equals sequential; dashboard and command line run the baseline.
- `python -m pytest`: 125 passed. All four experiment `--check` commands and the benchmark
  `--check` pass.
- `python -m marketsim.calibrate --design scheduled_news --check` passes (fresh search
  matches every stored value). Every equal-information control passes.
- Every number in the new README results checked against the saved tables; four
  mis-rounded cells and one wrong sentence (about the fixed margin's accuracy) corrected.
- All charts rendered and looked at; one legend moved off a line.

### What the frozen baseline shows

- Prices get more accurate at every step up in the better-informed share (mid-quote error
  $0.43 to $0.18; to $0.15 at 100% in the larger market). Learning from prices helps most
  when few traders know much.
- More than half of inventory need is met at every share (58% to 56%); with the pilot's
  fixed margin and learning only 15% to 25%.
- With learning, news gets into prices slowly (47% after 40 steps at 0%) and
  better-informed traders speed it up (+33 points at 75%, interval +29 to +36).
- Without learning the informed share makes little difference to news speed (a small early
  slowdown, significant only in the larger market). The pilot's clear early slowdown
  depended on the fixed margin.
- Better-informed traders gain at the others' expense: $24 each at 10%, $5.50 each at 75%;
  each other trader loses more as their number grows ($2.67 to $16.50).

## Session 7 (2026-11-13)

### Built

- **Three measures** in `marketsim/metrics.py`: `depth_near_mid` (shares within $0.50 of
  the mid-quote, recorded on the quote clock as `depth_samples`), price impact split into
  `impact_immediate` and `impact_later` at the end of the trade's own step, and `need_met`
  (share of each arrival's inventory gap that its order fills, overall and by group).
- **Designs can set their own shares, first seed and length** (`shares`, `first_seed`,
  `base.n_steps` in `DESIGNS`); `--steps` now defaults to the design's own.
- **`results/robustness/`**: scheduled news, 80 traders, 8,000 steps, shares 0% to 100%,
  seeds 100 to 129; variants `main` and `learn_calibrated` (recalibrated for this market).
- **`results/news_sign/`**: fixed trust $0.15 to $4.80 plus no learning, crossed with 20-
  and 80-step orders; chart `news_sign.png`.
- **Theory benchmark** (`marketsim/glosten_milgrom.py`, `results/glosten_milgrom/`): the
  Glosten–Milgrom dealer market on the exchange, 3 informed shares x 10,000 runs x 60
  trades, against the exact expected spread and dealer profit at every step.
- GitHub's checks now regenerate all four experiments and the benchmark and rerun three
  calibrations.

### Checks run

- `python -m pytest`: 116 passed. All four experiment `--check`, the benchmark `--check`
  and all three calibration `--check` commands pass.
- Benchmark: first spread equals the formula exactly at every share; mean spread and dealer
  profit within 1.7 standard errors of exact. A 2.25-SE gap at 2,000 runs was chased down
  (exact values confirmed by an independent recursion, pure Monte Carlo agrees) and is
  sampling noise; the saved benchmark uses 10,000 runs.
- Every earlier column of `runs.csv` and every earlier measure in the other tables is
  unchanged in both original experiments.
- Depth checked against a book rebuilt independently from the event log at every sample;
  impact split and need met checked on hand-worked cases.
- News-sign chart rendered and looked at; the no-learning point separated from the trust
  line.

### What changed in the findings

- Price impact is mostly mechanical: at 0%, $0.48 of $0.51 happens on the trade's own step.
  The later part rises from $0.02 to $0.20 at 75% and is the part to read as information.
- Need met falls from 52% to 28% between 0% and 75% while depth rises sixfold. With
  learning from prices only 16% to 25% is met: the fixed $0.20 margin around a shared
  mid-quote stops orders crossing. The margin rule deserves review.
- The news slowdown is a short-horizon effect of stale long-lived quotes with little or no
  trust in prices. At 40 steps better-informed traders never slow news down.
- Robustness (bigger market, fresh seeds): patterns hold, except that mid-quote error stops
  falling after 50% better informed.

## Session 6 (2026-11-13)

### Built

- **Calibrated trust** (`marketsim/calibrate.py`): at each informed share, finds the
  `price_sd` at which the root-mean-square mid-quote error the market produces equals the
  error traders assume. Bisection on f(s) - s over $0.10 to $2.00, because f falls with a
  slope near -1 at low shares and plain substitution would oscillate. Seeds 1000 to 1019,
  disjoint from the experiment's 0 to 29. `--check` reruns the search and compares with
  the stored values.
- **Per-share settings in experiment variants** (`"by_share"`), which must cover every
  share. Stored values in `CALIBRATED_PRICE_SD` in `marketsim/experiment.py`.
- **New variant `learn_calibrated`** in both experiments (750 runs each now).
  Scheduled-news chart is now five panels.
- GitHub's checks now also rerun the calibration for both designs.

### Checks run

- `python -m pytest`: 104 passed. Both experiment `--check` commands pass; both
  calibration `--check` commands pass.
- Every earlier row of every saved table is byte-for-byte unchanged; only rows for the new
  variant were added. Control unchanged.
- Calibration scanned first on a 10-point grid to confirm a single crossing at every
  share in both designs.
- Out of sample: on seeds 0 to 29, the produced error is within 5% of the calibrated
  trust (random news) and within 2% (scheduled news).
- Five-panel news chart rendered and looked at.

### What changed in the findings

- Calibrated trust: $0.53 at 0% falling to $0.35 at 75% (random news); $0.46 to $0.25
  (scheduled news). The fixed $0.30 was too high at low shares and slightly too low at 75%.
- Most of the fixed-trust damage was the mismatch: at 0% mid-quote error falls from $0.78
  to $0.41 (baseline $0.44) and volume recovers from 206 to 1,686 (baseline 3,543).
  Learning still makes prices less accurate than the baseline at every share above 0%.
- The news reversal survives calibration: after 40 steps 22% reflected at 0%, 61% at 75%
  (difference +39 points, 95% interval +37 to +40). Whether traders learn from prices
  decides the sign of the news-speed result.

## Session 5 (2026-11-12)

### Built

- **Learning-from-prices option** (`learn_from_prices`, `price_sd` in `marketsim/config.py`;
  `estimate_value` in `marketsim/traders.py`). Off by default. A trader's estimate is a
  precision-weighted average of its signal and the mid-quote it sees.
- Added as a variant, `learn_from_prices`, of both experiments (main: 600 grid runs;
  scheduled news: 600 runs).

### Checks run

- `python -m pytest`: 98 passed. Both `--check` commands pass.
- Estimate checked on hand-worked numbers; with learning on, the run still replays
  exactly, the equal-information relabelling is still inert and orders still do not
  depend on future values.
- Earlier runs of the main experiment are unchanged.
- Four-panel news chart rendered and looked at; an overlapping subtitle and legend fixed.

### What changed in the findings

- With learning at a fixed trust of $0.30, prices anchor on themselves: quotes are tight
  but less accurate than the baseline at every share, and volume collapses at low shares.
- The direction of the news result reverses: better-informed traders now speed news up
  (after 40 steps: 9% reflected at 0%, 65% at 75%).
- **Caveat that matters:** the trust is fixed and too high at low informed shares (assumed
  $0.30, actual mid-quote error $0.59 to $0.78). The size of these effects depends on
  that mismatch.

## Session 4 (2026-11-12)

### Built

- **Cost-of-trading measures** (`spread_decomposition` in `marketsim/metrics.py`): effective
  spread, price impact and realized spread per trade, with a 10-step horizon.
- **Quote-refresh option** `cancel_on_news` (off by default): every resting order is
  cancelled on a step where the value changes. Added as a third variant, `pull_on_news`,
  of the scheduled-news experiment (now 450 runs).

### Checks run

- `python -m pytest`: 95 passed. Both `--check` commands pass.
- Decomposition checked on two hand-worked trades and on a real run (parts add up).
- Earlier columns of the main experiment's `runs.csv` are unchanged.

### What changed in the findings

- The stale-quote explanation for slow news is now tested directly: with quotes pulled on
  news the mid-quote reflects news within about one step at every informed share.
- Trading at once gets cheaper as the informed share rises (effective spread $0.68 to
  $0.24), while what the resting side keeps falls from $0.18 a share to a loss of $0.06.
- Price impact is $0.51 even with no better-informed traders, so it is mostly mechanical
  in this model and should not be read as information alone.

## Session 3 (2026-11-12)

### Built

- **Scheduled news as a model option** (`news_every` in `marketsim/config.py`): the value
  changes every N steps by a fixed log size in a random direction. Off by default, so no
  existing result changes.
- **A second saved experiment,** `python -m marketsim.experiment --design scheduled_news`,
  in `results/scheduled_news/`: 0.5% news every 100 steps, 5 shares x 30 seeds, with 80-step
  and 20-step orders (300 runs). 31 to 39 usable news events per run instead of about 14.
- GitHub's checks now regenerate and compare both experiments.

### Checks run

- `python -m pytest`: 91 passed. Both `--check` commands pass locally.
- Adding the option left every table of the main experiment unchanged (only its manifest
  gained the new setting).
- Scheduled value path checked for timing, fixed size, both directions and prefix stability.

### What changed in the findings

- The news-speed result is now firm in the main configuration: ten steps after news the
  mid-quote reflects 48% of it at 0% better informed and 24% at 75% (difference −24 points,
  95% interval −31 to −17).
- With 20-step orders the gap in quotes nearly disappears (−3 points, −12 to +5), while
  trade prices still lag at high informed shares.

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

## Choices made by the build agent

Engine:

- Tick of $0.01, integer steps, one arrival per step, limit orders only, whole-order
  rejection.
- Self-trade rule: an order that would cross the trader's own resting order is rejected.
- Expiry convention: `expires_at = T` means gone at the start of step `T`.

Market model (frozen in model 1.0.0 on Dominic's instruction to take the recommended option
for each choice; reasoning in `docs/model_rules.md` 7 and 8):

- Value process: 2% chance of news per step, 0.5% log jump.
- Signal error: $0.10 for the better informed, $1.00 for the others.
- Decision rule: inventory need sets side and size; the estimate blends signal and
  mid-quote with calibrated trust; the margin is $0.20 x (1 - 2 x urgency), urgency =
  min(1, gap / 10).
- One live order per trader, never refreshed between arrivals; 80-step order lifetime.
- 4,000 steps, 40 traders.

Tooling:

- Dashboard on Python's built-in web server with plain JavaScript and SVG, no framework.
- 95% t-intervals across seeds (adds scipy as a dependency).
- News event study uses only isolated events and a 40-step window.
- Calibration seeds 1000 to 1019; trust rounded to 0.1 tick.

## Not done

- No source has been read or cited to motivate the main model.
- In the main (random news) experiment the news measures are noisy, with about 14 usable
  events per run. Use `results/scheduled_news/` for news-speed claims.
- The dashboard does not show the newer measures (depth, impact split, need met) and has
  only been checked in headless Chrome at desktop width.
- Better-informed traders never trade beyond their need; this is the main gap between the
  model and the theory of informed trading.

## Changing the model from here

Any rule change that alters results: bump `MODEL_VERSION` in `marketsim/config.py`, run
`python -m marketsim.calibrate --design D --write` for informed_share, scheduled_news and
robustness (about 20 minutes on two cores), then regenerate all four experiments and
update the README numbers.

## Next unfinished milestone

1. Dominic reads the frozen-baseline results and the decisions in `docs/model_rules.md`
   section 8; any decision can still be reversed.
2. Benchmark aimed at the main model's measures: a Glosten–Milgrom run summarized with
   `metrics.summarize`, so the spread decomposition is checked against theory too.
3. Show the newer measures in the dashboard.
4. Read and cite sources.
5. First extension: better-informed traders who trade beyond their need when their edge
   is large (a variant, with its own calibration).
