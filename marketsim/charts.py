"""Charts for the informed-share experiment. Static PNGs; the CSVs beside them are the
table view of the same numbers."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE = "#fcfcfb"
TEXT, TEXT_SECONDARY, TEXT_MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE = "#2a78d6", "#eb6834"  # categorical slots 1 and 2, validated as a pair

PANELS = (
    ("price_error", "Price error", "mean |trade price − value|, $", 100.0),
    ("spread", "Quoted spread", "best offer − best bid, $", 100.0),
    ("volume", "Volume", "shares traded per run", 1.0),
)
VARIANT_STYLE = {
    "main": (BLUE, r"Main: signal error \$0.10 vs \$1.00"),
    "narrow_gap": (ORANGE, r"Narrow gap: \$0.50 vs \$1.00"),
}


def _style(ax: plt.Axes) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=TEXT_MUTED, labelsize=9, length=0)
    ax.set_xticks([0, 10, 25, 50, 75])
    ax.set_xticklabels(["0%", "10%", "25%", "50%", "75%"])
    ax.set_xlim(-6, 81)


def _titles(ax: plt.Axes, title: str, subtitle: str) -> None:
    ax.set_title(title, loc="left", color=TEXT, fontsize=11, fontweight="bold", pad=20)
    ax.text(0, 1.03, subtitle, transform=ax.transAxes, color=TEXT_SECONDARY, fontsize=9, va="bottom")


def _line(ax: plt.Axes, x, y, color: str, label: str | None = None, low=None, high=None) -> None:
    if low is not None:
        ax.vlines(x, low, high, color=color, linewidth=2, capstyle="round")
    ax.plot(
        x, y, color=color, linewidth=2, marker="o", markersize=7.5,
        markeredgecolor=SURFACE, markeredgewidth=1.6, solid_capstyle="round", label=label, zorder=3,
    )


def market_chart(runs: pd.DataFrame, paired: pd.DataFrame, path: str | Path) -> None:
    """Top row: every run and the mean, main variant. Bottom row: within-seed change from
    the 0% baseline with 95% intervals, for both precision gaps."""
    main = runs[runs["variant"] == "main"]
    n_seeds = main["seed"].nunique()
    seeds = sorted(main["seed"].unique())
    jitter = {seed: (i / max(len(seeds) - 1, 1) - 0.5) * 3.2 for i, seed in enumerate(seeds)}

    fig, axes = plt.subplots(2, 3, figsize=(12.5, 7.6), facecolor=SURFACE)
    for column, (measure, title, unit_label, unit) in enumerate(PANELS):
        top, bottom = axes[0, column], axes[1, column]

        _style(top)
        x = main["informed_share"] * 100 + main["seed"].map(jitter)
        top.scatter(x, main[measure] / unit, s=11, color=BLUE, alpha=0.22, linewidths=0, zorder=2)
        means = main.groupby("informed_share")[measure].mean() / unit
        _line(top, means.index * 100, means.values, BLUE)
        _titles(top, title, unit_label)

        _style(bottom)
        bottom.axhline(0, color=AXIS, linewidth=1)
        for offset, (variant, (color, label)) in zip((-0.9, 0.9), VARIANT_STYLE.items()):
            rows = paired[(paired["variant"] == variant) & (paired["measure"] == measure)].sort_values("informed_share")
            _line(
                bottom, rows["informed_share"] * 100 + offset, rows["mean_difference"] / unit, color, label,
                rows["ci_low"] / unit, rows["ci_high"] / unit,
            )
        unit_word = "shares" if unit == 1.0 else "$"
        _titles(bottom, f"{title}: change from 0% informed", f"within-seed difference in {unit_word}, mean and 95% interval")
        bottom.set_xlabel("share of better-informed traders", color=TEXT_SECONDARY, fontsize=9)

    axes[1, 2].legend(frameon=False, fontsize=9, labelcolor=TEXT_SECONDARY, loc="lower left", handlelength=1.6)
    fig.suptitle(
        "How the share of better-informed traders changes the market",
        x=0.012, y=0.988, ha="left", color=TEXT, fontsize=14, fontweight="bold",
    )
    fig.text(
        0.012, 0.95,
        f"{n_seeds} seeds per setting; within a seed every setting shares one value path, arrival schedule and trader luck.\n"
        "Top row: main variant, each dot is one run and the line is the mean. Bottom row: both signal-precision gaps.",
        color=TEXT_SECONDARY, fontsize=10, va="top", linespacing=1.4,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9), h_pad=2.2, w_pad=2.0)
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def outcomes_chart(runs: pd.DataFrame, levels: pd.DataFrame, path: str | Path) -> None:
    """Mean trading gain per trader in each group, main variant."""
    main = levels[levels["variant"] == "main"]
    n_seeds = runs[runs["variant"] == "main"]["seed"].nunique()
    fig, ax = plt.subplots(figsize=(7.4, 4.8), facecolor=SURFACE)
    _style(ax)
    ax.axhline(0, color=AXIS, linewidth=1)
    series = (("trading_gain_informed", BLUE, "Better informed"), ("trading_gain_uninformed", ORANGE, "Others"))
    for offset, (measure, color, label) in zip((-0.7, 0.7), series):
        rows = main[(main["measure"] == measure) & main["mean"].notna()].sort_values("informed_share")
        x = rows["informed_share"] * 100 + offset
        low = rows["ci_low"].fillna(rows["mean"]) / 100
        high = rows["ci_high"].fillna(rows["mean"]) / 100
        _line(ax, x, rows["mean"] / 100, color, label, low, high)
        ax.annotate(
            label, (x.iloc[-1], rows["mean"].iloc[-1] / 100), xytext=(8, 0), textcoords="offset points",
            color=TEXT_SECONDARY, fontsize=9, va="center",
        )
    ax.set_xlim(-6, 95)
    ax.yaxis.set_major_formatter(lambda value, _: f"${value:,.0f}" if value >= 0 else f"−${-value:,.0f}")
    ax.set_xlabel("share of better-informed traders", color=TEXT_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=9, labelcolor=TEXT_SECONDARY, loc="upper right")
    ax.set_title("Trading gain per trader, by group", loc="left", color=TEXT, fontsize=12, fontweight="bold", pad=34)
    ax.text(
        0, 1.03,
        f"final wealth minus the same trader's wealth had it never traded; mean and 95% interval over {n_seeds} seeds\n"
        "no better-informed traders exist at 0%, so that point is absent",
        transform=ax.transAxes, color=TEXT_SECONDARY, fontsize=9, va="bottom",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)
