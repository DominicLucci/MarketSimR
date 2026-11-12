"""Simulation settings. One frozen record fully describes a run, together with the model
version, so saving it is enough to reproduce the run."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from typing import Any

# Bump when a rule changes in a way that changes results for the same config and seed.
MODEL_VERSION = "0.2.0-pilot"


@dataclass(frozen=True, slots=True)
class SimConfig:
    seed: int = 0

    # Population. Both groups get the same endowment, arrival process and decision rule.
    n_traders: int = 40
    informed_share: float = 0.25
    initial_cash: int = 100_000  # ticks ($1,000.00)
    initial_shares: int = 10

    # Horizon. One trader arrives per step.
    n_steps: int = 4_000

    # Underlying value: starts at initial_value; on each step it jumps with probability
    # news_prob by a log-normal factor with standard deviation news_sigma.
    initial_value: float = 10_000.0  # ticks ($100.00)
    news_prob: float = 0.02
    news_sigma: float = 0.005
    # Designed-news option. If positive, news arrives every `news_every` steps instead of at
    # random, and each jump has log size exactly news_sigma in a random direction.
    news_every: int = 0
    # Quote-refresh option. If True, every resting order is cancelled on a step where the
    # value changes: traders know that news arrived (not what it was) and pull their quotes.
    cancel_on_news: bool = False

    # Private signal = value + error; the error's standard deviation depends on the group.
    sigma_informed: float = 10.0  # ticks
    sigma_uninformed: float = 100.0  # ticks

    # Decision rule.
    margin: float = 20.0  # ticks kept between a trader's estimate and its limit price
    max_need: int = 5  # inventory target = initial_shares + need, need in [-max_need, max_need]
    max_order_size: int = 5
    order_lifetime: int = 80  # steps before a resting order expires

    # Measurement.
    quote_sample_every: int = 10

    def __post_init__(self) -> None:
        if self.n_traders < 2 or self.n_steps < 1:
            raise ValueError("need at least two traders and one step")
        if not 0.0 <= self.informed_share <= 1.0:
            raise ValueError("informed_share must be between 0 and 1")
        exact = self.informed_share * self.n_traders
        if abs(exact - round(exact)) > 1e-9:
            raise ValueError(
                f"informed_share {self.informed_share} of {self.n_traders} traders "
                "is not a whole number of traders"
            )
        if min(self.sigma_informed, self.sigma_uninformed, self.margin, self.news_sigma) < 0:
            raise ValueError("standard deviations and margin cannot be negative")
        if not 0.0 <= self.news_prob <= 1.0:
            raise ValueError("news_prob must be between 0 and 1")
        if type(self.news_every) is not int or self.news_every < 0:
            raise ValueError("news_every must be 0 (random news) or a positive whole number of steps")
        if self.initial_value <= 0 or self.initial_cash < 0 or self.initial_shares < 0:
            raise ValueError("initial value must be positive and endowments non-negative")
        if min(self.max_order_size, self.order_lifetime, self.quote_sample_every) < 1 or self.max_need < 0:
            raise ValueError("order size, lifetime and sampling interval must be at least 1")

    @property
    def n_informed(self) -> int:
        return round(self.informed_share * self.n_traders)

    def with_(self, **changes: Any) -> "SimConfig":
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimConfig":
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown settings: {sorted(unknown)}")
        return cls(**data)
