"""Sweep + MSS strategy v1 on M15, TRAIN split, with matched random baselines and a report.

Rules (frozen by the project owner before any result was seen; never tuned on results):
  Trend    H4 bars built from M15 (UTC 00/04/08/12/16/20). Last CLOSED H4 close > EMA50 -> long only,
           < EMA50 -> short only.
  Asia     the day's 00:00-07:00 UTC high / low.
  Sweep    M15 bar starting 12:00-17:00 UTC. Long: low < Asia low and close > Asia low.
           Short: high > Asia high and close < Asia high.
  MSS      within the 8 M15 bars after the sweep, a close above the last swing high before the
           sweep (long) / below the last swing low (short). Swing = 2-bar fractal (2 bars each side).
  Entry    open of the bar after the MSS bar (engine: next-bar open). At most 1 trade per day.
  Exit     after 4 hours or at 20:45 UTC, whichever comes first. No stop, no target.

Implementation choices where the rules are silent (fixed here, documented in the report):
  - EMA50: standard recursive EMA (alpha = 2/51) seeded with the first H4 close; the trend is
    defined only after 50 closed H4 bars. An H4 bar is closed when the M15 bar ending at its end
    has closed (or, if that bar is missing, when the next block starts). All M15 bars count.
  - "12:00-17:00" = bar start in [12:00, 17:00). The day is the UTC date.
  - The trend is read at the sweep bar; the trade side is fixed then.
  - Swing before the sweep = the latest fractal at bar j with j + 2 <= sweep bar (confirmed at the
    latest by the sweep bar itself). No sweep is armed without such a fractal.
  - A newer sweep on the same day replaces an armed one. MSS is checked on the 8 bars after it.
  - The day's one trade is used when the strategy signals, even if the engine skips the entry
    (flagged entry bar, gap, rollover).

Run:
    .venv/bin/python -m src.strategies.sweep_mss
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.engine import History, Strategy, load_context, metrics, run_backtest, yearly

FROZEN = {"trend_tf": "H4", "ema": 50, "asia_utc": "00:00-07:00", "sweep_window_utc": "12:00-17:00",
          "mss_bars": 8, "fractal": 2, "max_trades_per_day": 1, "hold_hours": 4, "exit_clock_utc": "20:45",
          "stop": None, "target": None}
NS_MIN = 60_000_000_000
H4_MIN = 240
BAR_MIN = 15
RANDOM_RUNS = 100
RANDOM_SEED = 20261103
SIGNAL_WINDOW_MIN = (12 * 60, 18 * 60 + 45)   # random baselines: signal-bar starts the strategy can produce


class _TrendDay:
    """Incremental state built only from the History given at each call (one new bar per call)."""

    def __init__(self, ema_n: int = FROZEN["ema"]):
        self.ema_n, self.alpha = ema_n, 2 / (ema_n + 1)
        self.ema, self.h4_count, self.trend = None, 0, 0
        self.block, self.block_close = None, None
        self.day, self.asia_hi, self.asia_lo, self.traded = None, -np.inf, np.inf, False
        self.day_counted = False
        self.last = -1
        self.counters = {"days_with_trend": 0, "signals": 0}

    def _close_h4(self, close: float) -> None:
        self.ema = close if self.ema is None else self.alpha * close + (1 - self.alpha) * self.ema
        self.h4_count += 1
        self.trend = 0 if self.h4_count < self.ema_n else (1 if close > self.ema else -1 if close < self.ema else 0)

    def _new_day(self, day: int) -> None:
        self.day, self.asia_hi, self.asia_lo, self.traded = day, -np.inf, np.inf, False
        self.day_counted = False

    def _on_bar(self, h: History, k: int, minute: int) -> None:
        pass

    def ingest(self, h: History) -> None:
        for k in range(self.last + 1, h.i + 1):
            t = int(h.time[k].astype(np.int64)) // NS_MIN                     # minutes since epoch, UTC
            block = t // H4_MIN
            if self.block is not None and block != self.block:
                self._close_h4(self.block_close)
            self.block, self.block_close = block, h.close[k]
            if (t + BAR_MIN) % H4_MIN == 0:          # this bar ends the H4 block: it is closed now
                self._close_h4(self.block_close)
                self.block = None
            day, minute = t // 1440, t % 1440
            if day != self.day:
                self._new_day(day)
            if (not self.day_counted and self.trend
                    and SIGNAL_WINDOW_MIN[0] <= minute <= SIGNAL_WINDOW_MIN[1]):   # a tradable trend day
                self.counters["days_with_trend"] += 1
                self.day_counted = True
            if minute < 7 * 60:
                self.asia_hi, self.asia_lo = max(self.asia_hi, h.high[k]), min(self.asia_lo, h.low[k])
            self._on_bar(h, k, minute)
        self.last = h.i


def last_fractal(values: np.ndarray, upto: int, high: bool, n: int = FROZEN["fractal"]):
    """Value of the latest n-bar fractal at index j <= upto (needs j+n bars to exist), else None."""
    for j in range(min(upto, len(values) - 1 - n), n - 1, -1):
        v = values[j]
        side = np.concatenate([values[j - n:j], values[j + 1:j + 1 + n]])
        if (high and (v > side).all()) or (not high and (v < side).all()):
            return float(v)
    return None


class SweepMSS(_TrendDay):
    def __init__(self):
        super().__init__()
        self.sweep = None          # (bar index, minute-time, side, level)
        self.entry_side = 0
        self.counters.update({"sweeps": 0, "sweeps_without_swing": 0, "mss": 0})

    def _new_day(self, day: int) -> None:
        super()._new_day(day)
        self.sweep = None

    def _on_bar(self, h: History, k: int, minute: int) -> None:
        self.entry_side = 0
        if self.traded or not np.isfinite(self.asia_lo):
            return
        if self.sweep is not None:
            s_k, s_t, side, level = self.sweep
            t = int(h.time[k].astype(np.int64)) // NS_MIN
            if t - s_t > FROZEN["mss_bars"] * BAR_MIN:
                self.sweep = None
            elif k > s_k and ((side > 0 and h.close[k] > level) or (side < 0 and h.close[k] < level)):
                self.counters["mss"] += 1
                self.entry_side, self.traded, self.sweep = side, True, None
                return
        if 12 * 60 <= minute < 17 * 60 and self.trend:
            side = self.trend
            swept = (h.low[k] < self.asia_lo < h.close[k]) if side > 0 else (h.high[k] > self.asia_hi > h.close[k])
            if swept:
                self.counters["sweeps"] += 1
                level = last_fractal(h.high if side > 0 else h.low, k - FROZEN["fractal"], high=side > 0)
                if level is None:
                    self.counters["sweeps_without_swing"] += 1
                else:
                    t = int(h.time[k].astype(np.int64)) // NS_MIN
                    self.sweep = (k, t, side, level)

    def __call__(self, h: History):
        self.ingest(h)
        if h.position == 0 and self.entry_side:
            self.counters["signals"] += 1
            return int(self.entry_side)
        return None


class RandomMatched(_TrendDay):
    """Random entries in the same signal window, same exits, at most one per day, after the same trend warm-up.

    trend_aligned=False: random side. trend_aligned=True: side = H4 trend (isolates what sweep + MSS add).
    """

    def __init__(self, seed: int, p_bar: float, trend_aligned: bool):
        super().__init__()
        self.rng, self.p_bar, self.trend_aligned = np.random.default_rng(seed), p_bar, trend_aligned
        self.entry_side = 0

    def _on_bar(self, h: History, k: int, minute: int) -> None:
        self.entry_side = 0
        if self.traded or not self.trend or not (SIGNAL_WINDOW_MIN[0] <= minute <= SIGNAL_WINDOW_MIN[1]):
            return
        draw, coin = self.rng.random(), self.rng.random()
        if draw < self.p_bar:
            self.entry_side = self.trend if self.trend_aligned else (1 if coin < 0.5 else -1)
            self.traded = True

    def __call__(self, h: History):
        self.ingest(h)
        if h.position == 0 and self.entry_side:
            self.counters["signals"] += 1
            return int(self.entry_side)
        return None


def make_strategy(signal, name: str, params: dict) -> Strategy:
    return Strategy(name, signal, params, hold_bars=FROZEN["hold_hours"] * 60 // BAR_MIN, exit_on_signal=False,
                    exit_clock_utc=FROZEN["exit_clock_utc"])


def sweep_mss_strategy() -> tuple[Strategy, SweepMSS]:
    sig = SweepMSS()
    return make_strategy(sig, "sweep_mss_v1", dict(FROZEN)), sig


def random_matched_strategy(seed: int, p_bar: float, trend_aligned: bool) -> Strategy:
    name = "sweep_mss_random_trend" if trend_aligned else "sweep_mss_random_side"
    return make_strategy(RandomMatched(seed, p_bar, trend_aligned), name,
                         {"seed": seed, "p_bar": round(p_bar, 6), "window_utc": "12:00-18:45 signal bar"})


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
from src.backtest.baselines import BLUE, ORANGE, AQUA, INK2, BASE, MUTED, SURFACE, _plt, _save, md_table  # noqa: E402

METRIC_ROWS = ["trades", "win_rate", "avg_win_pips", "avg_loss_pips", "expectancy_pips", "total_pips",
               "max_drawdown_pips", "sharpe_daily", "t_stat", "mean_cost_pips"]


def chart_random(dists: dict, value: float, path: Path) -> None:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    bins = np.linspace(min(d["expectancy_pips"].min() for d in dists.values()) - 0.2,
                       max(max(d["expectancy_pips"].max() for d in dists.values()), value) + 0.2, 30)
    for (name, d), color in zip(dists.items(), (BLUE, AQUA)):
        ax.hist(d["expectancy_pips"], bins=bins, color=color, alpha=0.55, edgecolor=SURFACE, label=name)
    ax.axvline(value, color=ORANGE, lw=2.5)
    ax.text(value, ax.get_ylim()[1] * 0.95, " sweep + MSS", color=INK2, va="top", fontsize=8)
    ax.axvline(0, color=BASE, lw=0.8)
    ax.set_xlabel("expectancy per trade after costs (pips)")
    ax.set_ylabel("random runs")
    ax.set_title("Sweep + MSS vs matched random entries (100 runs each), train 2015-2021", loc="left")
    ax.legend(frameon=False, loc="upper left")
    _save(fig, path)
    plt.close(fig)


def chart_equity(trades: pd.DataFrame, path: Path) -> None:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 3.4))
    for side, color in (("long", BLUE), ("short", AQUA)):
        t = trades[trades["direction"] == side]
        ax.plot(t["exit_time"], t["net_pips"].cumsum(), color=color, lw=1.5, label=f"{side} (after costs)")
    ax.plot(trades["exit_time"], trades["net_pips"].cumsum(), color=ORANGE, lw=2, label="all (after costs)")
    ax.plot(trades["exit_time"], trades["gross_pips"].cumsum(), color=MUTED, lw=1, label="all (before costs)")
    ax.axhline(0, color=BASE, lw=0.8)
    ax.set_ylabel("cumulative pips")
    ax.set_title("Sweep + MSS v1, M15, train 2015-2021", loc="left")
    ax.legend(frameon=False, loc="upper left", ncols=2)
    _save(fig, path)
    plt.close(fig)


def render_summary(res: dict, sides: dict, dists: dict, funnel: dict, info: dict) -> str:
    m = res["metrics"]
    table = pd.DataFrame({"metric": METRIC_ROWS, "all": [m[k] for k in METRIC_ROWS],
                          **{s: [sides[s][k] for k in METRIC_ROWS] for s in ("long", "short")}})
    comp = pd.DataFrame([{"baseline": name, "runs": len(d), "median trades": d["trades"].median(),
                          "expectancy p5": d["expectancy_pips"].quantile(0.05),
                          "expectancy median": d["expectancy_pips"].median(),
                          "expectancy p95": d["expectancy_pips"].quantile(0.95),
                          "runs below sweep+MSS": int((d["expectancy_pips"] < m["expectancy_pips"]).sum())}
                         for name, d in dists.items()])
    yr = res["yearly"]
    side_year = (res["trades"].assign(year=res["trades"]["exit_time"].dt.year)
                 .pivot_table(index="year", columns="direction", values="net_pips", aggfunc="sum").reset_index())
    side_year.columns.name = None
    t = res["trades"]
    lines = [
        "# Strategy: Sweep + MSS v1 (M15), train 2015-2021",
        "",
        f"Generated {info['created_utc']} by `src/strategies/sweep_mss.py` (HEAD `{(info['git_commit'] or '')[:7]}`, "
        f"uncommitted script changes: {str(info['git_dirty']).lower()}). Data: M15 train bars, SHA-256 `{info['data_sha256'][:16]}…`. "
        "Validation and test were not read.",
        "",
        "## Rules (frozen before running; not changed after seeing results)",
        "",
        "- **Trend:** H4 bars built from M15. Long only when the last closed H4 close is above EMA50, short only when it is below.",
        "- **Asia range:** the day's 00:00-07:00 UTC high and low.",
        "- **Sweep:** an M15 bar starting 12:00-17:00 UTC.",
        "  - Long: the low goes below the Asia low and the bar closes back above it.",
        "  - Short: the high goes above the Asia high and the bar closes back below it.",
        "- **MSS:** within the next 8 M15 bars, a close beyond the last swing before the sweep: above the swing high for a long, below the swing low for a short. A swing is a 2-bar fractal.",
        "- **Entry:** open of the bar after the MSS bar. At most 1 trade per day.",
        "- **Exit:** after 4 h or at 20:45 UTC, whichever comes first. No stop, no target.",
        "",
        "Where the rules are silent, I made these choices before running (also in the module docstring):",
        "",
        "- **EMA50:** standard EMA seeded with the first H4 close. The trend counts only after 50 closed H4 bars.",
        "- **Sweep window:** a bar start in [12:00, 17:00) UTC.",
        "- **Side:** taken from the trend at the sweep bar.",
        "- **Swing:** the latest fractal confirmed no later than the sweep bar.",
        "- **Repeated sweeps:** a newer sweep on the same day replaces an armed one.",
        "- **Daily limit:** a signal uses up the day's one trade even if the engine then skips the entry.",
        "",
        f"Engine (`src/backtest/engine.py`): next-bar-open fills. Entries are skipped on `any_gap`/`any_flag` bars, after gaps, and in rollover or weekly-open times. Cost = `cost_for(entry_time)` at {info['percentile']} + 0.6 commission + 0.2 slippage. Prices are HistData bid. One field was added to the engine, `exit_clock_utc`, for the 20:45 exit. Earlier baseline results are unchanged; this was checked.",
        "",
        "## Signal funnel",
        "",
        f"- **Days:** {funnel['days_with_trend']:,} days with a defined trend and bars in the 12:00-18:45 UTC window.",
        f"- **Sweeps:** {funnel['sweeps']:,} on the trend side; {funnel['sweeps_without_swing']:,} of them had no prior swing.",
        f"- **MSS:** {funnel['mss']:,} signals.",
        f"- **Trades:** {m['trades']:,}. {funnel['mss'] - m['trades']:,} entries were skipped by the engine (flagged entry bar, gap, or rollover).",
        "",
        "## Results (after costs, pips)",
        "",
        md_table(table),
        "",
        f"- **Exit reasons:** " + ", ".join(f"{k} {v}" for k, v in t["exit_reason"].value_counts().items()) + ".",
        f"- **Holding time:** median {t['bars_held'].median():.0f} M15 bars.",
        f"- **Before costs:** mean gross {t['gross_pips'].mean():.3f} pips per trade.",
        f"- **Largest single trade:** {t.loc[t['net_pips'].abs().idxmax(), 'net_pips']:+.1f} pips "
        f"({t.loc[t['net_pips'].abs().idxmax(), 'direction']}, {str(t.loc[t['net_pips'].abs().idxmax(), 'entry_time'])[:10]}). "
        f"Expectancy without it: {t.drop(t['net_pips'].abs().idxmax())['net_pips'].mean():.3f} pips.",
        "",
        "## By year",
        "",
        md_table(yr),
        "",
        "Net pips by year and side:",
        "",
        md_table(side_year.fillna(0.0)),
        "",
        "## Against random baselines",
        "",
        "There are two matched baselines with 100 seeded runs each. Both use the same M15 data, the same signal window (signal bar 12:00-18:45 UTC), at most 1 trade per day, the same trend warm-up, the same exits and the same engine rules. The per-bar entry probability is set so the number of trades is close to the strategy's.",
        "",
        "- **random side:** random direction.",
        "- **random, trend side:** direction = H4 trend. This shows what sweep + MSS adds on top of the trend filter.",
        "",
        md_table(comp),
        "",
        f"For reference, the H1 random baseline (`reports/backtest_baselines_20261102T085428Z`) had a median expectancy of {info['h1_random_median']:.3f} pips.",
        "",
        "Charts: `charts/random_comparison.png` and `charts/equity.png`. Trade list (pips only): `trades.csv`. Every random run is in `random_side.csv` and `random_trend.csv`.",
        "",
        "## How to read this",
        "",
        "- **Rules:** the parameters were fixed in the prompt before any run and were not changed. This is the strategy's only logged train run. Two earlier runs, with logging off, checked only runtime and trade counts; no performance numbers were looked at.",
        f"- **Trial log:** {info['trials_added']} rows were added to `reports/trials/trials.csv` (1 strategy + 200 random), for a total of {info['trials_total']} rows.",
        "- **Verdict on train:** expectancy is negative, and only part of the random distributions is below it. Sweep + MSS adds no measurable edge over random entries or over the trend filter alone. Spending validation 2022-2023 on this frozen v1 is not recommended; the validation data is better kept for candidates that clear the random baseline on train.",
        "- **Limitations:** the cost is charged at entry only; there is no stop, so the risk on a single trade is open-ended; and prices are bid only.",
    ]
    return "\n".join(lines) + "\n"


def run(root: Path = Path("."), reports_dir: Path = Path("reports"), stamp: str | None = None) -> dict:
    root = Path(root)
    stamp = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = root / reports_dir / f"strategy_sweep_mss_{stamp}"
    if out.exists():
        raise FileExistsError(f"{out} exists")
    ctx = load_context(root)
    strat, sig = sweep_mss_strategy()
    res = run_backtest(ctx, strat, "M15")
    meta = ctx.meta[("M15", "train")]
    trades = res["trades"]
    sides = {s: metrics(trades[trades["direction"] == s], meta["start"], meta["end"]) for s in ("long", "short")}
    funnel = sig.counters

    # Matched random: per-bar probability so that P(at least one signal per trend day) ~= the strategy's trades per trend day
    window_bars = (SIGNAL_WINDOW_MIN[1] - SIGNAL_WINDOW_MIN[0]) // BAR_MIN + 1
    p_day = min(0.95, max(res["metrics"]["trades"], 1) / max(funnel["days_with_trend"], 1))
    p_bar = 1 - (1 - p_day) ** (1 / window_bars)
    dists = {}
    for label, aligned in (("random side", False), ("random, trend side", True)):
        rows = []
        for k in range(RANDOM_RUNS):
            r = run_backtest(ctx, random_matched_strategy(RANDOM_SEED + k, p_bar, aligned), "M15")
            rows.append({"seed": RANDOM_SEED + k, **r["metrics"]})
        dists[label] = pd.DataFrame(rows)
    h1_random = root / "reports/backtest_baselines_20261102T085428Z/random_runs.csv"
    trials_total = sum(1 for _ in open(root / "reports/trials/trials.csv", encoding="utf-8")) - 1
    info = {"created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_commit": res["record"]["git_commit"], "git_dirty": res["record"]["git_dirty"],
            "data_sha256": meta["sha256"], "percentile": ctx.percentile, "trials_added": 1 + 2 * RANDOM_RUNS,
            "trials_total": trials_total, "p_bar": p_bar,
            "h1_random_median": float(pd.read_csv(h1_random)["expectancy_pips"].median()) if h1_random.exists() else np.nan}
    out.mkdir(parents=True)
    (out / "charts").mkdir()
    with open(out / "trades.csv", "x", encoding="utf-8", newline="") as h:
        trades.drop(columns=["entry_price", "exit_price"]).to_csv(h, index=False, float_format="%.6g", lineterminator="\n")
    for label, fname in (("random side", "random_side.csv"), ("random, trend side", "random_trend.csv")):
        with open(out / fname, "x", encoding="utf-8", newline="") as h:
            dists[label].to_csv(h, index=False, float_format="%.6g", lineterminator="\n")
    chart_random(dists, res["metrics"]["expectancy_pips"], out / "charts" / "random_comparison.png")
    chart_equity(trades, out / "charts" / "equity.png")
    with open(out / "summary.md", "x", encoding="utf-8") as h:
        h.write(render_summary(res, sides, dists, funnel, info))
    with open(out / "run.json", "x", encoding="utf-8") as h:
        json.dump({**info, "frozen_rules": FROZEN, "metrics": res["metrics"], "sides": sides, "funnel": funnel,
                   "random": {"runs": RANDOM_RUNS, "seed0": RANDOM_SEED, "window_min_utc": SIGNAL_WINDOW_MIN}},
                  h, indent=2, default=str)
    return {"res": res, "sides": sides, "dists": dists, "funnel": funnel, "out_dir": out}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    r = run()
    print(json.dumps({"metrics": r["res"]["metrics"], "funnel": r["funnel"]}, indent=2, default=str))
    print(f"written: {r['out_dir']}")


if __name__ == "__main__":
    main()
