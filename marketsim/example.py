"""The first hand-worked case, replayed through the engine.

Run with:  python -m marketsim.example

A seller with five shares offers three at $10.00. A buyer with $50.00 bids for two at a
limit of $10.10. Expect one trade of two shares at $10.00, twenty cents of the buyer's
reservation released, and one seller share still reserved until the remainder is cancelled.
"""

from __future__ import annotations

from .events import Side, Trade
from .exchange import Exchange
from .render import accounts_text, book_text, describe
from .script import Advance, Cancel, Command, Open, Submit, run_script
from .units import to_ticks

SELLER, BUYER = 1, 2

COMMANDS: list[Command] = [
    Open(SELLER, cash=0, shares=5),
    Open(BUYER, cash=to_ticks("50.00"), shares=0),
    Submit(SELLER, Side.SELL, to_ticks("10.00"), 3),  # becomes order #3
    Submit(BUYER, Side.BUY, to_ticks("10.10"), 2),
    Cancel(SELLER, order_id=3),
]

LABELS = {
    Open: "open account",
    Submit: "submit order",
    Cancel: "cancel order",
    Advance: "advance clock",
}


def run(verbose: bool = True) -> Exchange:
    def show(command: Command, exchange: Exchange, events: list) -> None:
        if not verbose:
            return
        print(f"\n> {LABELS[type(command)]}: {command}")
        for event in events:
            print("  " + describe(event))
        if not isinstance(command, Open):
            print(book_text(exchange))
            print(accounts_text(exchange))

    exchange = run_script(COMMANDS, check_invariants=True, observer=show)

    trades = [e for e in exchange.events if isinstance(e, Trade)]
    seller, buyer = exchange.accounts[SELLER], exchange.accounts[BUYER]
    assert [(t.quantity, t.price) for t in trades] == [(2, 1000)], trades
    assert (buyer.cash, buyer.shares, buyer.reserved_cash) == (3000, 2, 0)
    assert (seller.cash, seller.shares, seller.reserved_shares) == (2000, 3, 0)
    assert buyer.cash + seller.cash == 5000 and buyer.shares + seller.shares == 5
    if verbose:
        print("\nAll expected values from the handoff match.")
    return exchange


if __name__ == "__main__":
    run()
