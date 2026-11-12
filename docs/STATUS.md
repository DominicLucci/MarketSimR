# Status

Updated at the end of each build session so the next session has a verifiable place to
pick up.

## Session 1 (2026-11-12)

### Built

- **Weeks 1 and 2, exchange engine:** clock, price-time matching, reservations, settlement,
  partial fills, cancellation, expiry, event log, invariant checks, replay.
- **Week 3, market model (pilot):** underlying value with discrete news, private signals,
  inventory needs, two trader groups, one shared simulation runner, per-run measures,
  a command-line run with a decision trace and an export.
- **Week 4, first experiment (pilot):** five informed shares x 30 seeds, paired within seed,
  plus a narrower-precision-gap sensitivity check (300 grid runs) and an equal-information
  control (25 runs). One command regenerates tables and charts in `results/informed_share/`.

### Checks run

- `python -m pytest`: 75 passed.
- `python -m marketsim.example`: one trade of 2 @ $10.00; buyer ends with $30.00 and 2
  shares; seller ends with $20.00 and 3 shares, 1 reserved until the cancel.
- Engine against the independent reference model: 300 random streams x 200 commands,
  identical after every command.
- Eight deliberately planted engine bugs were each caught by the suite.
- Simulation: exact replay from version + config + seed; information-access check;
  equal-information control; pairing of value path, arrivals and per-trader luck across
  settings; trading gains sum to zero.
- Experiment: interval arithmetic against a hand calculation; differences taken within
  seed; two runs of the experiment write byte-identical tables; control passed.
- Charts were rendered and looked at; label rendering and clipped subtitles were fixed.
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

The configuration is a pilot. It has not been frozen.

### Not done

- The configuration has not been frozen, so the experiment is a pilot result.
- `pip install -e ".[dev]"` has not been tried: package installs were unavailable in the
  build session. Commands were run against libraries already present.
- No performance benchmark yet (week 6).

### Next unfinished milestone

Week 5: the dashboard on the shared runner (`marketsim.simulation.run_simulation`), with a
preset that reuses one seed across two informed shares and an export of configuration and
results. `marketsim.storage.save_run` already writes the export files.

Before that, Dominic should decide whether to keep the pilot configuration and the three
behavioural assumptions listed in `docs/model_rules.md` section 8, since the dashboard
and README will present whatever the model does.
