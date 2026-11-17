"""The decision rule, shared by every trader.

The rule is a pure function of what one trader can observe. It receives no group label and
never sees the underlying value, so two traders with the same view always act the same way.

Baseline rule (provisional, see docs/model_rules.md section 7):

* Inventory sets the side and the size. Below target, buy; above target, sell; at target,
  do nothing. Size is the gap to target, capped by max_order_size and by what the account
  can fund.
* The estimate sets the price. A buyer bids its estimate minus the margin, rounded down. A
  seller offers its estimate plus the margin, rounded up.
* With urgency on (urgency_scale > 0), the margin shrinks with distance from target:
  urgency = min(1, |gap| / urgency_scale) and margin x (1 - 2 x urgency), from the full
  margin at target to minus the margin (paying up to the margin beyond the estimate) when
  the gap is urgency_scale shares or more. Two traders with the same estimate then trade
  exactly when their urgencies add up to at least one.
* Traders in this baseline do not use the public quotes to revise their estimate. With
  the learn_from_prices option they replace the signal by a weighted average of the
  signal and the mid-quote, leaning on the price more when their own signal is noisier.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

from .events import Side
from .exchange import Quotes


@dataclass(frozen=True, slots=True)
class TraderView:
    """Everything a trader is allowed to see when it acts."""

    time: int
    signal: float  # private estimate of the value, in ticks
    signal_sd: float  # how noisy this trader knows its own signal to be, in ticks
    target_shares: int  # this arrival's inventory target (private)
    cash: int
    shares: int
    available_cash: int
    available_shares: int
    quotes: Quotes  # public top of book


@dataclass(frozen=True, slots=True)
class Intent:
    side: Side
    price: int
    quantity: int


def estimate_value(view: TraderView, price_sd: float | None = None) -> float:
    """The trader's estimate of the value. `price_sd` None means prices are ignored."""
    mid = view.quotes.mid
    if price_sd is None or mid is None:
        return view.signal
    weight_on_price = view.signal_sd**2 / (view.signal_sd**2 + price_sd**2)
    return (1 - weight_on_price) * view.signal + weight_on_price * mid


def effective_margin(margin: float, gap: int, urgency_scale: int = 0) -> float:
    """The margin a trader keeps, in ticks. Fixed when urgency_scale is 0; otherwise it
    falls linearly from +margin at the target to -margin at urgency_scale shares away."""
    if urgency_scale <= 0:
        return margin
    urgency = min(1.0, abs(gap) / urgency_scale)
    return margin * (1.0 - 2.0 * urgency)


def decide(
    view: TraderView, margin: float, max_order_size: int, price_sd: float | None = None, urgency_scale: int = 0
) -> tuple[Intent | None, str]:
    """Return the order to send (or None) and a short reason, for the decision trace."""
    estimate = estimate_value(view, price_sd)
    gap = view.target_shares - view.shares
    if gap == 0:
        return None, "at target"
    margin = effective_margin(margin, gap, urgency_scale)

    if gap > 0:
        price = floor(estimate - margin)
        if price < 1:
            return None, "bid would be below one tick"
        quantity = min(gap, max_order_size, view.available_cash // price)
        if quantity < 1:
            return None, "cannot afford one share at its bid"
        return Intent(Side.BUY, price, quantity), "below target"

    price = max(1, ceil(estimate + margin))
    quantity = min(-gap, max_order_size, view.available_shares)
    if quantity < 1:
        return None, "no shares available to sell"
    return Intent(Side.SELL, price, quantity), "above target"
