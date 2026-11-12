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

## 7. Underlying value and private signals (provisional)

- The value starts at $100.00 (10,000 ticks). On each step, with probability `news_prob`
  (2%), news arrives and the value is multiplied by `exp(x)`, where `x` is normal with
  standard deviation `news_sigma` (0.5%). Otherwise it stays put. It is always positive.
  Discrete news makes "how fast do trades reflect a change" a well-posed question.
- A trader's signal is `value + sigma x z`, where `z` is a standard normal draw from the
  trader's own random stream and `sigma` depends only on its group: $0.10 for the
  better-informed group, $1.00 for the others.
- Both groups see the same public quotes and get the same endowment ($1,000.00 and 10
  shares), the same arrival process and the same decision rule. The decision rule is a
  function that receives no group label (`marketsim/traders.py`).

## 8. Trader behaviour (provisional)

Each time a trader arrives:

1. Any order it still has resting is cancelled. A trader has at most one live order.
2. It draws an inventory need uniformly from -5 to +5 shares. Its target is its starting
   10 shares plus that need. This is the trader's reason to trade.
3. **Inventory sets side and size.** Below target it buys, above target it sells, at
   target it sends nothing. Size is the gap to target, capped at 5 shares and by what the
   account can fund.
4. **The signal sets the price.** A buyer bids `signal - margin` rounded down. A seller
   offers `signal + margin` rounded up. The margin is $0.20.
5. The order expires after 80 steps if still resting.

`python -m marketsim.run --seed 1 --informed-share 0.25 --trace-step 1` prints one
decision from its inputs to its fills.

### What this baseline assumes, and what that limits

- **Traders do not learn from prices.** A less-informed trader treats its own noisy
  signal as its estimate and ignores what the quotes imply. Every trade is zero-sum on a
  common value, so the less-informed group loses on average and keeps trading anyway. This
  makes the mechanism easy to trace, and it means the model cannot show less-informed
  traders protecting themselves by widening quotes or withdrawing.
- **Inventory does not move the price a trader will accept.** Need decides only side and
  size. Two equally informed traders with opposite needs both hold out for the margin and
  mostly do not trade with each other unless news has made a resting quote stale.
- **No trader takes a position beyond its inventory target.** Better-informed traders
  profit by trading on better terms in the direction they already wanted to go, not by
  speculating without limit.

These three are the first things to revisit if the results need to speak to real markets.

## 9. Randomness and paired runs

Everything random comes from the seed through separate streams (`marketsim/world.py`):
news timing, news size, the arrival schedule, the order in which traders become informed,
and one private stream per trader. Consequences, each tested in `tests/test_simulation.py`:

- Changing the informed share, the margin or any trader setting leaves the value path and
  the arrival schedule untouched.
- A trader's k-th arrival gets the same standardized signal error and the same inventory
  need in every run with that seed.
- Informed groups are nested: going from 10% to 25% adds six traders and removes none.
- **Information access:** multiplying all values after step 300 by 1.5 leaves every event
  and decision before step 300 unchanged.
- **Equal-information control:** with one signal precision for both groups, runs with 0%,
  10% and 75% labelled "better informed" produce identical event logs.
- **Replay:** model version + configuration (which includes the seed) reproduce the event
  log, balances and summary exactly.

## 10. Measures (`marketsim/metrics.py`)

All in ticks, one row per run. Anything that cannot be computed is reported as
unavailable, never as zero.

- **Price accuracy:** mean over trades of `|trade price - value at that step|`.
- **Liquidity:** quotes are sampled every 10 steps after the arriving trader acts. Reported:
  mean best offer minus best bid when both exist, mean shares at each best quote, the share
  of samples with no bid, with no offer and with both, and traded volume.
- **Trader outcomes:** per group, the mean per-trader wealth change with stock marked at
  the underlying value at the start and end, and the mean trading gain, which is final
  wealth minus the final wealth of the same trader had it never traded. Trading gains sum
  to zero across all traders.
