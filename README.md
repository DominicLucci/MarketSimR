# MarketSimR

An artificial exchange where software traders buy and sell one asset. The simulation knows
the asset's underlying value; each trader only gets a noisy private estimate of it. The
project asks **how the proportion of better-informed traders affects price accuracy,
liquidity and trader profits.**

**Status:** work in progress. See [docs/STATUS.md](docs/STATUS.md) for what is built, what
has been checked, and the next unfinished milestone.

## Run it

Requires Python 3.12 or newer. Checked with Python 3.13.18 and pytest 9.1.1.

```
python -m pytest              # run all checks
python -m marketsim.example   # replay the first hand-worked case and print each step
```

The exchange engine uses only the standard library. Tests need `pytest`.

## The first hand-worked case

A seller with five shares offers three at $10.00. A buyer with $50.00 bids for two at a
limit of $10.10. The engine produces one trade of two shares at $10.00:

```
#3   t=0   order     #3 trader 1 sell 3 @ $10.00
#4   t=0   order     #4 trader 2 buy 2 @ $10.10
#5   t=0   trade     2 @ $10.00  buyer 2 (order #4), seller 1 (order #3)
#6   t=0   cancelled #3 trader 1, 1 unfilled
```

| Account | Total cash | Total shares | Reserved before the cancel |
| --- | ---: | ---: | --- |
| Buyer | $30.00 | 2 | none |
| Seller | $20.00 | 3 | 1 share |

## How the code is organized

| File | Role |
| --- | --- |
| `marketsim/exchange.py` | Order entry, price-time matching, settlement, cancellation, expiry |
| `marketsim/book.py` | The resting orders, ranked by price then arrival |
| `marketsim/accounts.py` | Cash, shares and reservations per trader |
| `marketsim/events.py` | The append-only event log that analysis reads |
| `marketsim/checks.py` | Accounting and book invariants, run after every operation in tests |
| `marketsim/script.py` | Replayable lists of commands |
| `tests/reference.py` | An independent naive implementation used to cross-check the engine |

The trading rules are written out in [docs/model_rules.md](docs/model_rules.md).
