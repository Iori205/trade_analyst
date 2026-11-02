"""Baseline strategies for engine v1, run on the TRAIN split, plus their report.

  a) random        H1, random side, about one trade per day, 4-hour hold; 100 seeded runs
  b) ma_crossover  H1, SMA(20) vs SMA(50) of closes, always in the market, reverses on a cross
  c) monday_13     H1, long Monday 13:00 UTC, exit 14:00 UTC. Taken from the exploratory
                   train result (reports/exploratory_stats_20261102T084201Z), so on train it is
                   in-sample by construction; only validation can test it.

Run:
    .venv/bin/python -m src.backtest.baselines
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.engine import History, Strategy, load_context, run_backtest

RANDOM_RUNS = 100
RANDOM_SEED = 20261102
RANDOM_P_ENTRY = 1 / 16      # per flat H1 bar; gives about one trade per weekday (realised rate is reported)
RANDOM_HOLD = 4


def random_strategy(seed: int, p_entry: float = RANDOM_P_ENTRY, hold: int = RANDOM_HOLD) -> Strategy:
    rng = np.random.default_rng(seed)

    def signal(h: History):
        if h.position:
            return None
        if rng.random() < p_entry:
            return 1 if rng.random() < 0.5 else -1
        return None
    return Strategy("random", signal, {"seed": seed, "p_entry": p_entry}, hold_bars=hold, exit_on_signal=False)


def ma_crossover(fast: int = 20, slow: int = 50) -> Strategy:
    def signal(h: History):
        if len(h.close) < slow:
            return None
        f, s = h.close[-fast:].mean(), h.close[-slow:].mean()
        return 1 if f > s else -1 if f < s else None
    return Strategy("ma_crossover", signal, {"fast": fast, "slow": slow, "price": "close", "ma": "simple"},
                    hold_bars=None, exit_on_signal=True)


def monday_13() -> Strategy:
    def signal(h: History):
        t = pd.Timestamp(h.time[-1])
        # the bar starting Mon 12:00 closes at 13:00, so the entry fills at the open of the Mon 13:00 bar
        return 1 if h.position == 0 and t.dayofweek == 0 and t.hour == 12 else None
    return Strategy("monday_13_long", signal, {"weekday": "Mon", "entry_utc": "13:00", "exit_utc": "14:00",
                                               "source": "exploratory_stats_20261102T084201Z (train, in-sample)"},
                    hold_bars=1, exit_on_signal=False)


# ---------------------------------------------------------------------------
# Charts (static PNG, light surface; dataviz reference palette)
# ---------------------------------------------------------------------------
INK2, MUTED, BASE, GRID, SURFACE = "#52514e", "#898781", "#c3c2b7", "#e1e0d9", "#fcfcfb"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": BASE,
                         "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED, "font.size": 9,
                         "axes.titlesize": 10, "axes.titleweight": "bold", "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.dpi": 150})
    return plt


def _save(fig, path: Path) -> None:
    with open(path, "xb") as handle:
        fig.savefig(handle, format="png", bbox_inches="tight", metadata={"Software": None})


def chart_random(dist: pd.DataFrame, marks: dict, path: Path) -> None:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.hist(dist["expectancy_pips"], bins=20, color="#9ec5f4", edgecolor=SURFACE)
    ax.axvline(-dist["mean_cost_pips"].mean(), color=INK2, lw=1.5, ls="--")
    ax.text(-dist["mean_cost_pips"].mean(), ax.get_ylim()[1] * 0.95, " −mean cost", color=INK2, va="top", fontsize=8)
    for (name, value), color in zip(marks.items(), (ORANGE, AQUA)):
        ax.axvline(value, color=color, lw=2)
        ax.text(value, ax.get_ylim()[1] * 0.8, f" {name}", color=INK2, va="top", fontsize=8)
    ax.set_xlabel("expectancy per trade after costs (pips)")
    ax.set_ylabel("random runs")
    ax.set_title(f"Random baseline: {len(dist)} seeded runs, H1, 4h hold (train 2015-2021)", loc="left")
    _save(fig, path)
    plt.close(fig)


def chart_equity(results: dict, path: Path) -> None:
    plt = _plt()
    fig, axes = plt.subplots(len(results), 1, figsize=(8, 2.6 * len(results)), sharex=True)
    for ax, (name, r), color in zip(np.atleast_1d(axes), results.items(), (BLUE, ORANGE)):
        t = r["trades"]
        ax.plot(t["exit_time"], t["net_pips"].cumsum(), color=color, lw=2, label="after costs")
        ax.plot(t["exit_time"], t["gross_pips"].cumsum(), color=MUTED, lw=1, label="before costs")
        ax.axhline(0, color=BASE, lw=0.8)
        ax.set_ylabel("cumulative pips")
        ax.set_title(name, loc="left")
        ax.legend(frameon=False, loc="upper left")
    _save(fig, path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def fmt(v) -> str:
    if isinstance(v, (float, np.floating)):
        return "–" if np.isnan(v) else f"{v:,.3f}" if abs(v) < 100 else f"{v:,.0f}"
    return str(v)


def md_table(df: pd.DataFrame) -> str:
    head = "| " + " | ".join(map(str, df.columns)) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "\n".join("| " + " | ".join(fmt(v) for v in r) + " |" for r in df.itertuples(index=False))


METRIC_ROWS = ["trades", "win_rate", "avg_win_pips", "avg_loss_pips", "expectancy_pips", "total_pips",
               "max_drawdown_pips", "sharpe_daily", "t_stat", "mean_cost_pips"]


def render_summary(dist: pd.DataFrame, results: dict, info: dict) -> str:
    q = dist["expectancy_pips"].quantile([0.05, 0.5, 0.95])
    metric_table = pd.DataFrame({"metric": METRIC_ROWS,
                                 "random (median of 100)": [dist[m].median() for m in METRIC_ROWS],
                                 **{name: [r["metrics"][m] for m in METRIC_ROWS] for name, r in results.items()}})
    lines = [
        "# Backtest baselines (engine v1), train split 2015-2021",
        "",
        f"Generated {info['created_utc']} by `src/backtest/baselines.py` (HEAD `{(info['git_commit'] or '')[:7]}`, "
        f"uncommitted script changes: {str(info['git_dirty']).lower()}). Data: `{info['data']}` "
        f"(SHA-256 `{info['data_sha256'][:16]}…`). Only the train split was read.",
        "",
        "## Engine rules",
        "",
        "- **Timing:** a signal sees bars up to and including the bar that just closed. Fills happen at the **next bar's open**.",
        "- **Position:** one at a time, 1 lot, long or short. Exit is by a time limit or by the signal.",
        "- **Entries are skipped when the entry bar:**",
        "  - is not directly after the signal bar (weekend or data gap),",
        "  - has `any_gap` or `any_flag`,",
        "  - or `cost_for` marks it as rollover, weekly open or market closed.",
        "- **Exits:** never blocked.",
        f"- **Cost:** `cost_for(entry_time)` once per round trip, spread at {info['percentile']} + 0.6 commission + 0.2 slippage. The commission and slippage are broker assumptions.",
        "- **Prices:** HistData bid; P&L in pips, 1 lot ≈ 10 USD per pip.",
        f"- **Trial log:** every run is appended to `reports/trials/trials.csv`. This report added {info['trials_logged']} rows (100 random + 2).",
        "",
        "## Results (after costs)",
        "",
        md_table(metric_table),
        "",
        "## a) Random baseline",
        "",
        f"- **Setup:** {RANDOM_RUNS} runs, seeds {RANDOM_SEED}..{RANDOM_SEED + RANDOM_RUNS - 1}, entry probability {RANDOM_P_ENTRY:.4f} per flat H1 bar, hold {RANDOM_HOLD} h.",
        f"- **Activity:** about {dist['trades'].median() / info['weekdays']:.2f} trades per weekday.",
        f"- **Expectancy distribution:** p5 {q[0.05]:.3f}, median {q[0.5]:.3f}, p95 {q[0.95]:.3f} pips per trade.",
        f"- **Cost:** mean cost {dist['mean_cost_pips'].mean():.3f} pips. Mean gross per trade {dist['gross_expectancy_pips'].mean():.3f} pips, i.e. about 0, as it should be.",
        "- **Conclusion:** random entries lose roughly the cost on every trade. Any strategy has to clear this distribution, not zero.",
        "",
        "Chart: `charts/random_expectancy.png`. Every run is in `random_runs.csv`.",
        "",
    ]
    for key, title, note in (
        ("ma_crossover", "b) MA crossover 20/50 (H1)",
         "Always in the market and reverses on a cross. When the entry bar is blocked, the strategy waits flat for the next allowed bar."),
        ("monday_13_long", "c) Monday 13:00 UTC long, exit 14:00",
         "**Not truly pre-registered:** it comes from the exploratory analysis of the same train data (mean Mon 13 +2.7 pips, q = 0.017). The train result below is therefore in-sample and biased upward by selection. Validation 2022-2023 is the real test, and it should be run once with these parameters fixed."),
    ):
        r = results[key]
        beaten = int((dist["expectancy_pips"] < r["metrics"]["expectancy_pips"]).sum())
        y = r["yearly"].set_index("year")["net_pips"]
        total = r["metrics"]["total_pips"]
        note += (f" Best year {int(y.idxmax())}: {y.max():,.0f} pips"
                 f"{f', {y.max() / total * 100:.0f}% of the {total:,.0f} total' if total > 0 else ''}. "
                 f"Total without that year: {total - y.max():,.0f} pips.")
        lines += [f"## {title}", "", note, "",
                  f"Expectancy {r['metrics']['expectancy_pips']:.3f} pips per trade, t = {r['metrics']['t_stat']:.2f}. "
                  f"Higher than {beaten} of the {len(dist)} random runs.", "",
                  "By year (exit year):", "", md_table(r["yearly"]), "",
                  "Exit reasons: " + ", ".join(f"{k} {v}" for k, v in r["trades"]["exit_reason"].value_counts().items()) + ".", ""]
    lines += [
        "Equity curves: `charts/equity.png`. Trade lists, with pips only and no price levels: `trades_ma_crossover.csv` and `trades_monday_13_long.csv`.",
        "",
        "## Limitations",
        "",
        "- **Cost model:** the spread is FXCM's, from 10 sample weeks. Commission and slippage are assumptions.",
        "- **Exit cost:** cost is charged at entry only. An exit in a wide-spread period (e.g. rollover) costs more in reality.",
        "- **Prices:** bid prices only. A short's exit in reality is at the ask; the round-trip spread in the cost stands in for that.",
        "- **Execution:** fills are exact at the bar open, with no partial fills and no swap or financing charges.",
        f"- **Trial count:** {info['trials_total']} rows are now in the trial log. Any later selection among strategies must account for every trial in it.",
    ]
    return "\n".join(lines) + "\n"


def run(root: Path = Path("."), reports_dir: Path = Path("reports"), stamp: str | None = None) -> dict:
    root = Path(root)
    stamp = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = root / reports_dir / f"backtest_baselines_{stamp}"
    if out.exists():
        raise FileExistsError(f"{out} exists")
    ctx = load_context(root)
    rows = []
    for k in range(RANDOM_RUNS):
        r = run_backtest(ctx, random_strategy(RANDOM_SEED + k), "H1")
        rows.append({"seed": RANDOM_SEED + k, **r["metrics"], "gross_expectancy_pips": float(r["trades"]["gross_pips"].mean())})
    dist = pd.DataFrame(rows)
    results = {s.name: run_backtest(ctx, s, "H1") for s in (ma_crossover(20, 50), monday_13())}
    meta = ctx.meta[("H1", "train")]
    trials_total = sum(1 for _ in open(root / "reports/trials/trials.csv", encoding="utf-8")) - 1
    info = {"created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_commit": results["ma_crossover"]["record"]["git_commit"],
            "git_dirty": results["ma_crossover"]["record"]["git_dirty"],
            "data": "data/processed/eurusd_bars/v1/eurusd_h1_train.parquet", "data_sha256": meta["sha256"],
            "percentile": ctx.percentile, "trials_logged": RANDOM_RUNS + len(results), "trials_total": trials_total,
            "weekdays": len(pd.bdate_range(meta["start"].tz_convert(None), meta["end"].tz_convert(None), inclusive="left"))}
    out.mkdir(parents=True)
    (out / "charts").mkdir()
    with open(out / "random_runs.csv", "x", encoding="utf-8", newline="") as h:
        dist.to_csv(h, index=False, float_format="%.6g", lineterminator="\n")
    for name, r in results.items():
        with open(out / f"trades_{name}.csv", "x", encoding="utf-8", newline="") as h:
            r["trades"].drop(columns=["entry_price", "exit_price"]).to_csv(h, index=False, float_format="%.6g",
                                                                           lineterminator="\n")
    chart_random(dist, {"MA 20/50": results["ma_crossover"]["metrics"]["expectancy_pips"],
                        "Mon 13 long": results["monday_13_long"]["metrics"]["expectancy_pips"]},
                 out / "charts" / "random_expectancy.png")
    chart_equity({"MA crossover 20/50 (H1)": results["ma_crossover"], "Monday 13:00 UTC long (H1)": results["monday_13_long"]},
                 out / "charts" / "equity.png")
    with open(out / "summary.md", "x", encoding="utf-8") as h:
        h.write(render_summary(dist, results, info))
    with open(out / "run.json", "x", encoding="utf-8") as h:
        json.dump({**info, "metrics": {k: r["metrics"] for k, r in results.items()},
                   "random": {"runs": RANDOM_RUNS, "seed0": RANDOM_SEED, "p_entry": RANDOM_P_ENTRY, "hold": RANDOM_HOLD}},
                  h, indent=2, default=str)
    return {"dist": dist, "results": results, "out_dir": out, "info": info}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    r = run()
    print(json.dumps({k: v["metrics"] for k, v in r["results"].items()}, indent=2, default=str))
    print("random expectancy median:", r["dist"]["expectancy_pips"].median())
    print(f"written: {r['out_dir']}")


if __name__ == "__main__":
    main()
