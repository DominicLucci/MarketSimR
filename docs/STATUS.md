# Status

Updated at the end of each build session so the next session has a verifiable place to
pick up.

## Session 1 (2026-11-12)

### Built

- Exchange engine covering handoff weeks 1 and 2: clock, price-time matching, reservations,
  settlement, partial fills, cancellation, expiry, event log, invariant checks, replay.

### Checks run

- `python -m pytest`: 52 passed.
- `python -m marketsim.example`: one trade of 2 @ $10.00; buyer ends with $30.00 and 2
  shares; seller ends with $20.00 and 3 shares, 1 reserved until the cancel.
- Engine against the independent reference model: 300 random streams x 200 commands,
  identical after every command.
- Eight deliberately planted bugs (wrong trade price, late expiry, wrong reservation
  release, last-in-first-out queue, worst bid first, ignored cash reservations, self-trades
  allowed, strict sell crossing) were each caught by the suite.

### Choices made without Dominic, to confirm or change

- Tick of $0.01, integer steps, one arrival per step, limit orders only, whole-order
  rejection (the defaults from the planning table).
- Self-trade rule: an order that would cross the trader's own resting order is rejected.
- Expiry convention: `expires_at = T` means gone at the start of step `T`.

### Next unfinished milestone

Week 3: underlying value path, private signals, inventory motives, the two trader groups,
and a pilot run.
