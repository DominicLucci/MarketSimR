"""Everything random in a run, generated from the seed through separate streams.

Separate streams are what make runs comparable. Within one seed, changing the informed
share must not change the news the market receives, who arrives when, or the luck each
trader has. So each of those comes from its own stream:

    stream (0, 0)   which steps carry news
    stream (0, 1)   how large each piece of news is
    stream (1,)     which trader arrives at each step
    stream (2,)     the order in which traders become informed as the share grows
    stream (3, i)   trader i's own draws: one signal error and one inventory need per arrival

A trader's draws never depend on what the market did, so trader i's k-th arrival gets the
same luck in every run with the same seed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import SimConfig


def _rng(seed: int, *key: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence(seed, spawn_key=key))


def value_path(config: SimConfig) -> np.ndarray:
    """Underlying value at each step, in ticks. Always positive; path[0] is the initial value."""
    draws = _rng(config.seed, 0, 1).standard_normal(config.n_steps)
    if config.news_every > 0:  # scheduled news: fixed size, random direction
        is_news = np.arange(config.n_steps) % config.news_every == 0
        size = np.sign(draws) * config.news_sigma
    else:  # random news: random timing and size
        is_news = _rng(config.seed, 0, 0).random(config.n_steps) < config.news_prob
        size = draws * config.news_sigma
    is_news[0] = False  # the run starts at the initial value
    return config.initial_value * np.exp(np.cumsum(np.where(is_news, size, 0.0)))


def arrival_schedule(config: SimConfig) -> np.ndarray:
    """The trader who arrives at each step, drawn uniformly."""
    return _rng(config.seed, 1).integers(0, config.n_traders, size=config.n_steps)


def informed_traders(config: SimConfig) -> frozenset[int]:
    """Who is better informed. The sets are nested: raising the share adds traders to the
    informed group and never swaps anyone out."""
    ranking = _rng(config.seed, 2).permutation(config.n_traders)
    return frozenset(int(i) for i in ranking[: config.n_informed])


@dataclass(slots=True)
class TraderLuck:
    """One trader's private stream. Each arrival consumes exactly one draw of each kind."""

    rng: np.random.Generator

    def draw(self, max_need: int) -> tuple[float, int]:
        z = float(self.rng.standard_normal())  # signal error before scaling by the group's sigma
        u = float(self.rng.random())
        need = int(u * (2 * max_need + 1)) - max_need  # uniform on -max_need..max_need
        return z, need


def trader_luck(config: SimConfig, trader_id: int) -> TraderLuck:
    return TraderLuck(_rng(config.seed, 3, trader_id))
