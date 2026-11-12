# Model rules

This page states the rules the code implements. Each rule names the test that checks it.
Rules marked **provisional** were chosen by the build agent to get a working baseline and
are Dominic's to confirm or change.

## 1. Units

- One asset. Quantities are whole shares.
- One tick is $0.01. Prices and cash are stored as integer ticks, so `price x quantity` is
  exact and the exchange contains no floating-point arithmetic.
- The underlying value and private signals are real numbers measured in ticks. When a
  trader turns a valuation into a limit price, buys round down and sells round up, so no
  trader quotes through its own valuation.

## 2. Clock and event order

- Time is an integer step counter. One trader arrives per step.
- Within a step, things happen in a fixed order:
  1. the underlying value updates;
  2. orders whose expiry time has come are removed and their reservations released;
  3. the arriving trader receives its signal, sees its account and the public quotes, and acts;
  4. quotes are sampled for the liquidity measures.
- Updating the value before the trader acts means quotes posted earlier can be stale
  when news arrives. A trader with a precise signal can trade against them.
- One global counter stamps every logged event with `seq`. An order's id is the `seq` of
  its acceptance, so a lower id always means an earlier arrival.

## 3. Orders and matching

- Limit orders only: side, quantity, limit price, optional expiry time. A buy priced at or
  above the best offer trades at once, so no separate market order exists.
- An incoming buy trades against the lowest-priced resting sells at or below its limit.
  An incoming sell trades against the highest-priced resting buys at or above its limit.
  (`test_matching.py`: better price first, both sides.)
- At an equal price the oldest resting order trades first. A partly filled order keeps its
  place. (`test_matching.py`: same-price queue, partial fill keeps place.)
- Every fill executes at the resting order's price. (`test_worked_example.py`)
- Any unfilled remainder rests on the book until filled, cancelled or expired.
- An order with `expires_at = T` can trade on steps before `T` and is removed at the start
  of step `T`, before anyone acts. (`test_expiry_cancel.py`)
- **Provisional:** an order priced to cross the same trader's own resting order is rejected
  whole (`would_self_trade`). A trader can therefore never trade with itself.

## 4. Accounts and reservations

- Each trader has finite cash and shares. No borrowing, no short selling, no fees. The
  market is closed: total cash and total shares never change.
- A buy reserves `limit price x quantity` of cash when it is accepted. A sell reserves its
  shares. Reserved resources cannot back a second order. (`test_accounts.py`)
- An order the account cannot fully fund is rejected whole and logged. It is never trimmed.
- On a fill, cash and shares move at the trade price. The buyer's reservation shrinks by
  `its limit x filled quantity`, so the difference between limit and trade price returns
  to available cash immediately.
- Cancellation and expiry release the reservation for the unfilled remainder.
- Proceeds of a fill are available at once.

## 5. Checks that run after every exchange operation

With `Exchange(check_invariants=True)` (`marketsim/checks.py`):

1. total cash and total shares equal their starting totals;
2. each account's reserved cash and shares equal exactly what its open orders commit,
   recomputed from the book;
3. reserved amounts are never negative and never exceed totals;
4. the book is never crossed (best bid below best ask);
5. the book's queues are in price-time order and hold no dead or expired orders.

## 6. Evidence beyond hand-worked cases

- `tests/reference.py` is a second, deliberately naive implementation of sections 3 and 4
  that shares no code with the engine. `tests/test_random_streams.py` drives 300 random
  streams of 200 commands through both and requires identical trades, balances,
  reservations and resting books after every command.
- The same file checks that the random streams really do produce partial fills,
  cancellations, expiries and each kind of rejection.
- Replaying a saved list of commands reproduces the event log exactly (`test_replay.py`).
