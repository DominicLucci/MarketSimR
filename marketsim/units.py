"""Units. The engine only ever sees integers: prices and cash in ticks, quantity in shares.

One tick is $0.01. Dollars appear only at the edges (parsing input, printing output).
"""

from __future__ import annotations

from decimal import Decimal

TICKS_PER_DOLLAR = 100


def to_ticks(dollars: str | int) -> int:
    """Parse a dollar amount exactly, e.g. to_ticks("10.10") == 1010."""
    ticks = Decimal(str(dollars)) * TICKS_PER_DOLLAR
    if ticks != ticks.to_integral_value():
        raise ValueError(f"{dollars!r} is not a whole number of ticks")
    return int(ticks)


def dollars(ticks: int | float) -> str:
    """Format ticks as dollars, e.g. dollars(1010) == "$10.10"."""
    sign = "-" if ticks < 0 else ""
    return f"{sign}${abs(ticks) / TICKS_PER_DOLLAR:,.2f}"
