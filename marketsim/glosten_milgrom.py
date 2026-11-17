"""A theory benchmark: the Glosten and Milgrom (1985) market, run on this project's exchange.

    python -m marketsim.glosten_milgrom            # writes results/glosten_milgrom
    python -m marketsim.glosten_milgrom --check    # regenerates and compares

The setting has a closed form, so the simulation can be checked against it:

* The value is V_HIGH or V_LOW with equal chance and never changes within a run.
* One trader arrives per step and trades one share. With chance mu it is informed and buys
  if the value is high, sells if low. Otherwise it buys or sells with equal chance.
* A competitive dealer quotes one share each side: ask = E[V | next trader buys], bid =
  E[V | next trader sells], given everything traded so far. After each trade it updates its
  belief by Bayes' rule.

Here the dealer is an ordinary account on the exchange posting limit orders, and each
arriving trader sends a limit order at the dealer's price, so every trade goes through the
same order entry, matching and settlement as the main model. Prices are whole ticks: the
dealer rounds its ask up and its bid down, and keeps them at least one tick apart.

The exact expected quoted spread and dealer profit at every step are computed separately,
without the exchange, by summing over how many buys and sells could have happened
(`exact_path`). Rounding is included in both, so in expectation they must agree exactly;
the simulated mean differs only by sampling error. With no rounding the dealer would break
even on every trade in expectation; rounding outward gives it a small, computable profit.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict, dataclass
from math import ceil, comb, floor
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from .events import Side, Trade
from .exchange import Exchange
from .metrics import IMPACT_HORIZON, spread_decomposition
from .parallel import pmap

OUT = "results/glosten_milgrom"
MUS = (0.10, 0.25, 0.50)


@dataclass(frozen=True)
class GMConfig:
    mu: float = 0.25  # chance an arriving trader is informed
    v_low: int = 9_900  # ticks
    v_high: int = 10_100
    n_steps: int = 60
    seed: int = 0


def belief_after(net_buys: int, mu: float) -> float:
    """P(V high) after a history with `net_buys` more buys than sells, from a prior of 1/2.

    Each buy multiplies the odds by (1 + mu) / (1 - mu) and each sell divides them by it,
    so only the difference matters."""
    ratio = (1 - mu) / (1 + mu)
    return 1.0 / (1.0 + ratio**net_buys)


def quotes(belief: float, config: GMConfig) -> tuple[int, int]:
    """The dealer's (bid, ask) in whole ticks at a given belief that the value is high."""
    mu, gap = config.mu, config.v_high - config.v_low
    p_buy_high, p_buy_low = (1 + mu) / 2, (1 - mu) / 2
    high_given_buy = belief * p_buy_high / (belief * p_buy_high + (1 - belief) * p_buy_low)
    high_given_sell = belief * p_buy_low / (belief * p_buy_low + (1 - belief) * p_buy_high)
    ask = config.v_low + gap * high_given_buy
    bid = config.v_low + gap * high_given_sell
    # Round to 9 decimals first so a value that is a whole tick in exact arithmetic is not
    # pushed to the next tick by floating-point error.
    bid, ask = floor(round(bid, 9)), ceil(round(ask, 9))
    # Once the dealer is nearly certain both can round to the same tick; its own bid would
    # then cross its own offer. Keep them one tick apart (in the formulas as well).
    return min(bid, ask - 1), ask


def exact_path(config: GMConfig) -> pd.DataFrame:
    """Expected quoted spread and dealer profit per trade at each step, from the formulas.

    At step t, after t trades, the number of buys among them is binomial with chance
    (1 + mu) / 2 if the value is high and (1 - mu) / 2 if low."""
    mu = config.mu
    rows = []
    for t in range(config.n_steps):
        spread = profit = 0.0
        for value, p_buy in ((config.v_high, (1 + mu) / 2), (config.v_low, (1 - mu) / 2)):
            for buys in range(t + 1):
                weight = 0.5 * comb(t, buys) * p_buy**buys * (1 - p_buy) ** (t - buys)
                bid, ask = quotes(belief_after(2 * buys - t, mu), config)
                spread += weight * (ask - bid)
                profit += weight * (p_buy * (ask - value) + (1 - p_buy) * (value - bid))
        rows.append({"step": t, "exact_spread": spread, "exact_dealer_profit": profit})
    return pd.DataFrame(rows)


DEALER = 0


def simulate_run(config: GMConfig) -> tuple[pd.DataFrame, SimpleNamespace]:
    """One run on the exchange.

    Returns one row per step (quotes before the trade, the trade, and the dealer's profit
    on it valued at the true value), and the run in the form the main model's measures read:
    the event log, the quotes each arriving trader saw, and the mid-quote at the end of each
    step. As in the theory, the dealer requotes as soon as a trade has updated its belief,
    so the book is two-sided at the end of every step."""
    rng = np.random.default_rng(config.seed)
    value = config.v_high if rng.random() < 0.5 else config.v_low
    exchange = Exchange()
    exchange.open_account(DEALER, 10**9, 10**6)
    n_traders = 8  # arrivals rotate through a few funded accounts
    for trader in range(1, n_traders + 1):
        exchange.open_account(trader, 10**9, 10**6)

    def requote(net_buys: int) -> None:
        for order in exchange.open_orders(DEALER):
            exchange.cancel(DEALER, order.order_id)
        bid, ask = quotes(belief_after(net_buys, config.mu), config)
        exchange.submit_limit(DEALER, Side.BUY, bid, 1)
        exchange.submit_limit(DEALER, Side.SELL, ask, 1)

    net_buys, rows, seen_quotes = 0, [], []
    mid_path = np.full(config.n_steps, np.nan)
    exchange.advance_to(0)
    requote(net_buys)
    for t in range(config.n_steps):
        exchange.advance_to(t)
        seen = exchange.quotes()
        bid, ask = seen.best_bid, seen.best_ask

        informed = rng.random() < config.mu
        coin = rng.random() < 0.5
        buys = (value == config.v_high) if informed else coin
        trader = 1 + t % n_traders
        before = len(exchange.events)
        exchange.submit_limit(trader, Side.BUY if buys else Side.SELL, ask if buys else bid, 1)
        trades = [e for e in exchange.events[before:] if isinstance(e, Trade)]
        if len(trades) != 1 or trades[0].quantity != 1:
            raise RuntimeError(f"step {t}: expected exactly one one-share trade with the dealer")
        price = trades[0].price
        net_buys += 1 if buys else -1
        requote(net_buys)
        mid_path[t] = exchange.quotes().mid
        seen_quotes.append({"best_bid": bid, "best_ask": ask})
        rows.append(
            {
                "seed": config.seed, "step": t, "value": value, "bid": bid, "ask": ask,
                "spread": seen.spread, "mid": seen.mid, "trade_price": price, "buy": buys,
                "dealer_profit": (price - value) if buys else (value - price),
            }
        )
    run = SimpleNamespace(events=exchange.events, decisions=seen_quotes, mid_path=mid_path)
    return pd.DataFrame(rows), run


def simulate(config: GMConfig) -> pd.DataFrame:
    """One run on the exchange, one row per step (see simulate_run)."""
    return simulate_run(config)[0]


DECOMPOSITION = ("effective_spread", "price_impact", "impact_immediate", "impact_later", "realized_spread")


def exact_decomposition(config: GMConfig) -> pd.DataFrame:
    """Expected effective spread, price impact (own step and after) and realized spread of
    the trade at each step, exactly as metrics.spread_decomposition measures them: m0 is
    the mid-quote the trader saw, ma the mid-quote at the end of its step, m1 the mid-quote
    IMPACT_HORIZON steps later. Only steps with a later mid-quote are included, as there.

    Before step t the net buys n are 2 x buys - t with buys binomial; the trade moves them
    to n + d; the IMPACT_HORIZON trades after it add 2k - IMPACT_HORIZON, k binomial again.
    Summed exactly over both values, so rounding and the dealer's one-tick floor are in."""
    mu, horizon = config.mu, IMPACT_HORIZON
    mids: dict[int, float] = {}

    def mid(n: int) -> float:
        if n not in mids:
            bid, ask = quotes(belief_after(n, mu), config)
            mids[n] = (bid + ask) / 2
        return mids[n]

    rows = []
    for t in range(config.n_steps - horizon):
        effective = immediate = later = 0.0
        for p_buy in ((1 + mu) / 2, (1 - mu) / 2):  # value high, value low
            future = [comb(horizon, k) * p_buy**k * (1 - p_buy) ** (horizon - k) for k in range(horizon + 1)]
            for buys in range(t + 1):
                weight = 0.5 * comb(t, buys) * p_buy**buys * (1 - p_buy) ** (t - buys)
                n = 2 * buys - t
                bid, ask = quotes(belief_after(n, mu), config)
                m0 = (bid + ask) / 2
                for d, p_d, price in ((1, p_buy, ask), (-1, 1 - p_buy, bid)):
                    m_after = mid(n + d)
                    m_later = sum(f * mid(n + d + 2 * k - horizon) for k, f in enumerate(future))
                    effective += weight * p_d * 2 * d * (price - m0)
                    immediate += weight * p_d * 2 * d * (m_after - m0)
                    later += weight * p_d * 2 * d * (m_later - m_after)
        impact = immediate + later
        rows.append({"step": t, "effective_spread": effective, "price_impact": impact, "impact_immediate": immediate,
                     "impact_later": later, "realized_spread": effective - impact})
    return pd.DataFrame(rows)


def _one_seed(config: GMConfig) -> tuple[pd.DataFrame, dict]:
    rows, run = simulate_run(config)
    return rows, spread_decomposition(run)


def run_benchmark(n_seeds: int, mus: tuple[float, ...] = MUS, n_steps: int = 60) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """For each mu: the mean over seeds at each step beside the exact value, and the main
    model's spread decomposition averaged over seeds beside its exact expectation."""
    tables, decompositions, summary = [], [], {}
    for mu in mus:
        results = pmap(_one_seed, [GMConfig(mu=mu, n_steps=n_steps, seed=s) for s in range(n_seeds)])
        runs = pd.concat([rows for rows, _ in results], ignore_index=True)
        runs["abs_mid_error"] = (runs["mid"] - runs["value"]).abs()
        by_step = runs.groupby("step").agg(
            sim_spread=("spread", "mean"), sim_spread_se=("spread", lambda x: x.std(ddof=1) / np.sqrt(len(x))),
            sim_dealer_profit=("dealer_profit", "mean"),
            sim_dealer_profit_se=("dealer_profit", lambda x: x.std(ddof=1) / np.sqrt(len(x))),
            sim_abs_mid_error=("abs_mid_error", "mean"),
        ).reset_index()
        table = exact_path(GMConfig(mu=mu, n_steps=n_steps)).merge(by_step, on="step")
        table.insert(0, "mu", mu)
        tables.append(table)
        # One comparison per mu that respects the correlation between steps of a run: average
        # each seed over all steps, then compare the mean across seeds with the exact average.
        per_seed = runs.groupby("seed")[["spread", "dealer_profit"]].mean()
        pooled = {}
        for name, column, exact in (("spread", "spread", "exact_spread"), ("dealer_profit", "dealer_profit", "exact_dealer_profit")):
            pooled[name] = _compare(per_seed[column], float(table[exact].mean()))
        # The main model's measurement code on the same runs: each run's average over its
        # trades, against the exact expectation of that average.
        measured = pd.DataFrame([decomposition for _, decomposition in results])
        exact = exact_decomposition(GMConfig(mu=mu, n_steps=n_steps))
        if not (measured["n_trades_decomposed"] == len(exact)).all():
            raise RuntimeError("every run should decompose the same trades as the exact calculation")
        for measure in DECOMPOSITION:
            decompositions.append({"mu": mu, "measure": measure, **_compare(measured[measure], float(exact[measure].mean()))})
        config = GMConfig(mu=mu)
        summary[str(mu)] = {
            "first_spread_formula": mu * (config.v_high - config.v_low),
            "first_spread_quoted": float(table.loc[0, "sim_spread"]),
            "mean_spread_over_steps": pooled["spread"],
            "dealer_profit_per_trade": pooled["dealer_profit"],
            "abs_mid_error_first_step": float(table.loc[0, "sim_abs_mid_error"]),
            "abs_mid_error_last_step": float(table.iloc[-1]["sim_abs_mid_error"]),
        }
    meta = {
        "command": f"python -m marketsim.glosten_milgrom --seeds {n_seeds}",
        "settings": {**asdict(GMConfig()), "mu": list(mus), "n_steps": n_steps, "seeds": n_seeds,
                     "impact_horizon": IMPACT_HORIZON},
        "by_mu": summary,
    }
    return pd.concat(tables, ignore_index=True), pd.DataFrame(decompositions), meta


def _compare(per_seed: pd.Series, exact: float) -> dict[str, float]:
    """Mean across seeds against an exact value, with the standard error across seeds."""
    se = float(per_seed.std(ddof=1) / np.sqrt(len(per_seed)))
    difference = float(per_seed.mean() - exact)
    return {"sim": float(per_seed.mean()), "exact": exact, "difference": difference, "se": se,
            "z": difference / se if se > 0 else float("nan")}


def chart(table: pd.DataFrame, path: str | Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from .charts import AXIS, GRID, SURFACE, TEXT, TEXT_MUTED, TEXT_SECONDARY

    colors = {0.10: "#86b6ef", 0.25: "#2a78d6", 0.50: "#0d366b"}
    fig, ax = plt.subplots(figsize=(8.5, 5.0), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=TEXT_MUTED, labelsize=9, length=0)
    for mu, group in table.groupby("mu"):
        color = colors.get(round(mu, 2), "#2a78d6")
        ax.plot(group["step"], group["exact_spread"] / 100, color=color, linewidth=2, label=f"{mu:.0%} of traders informed")
        ax.plot(group["step"], group["sim_spread"] / 100, "o", color=color, markersize=3.5, alpha=0.8)
    ax.yaxis.set_major_formatter(lambda v, _: f"${v:.2f}")
    ax.set_xlabel("trades so far", color=TEXT_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=9, labelcolor=TEXT_SECONDARY)
    fig.suptitle("Glosten–Milgrom benchmark: expected quoted spread", x=0.02, ha="left", color=TEXT, fontsize=13,
                 fontweight="bold")
    fig.text(0.02, 0.905, "Lines: exact expectation from the formulas. Dots: mean over seeds of the dealer's quotes "
             "on the exchange. Value \\$99 or \\$101.", color=TEXT_SECONDARY, fontsize=9, va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def write(out: str | Path, n_seeds: int, with_chart: bool = True) -> Path:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    table, decomposition, meta = run_benchmark(n_seeds)
    table.to_csv(out / "spread_by_step.csv", index=False)
    decomposition.to_csv(out / "decomposition.csv", index=False)
    (out / "summary.json").write_text(json.dumps(meta, indent=2) + "\n")
    if with_chart:
        chart(table, out / "spread_by_step.png")
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Glosten-Milgrom benchmark on the exchange.")
    parser.add_argument("--seeds", type=int, default=10_000)
    parser.add_argument("--out", default=OUT)
    parser.add_argument("--check", action="store_true", help="regenerate and compare with the saved results")
    args = parser.parse_args(argv)
    if args.check:
        saved = json.loads((Path(args.out) / "summary.json").read_text())
        with tempfile.TemporaryDirectory() as scratch:
            fresh = write(scratch, saved["settings"]["seeds"], with_chart=False)
            for name in ("spread_by_step.csv", "decomposition.csv"):
                pd.testing.assert_frame_equal(pd.read_csv(Path(args.out) / name),
                                              pd.read_csv(fresh / name), check_exact=False, rtol=1e-9, atol=1e-9)
        print(f"saved results in {args.out}/ match a fresh run")
        return
    out = write(args.out, args.seeds)
    meta = json.loads((out / "summary.json").read_text())
    print("all in ticks; z = (simulated - exact) / standard error across seeds")
    print("mu    first spread: formula quoted | mean spread: sim  exact    z | dealer profit/trade: sim  exact    z")
    for mu, s in meta["by_mu"].items():
        sp, pr = s["mean_spread_over_steps"], s["dealer_profit_per_trade"]
        print(f"{float(mu):<5} {s['first_spread_formula']:>20.1f} {s['first_spread_quoted']:>6.1f} |"
              f" {sp['sim']:>16.3f} {sp['exact']:>6.3f} {sp['z']:>+5.2f} |"
              f" {pr['sim']:>24.3f} {pr['exact']:>6.3f} {pr['z']:>+5.2f}")
    decomposition = pd.read_csv(out / "decomposition.csv")
    print("\nthe main model's spread decomposition on these runs: simulated, exact, z")
    for mu, group in decomposition.groupby("mu"):
        cells = "  ".join(f"{r.measure} {r.sim:6.2f} {r.exact:6.2f} {r.z:+5.2f}" for r in group.itertuples())
        print(f"{mu:<5} {cells}")
    print(f"\nwrote {out}/")


if __name__ == "__main__":
    main()
