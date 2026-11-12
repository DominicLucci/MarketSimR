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

### Checks run

- `python -m pytest`: 71 passed.
- `python -m marketsim.example`: one trade of 2 @ $10.00; buyer ends with $30.00 and 2
  shares; seller ends with $20.00 and 3 shares, 1 reserved until the cancel.
- Engine against the independent reference model: 300 random streams x 200 commands,
  identical after every command.
- Eight deliberately planted engine bugs were each caught by the suite.
- Simulation: exact replay from version + config + seed; information-access check;
  equal-information control; pairing of value path, arrivals and per-trader luck across
  settings; trading gains sum to zero.

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

### Next unfinished milestone

Week 4: paired experiments across informed shares, the sensitivity check, and one command
that regenerates the comparison and a chart.
