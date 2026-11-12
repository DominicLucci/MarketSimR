# Status

Updated at the end of each build session so the next session has a verifiable place to
pick up.

## Session 1 (2026-11-12)

### Built

| Handoff week | What exists | State |
| --- | --- | --- |
| 1 and 2 | Exchange engine: clock, price-time matching, reservations, settlement, partial fills, cancellation, expiry, event log, invariant checks, replay | Done and tested |
| 3 | Market model: underlying value with discrete news, private signals, inventory needs, two trader groups, one shared runner, per-run measures, decision trace, export | Runs and is tested; configuration is a pilot |
| 4 | Informed-share experiment: 5 shares x 30 seeds paired within seed, narrower-gap sensitivity check (300 grid runs), equal-information control (25 runs), tables and charts from one command | Done as a pilot result |
| 5 | Local dashboard on the shared runner, with same-seed comparison preset and export | Done and tested in a browser |
| 6 | Benchmark of a fixed workload; README | Benchmark measured; README drafted; clean-machine setup not tried |

### Checks run

- `python -m pytest`: 80 passed.
- Fresh clone of the pushed branch: all tests pass, every README command runs, and
  regenerating the experiment changes no file (tables and charts byte-identical).
- `python -m marketsim.example`: one trade of 2 @ $10.00; buyer ends with $30.00 and 2
  shares; seller ends with $20.00 and 3 shares, 1 reserved until the cancel.
- Engine against the independent reference model: 300 random streams x 200 commands,
  identical trades, balances, reservations and book after every command.
- Eight deliberately planted engine bugs were each caught by the suite.
- Simulation: exact replay from version + config + seed; orders unaffected by future
  values; identical event logs under equal-information relabelling; value path, arrivals
  and per-trader luck shared across settings; trading gains sum to zero.
- Experiment: interval arithmetic against a hand calculation; differences taken within
  seed; two runs write byte-identical tables; control passed.
- Dashboard: its numbers equal the batch runner's for the same settings; settings are
  recoverable from the export; opened in headless Chrome and exercised (run, same-seed
  comparison, hover tooltip, download, single-run mode) with no page errors.
- Charts and the dashboard were rendered and looked at, and layout defects were fixed.
- Side check, not saved: with news switched off (8 seeds) price error falls steadily with
  the informed share, which supports the reading that the rise at 75% comes from trades
  against quotes made stale by news.

### Choices made without Dominic, to confirm or change

Engine:

- Tick of $0.01, integer steps, one arrival per step, limit orders only, whole-order
  rejection (the defaults from the planning table).
- Self-trade rule: an order that would cross the trader's own resting order is rejected.
- Expiry convention: `expires_at = T` means gone at the start of step `T`.

Market model (all in `marketsim/config.py`, reasoning in `docs/model_rules.md` 7 and 8):

- Value process: 2% chance of news per step, 0.5% log jump.
- Signal error: $0.10 for the better informed, $1.00 for the others.
- Decision rule: inventory need sets side and size; signal minus or plus a $0.20 margin
  sets the price; traders do not learn from prices.
- One live order per trader, 80-step order lifetime, 4,000 steps, 40 traders.

Tooling:

- Dashboard on Python's built-in web server with plain JavaScript and SVG, no framework.
- 95% t-intervals across seeds for the experiment (adds scipy as a dependency).

### Not done

- **The configuration has not been frozen.** The experiment and README numbers are pilot
  results and will change if any model choice above changes. Bump `MODEL_VERSION` in
  `marketsim/config.py` when a rule changes results.
- **Setup from a clean machine.** `pip install -e ".[dev]"` has not been tried: package
  installs were unavailable in the build session. Everything was run against libraries
  already present (versions in the README).
- No source has been read or cited to motivate the model.
- The dashboard has only been checked in headless Chrome at desktop width.
- All work is on the `claude/engine` branch. `main` still holds only the first README.

### Next unfinished milestone

1. Dominic reviews the three behavioural assumptions in `docs/model_rules.md` section 8
   and the pilot numbers, then freezes or changes the configuration.
2. Rerun `python -m marketsim.experiment` and update the README tables if anything changed.
3. On a clean machine: clone, `pip install -e ".[dev]"`, run the README commands, and fix
   whatever the README got wrong.
4. Merge `claude/engine` into `main`.
