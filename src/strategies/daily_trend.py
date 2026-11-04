"""Daily trend strategies v1 on EURUSD, TRAIN split, three frozen variants, with a random baseline.

Rules (frozen by the project owner before any result was seen; three trials, never tuned):
  Daily bars: built from data/processed/eurusd_m1/v1, day closes at 17:00 America/New_York (DST-aware).
  v1a Donchian 20/10: close > high of the last 20 days -> long, close < low of the last 20 days -> short;
      exit on a close through the opposite 10-day low / high.
  v1b Donchian 55/20: the same with 55 / 20.
  v1c MA 50/200: SMA(50) > SMA(200) -> long, < -> short; reverses on a cross.
  Signals are taken at the daily close; every fill is at the next day's open.
  Cost: cost_for(entry) at p75 once per trade. Swap: 0.5 pip per night, both sides, Wednesday x 3.

Implementation choices where the rules are silent (fixed before running, listed in the report):
  - The Donchian windows exclude the signal day, otherwise close > high could never be true.
  - Day label = NY date of (time + 7 h). The Sunday session is therefore already part of Monday; any minute
    labelled Saturday or Sunday moves to Monday as well.
  - A night is one 17:00 rollover. Every fill is just after 17:00, so a position entered at the open of day E and
    closed at the open of day X crosses the rollovers of the weekdays in [E, X). Calendar weekdays are counted, so a
    holiday missing from the data is still charged. Wednesday's 17:00 rollover is the triple one.
  - The engine's entry blocks are not used: every daily open is in the rollover or weekly-open window, so they would
    block all entries. For the same reason cost_for(entry) is about 2.7-3.2 pips here, not the usual 1.0. A fixed
    1.0 pip version is reported next to it.
  - v1c takes its side as soon as both averages exist; it does not wait for the first cross.
  - A position still open on the last train day closes at that day's close ("end_of_data").
  - Flagged minutes are measured, not removed. No day is dropped; short holiday bars count as days.
Baseline: 1000 runs with the same trade count and the same set of holding lengths, placed at random without overlap
after the warm-up, with a random direction. Second control: the strategy's own trades with a random direction.

Run:
    .venv/bin/python -m src.strategies.daily_trend
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.engine import TRIALS, git_state, load_context, log_trial, max_drawdown, metrics, yearly
from src.data.bars import BAR_FLAGS
from src.data.inventory import sha256_file
from src.data.splits import read_m1_split
from src.research.exploratory_stats import bh_qvalues
from src.research.ml_discovery import M1_PATH, trade_stats

PIP = 1e-4
NY = "America/New_York"
SWAP_PIPS_PER_NIGHT = 0.5
SWAP_WEDNESDAY_MULTIPLE = 3
FIXED_COST_PIPS = 1.0
CONTROL_RUNS = 1000
CONTROL_SEED = 20261110
VARIANTS = {
    "v1a": {"kind": "donchian", "entry": 20, "exit": 10},
    "v1b": {"kind": "donchian", "entry": 55, "exit": 20},
    "v1c": {"kind": "ma", "fast": 50, "slow": 200},
}
FROZEN = {"day_close": "17:00 America/New_York", "signal": "daily close", "fill": "next day open",
          "swap_pips_per_night": SWAP_PIPS_PER_NIGHT, "swap_wednesday_multiple": SWAP_WEDNESDAY_MULTIPLE,
          "net_includes": "cost_for(entry) p75 and swap"}
SCRIPTS = ["src/strategies/daily_trend.py"]


# ---------------------------------------------------------------------------
# Daily bars
# ---------------------------------------------------------------------------
def trading_day(utc) -> pd.DatetimeIndex:
    """Naive trading-day label of each UTC instant; the day ends at 17:00 New York, weekend labels move to Monday."""
    wall = pd.DatetimeIndex(utc).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)
    day = wall.normalize()
    return day + pd.to_timedelta(np.select([day.dayofweek == 5, day.dayofweek == 6], [2, 1], 0), unit="D")


def daily_bars(m1: pd.DataFrame) -> pd.DataFrame:
    """Daily OHLC from M1 rows (columns timestamp_utc, open, high, low, close and BAR_FLAGS), plus flag shares."""
    d = m1.sort_values("timestamp_utc", kind="stable").drop_duplicates("timestamp_utc", keep="first").copy()
    d["trading_day"] = trading_day(d["timestamp_utc"])
    d["flagged"] = d[list(BAR_FLAGS)].any(axis=1)
    g = d.groupby("trading_day")
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
                        "minutes": g.size(), "flagged_minutes": g["flagged"].sum(), "first_minute": g["timestamp_utc"].first(),
                        "last_minute": g["timestamp_utc"].last()})
    out["flagged_pct"] = out["flagged_minutes"] / out["minutes"] * 100
    return out.reset_index()


# ---------------------------------------------------------------------------
# Signals: target[i] is known at the close of day i and takes effect at the open of day i + 1
# ---------------------------------------------------------------------------
def donchian_target(b: pd.DataFrame, entry: int, exit: int) -> np.ndarray:
    prior_high, prior_low = b["high"].shift(1), b["low"].shift(1)
    hi_in = prior_high.rolling(entry).max().to_numpy()
    lo_in = prior_low.rolling(entry).min().to_numpy()
    hi_out = prior_high.rolling(exit).max().to_numpy()
    lo_out = prior_low.rolling(exit).min().to_numpy()
    close = b["close"].to_numpy(float)
    target = np.zeros(len(b), dtype=int)
    pos = 0
    for i in range(len(b)):
        if (pos > 0 and close[i] < lo_out[i]) or (pos < 0 and close[i] > hi_out[i]):
            pos = 0
        if pos == 0:
            pos = 1 if close[i] > hi_in[i] else -1 if close[i] < lo_in[i] else 0
        target[i] = pos
    return target


def ma_target(b: pd.DataFrame, fast: int, slow: int) -> np.ndarray:
    f = b["close"].rolling(fast).mean().to_numpy()
    s = b["close"].rolling(slow).mean().to_numpy()
    target = np.zeros(len(b), dtype=int)
    pos = 0
    for i in range(len(b)):
        pos = 1 if f[i] > s[i] else -1 if f[i] < s[i] else pos
        target[i] = pos
    return target


def target_for(b: pd.DataFrame, variant: dict) -> np.ndarray:
    if variant["kind"] == "donchian":
        return donchian_target(b, variant["entry"], variant["exit"])
    return ma_target(b, variant["fast"], variant["slow"])


def first_fill(variant: dict) -> int:
    """Index of the first day that can be filled: its signal day has a complete window."""
    return variant["entry"] + 1 if variant["kind"] == "donchian" else variant["slow"]


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------
def swap_units(days: pd.DatetimeIndex) -> np.ndarray:
    """Cumulative swap nights up to each day, length n + 1: units[x] - units[e] is what [e, x) costs, Wednesday = 3.

    units[n] = units[n - 1]: a position closed at the last day's close leaves before that day's rollover.
    """
    d = days.to_numpy().astype("datetime64[D]")
    plain = np.busday_count(d[0], d)
    wednesdays = np.busday_count(d[0], d, weekmask="Wed")
    units = plain + (SWAP_WEDNESDAY_MULTIPLE - 1) * wednesdays
    return np.append(units, units[-1]).astype(float)


def extended_open(b: pd.DataFrame) -> np.ndarray:
    """Fill price per day; index n is the last close, used for a position still open at the end."""
    return np.append(b["open"].to_numpy(float), float(b["close"].iloc[-1]))


def build_trades(b: pd.DataFrame, target: np.ndarray, cost_by_day: np.ndarray) -> pd.DataFrame:
    n = len(b)
    px, units = extended_open(b), swap_units(pd.DatetimeIndex(b["trading_day"]))
    first = pd.DatetimeIndex(b["first_minute"])
    end = b["last_minute"].iloc[-1] + pd.Timedelta(minutes=1)
    days = pd.DatetimeIndex(b["trading_day"])
    rows = []
    pos, entry = 0, None

    def close(x: int) -> None:
        when = end if x == n else first[x]
        rows.append({"direction": "long" if pos > 0 else "short", "entry_i": entry, "exit_i": x, "entry_day": days[entry],
                     "exit_day": days[min(x, n - 1)], "entry_time": first[entry], "exit_time": when,
                     "gross_pips": pos * (px[x] - px[entry]) / PIP, "cost_pips": cost_by_day[entry],
                     "swap_nights": units[x] - units[entry], "hold_days": x - entry,
                     "calendar_days": (when - first[entry]) / pd.Timedelta(days=1),
                     "exit_reason": "end_of_data" if x == n else "signal"})

    for i in range(n - 1):
        want = int(target[i])
        if want != pos:
            if pos:
                close(i + 1)
            pos, entry = want, (i + 1 if want else None)
    if pos:
        close(n)
    t = pd.DataFrame(rows, columns=["direction", "entry_i", "exit_i", "entry_day", "exit_day", "entry_time", "exit_time",
                                    "gross_pips", "cost_pips", "swap_nights", "hold_days", "calendar_days", "exit_reason"])
    t["swap_pips"] = t["swap_nights"] * SWAP_PIPS_PER_NIGHT
    t["net_no_swap_pips"] = t["gross_pips"] - t["cost_pips"]
    t["net_pips"] = t["net_no_swap_pips"] - t["swap_pips"]
    return t


def without_swap(t: pd.DataFrame) -> pd.DataFrame:
    return t.assign(net_pips=t["net_no_swap_pips"])


def equity_by_day(b: pd.DataFrame, t: pd.DataFrame, swap: bool = True) -> np.ndarray:
    """Marked-to-market equity at each day's fill point (length n + 1): open P&L counts, not only closed trades."""
    px, units = extended_open(b), swap_units(pd.DatetimeIndex(b["trading_day"]))
    step = np.zeros(len(px))
    for r in t.itertuples():
        side = 1 if r.direction == "long" else -1
        rng = np.arange(r.entry_i, r.exit_i)
        step[rng + 1] += side * np.diff(px)[rng] / PIP
        step[r.entry_i] -= r.cost_pips
        if swap:
            step[rng + 1] -= np.diff(units)[rng] * SWAP_PIPS_PER_NIGHT
    return np.cumsum(step)


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------
def random_baseline(b: pd.DataFrame, t: pd.DataFrame, cost_by_day: np.ndarray, start: int, runs: int = CONTROL_RUNS,
                    seed: int = CONTROL_SEED) -> dict:
    """Mean net pips of `runs` random placements of the same holding lengths, each with a random direction."""
    k = len(t)
    if k == 0:
        return {"swap": np.array([]), "no_swap": np.array([])}
    px, units = extended_open(b), swap_units(pd.DatetimeIndex(b["trading_day"]))
    holds = t["hold_days"].to_numpy(int)
    free = len(b) - start - int(holds.sum())
    if free < 0:
        raise ValueError("holding lengths do not fit after the warm-up")
    rng = np.random.default_rng(seed)
    swap, no_swap = np.empty(runs), np.empty(runs)
    for r in range(runs):
        h = rng.permutation(holds)
        gaps = np.sort(rng.integers(0, free + 1, k))
        entry = start + gaps + np.concatenate([[0], np.cumsum(h)[:-1]])
        exit_ = entry + h
        side = rng.choice([-1, 1], k)
        net = side * (px[exit_] - px[entry]) / PIP - cost_by_day[entry]
        no_swap[r] = net.mean()
        swap[r] = (net - (units[exit_] - units[entry]) * SWAP_PIPS_PER_NIGHT).mean()
    return {"swap": swap, "no_swap": no_swap}


def direction_baseline(t: pd.DataFrame, runs: int = CONTROL_RUNS, seed: int = CONTROL_SEED + 1) -> dict:
    """The strategy's own trades, each with a random direction. Costs and swap do not depend on the direction."""
    if t.empty:
        return {"swap": np.array([]), "no_swap": np.array([])}
    rng = np.random.default_rng(seed)
    flips = rng.choice([-1.0, 1.0], (runs, len(t)))
    gross = (flips * t["gross_pips"].to_numpy(float)).mean(axis=1)
    no_swap = gross - t["cost_pips"].mean()
    return {"swap": no_swap - t["swap_pips"].mean(), "no_swap": no_swap}


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


ROWS = ["trades", "win_rate", "avg_win_pips", "avg_loss_pips", "expectancy_pips", "total_pips", "max_drawdown_pips",
        "sharpe_daily", "t_stat", "mean_cost_pips"]


def evaluate(b: pd.DataFrame, t: pd.DataFrame, cost_by_day: np.ndarray, variant: dict, start, end) -> dict:
    plain = without_swap(t)
    eq, eq_plain = equity_by_day(b, t), equity_by_day(b, t, swap=False)
    sides = {s: metrics(t[t["direction"] == s], start, end) for s in ("long", "short")}
    return {"trades": t, "metrics": metrics(t, start, end), "no_swap": metrics(plain, start, end), "stats": trade_stats(t),
            "yearly": yearly(t), "yearly_no_swap": yearly(plain), "sides": sides,
            "mtm_drawdown": max_drawdown(np.diff(eq, prepend=0.0)), "mtm_drawdown_no_swap": max_drawdown(np.diff(eq_plain, prepend=0.0)),
            "random": random_baseline(b, t, cost_by_day, first_fill(variant)), "direction": direction_baseline(t)}


def rank(control: np.ndarray, value: float) -> int:
    return int((control < value).sum())


def metric_table(res: dict) -> pd.DataFrame:
    rows = {
        "trades": lambda r: r["metrics"]["trades"], "win rate": lambda r: r["metrics"]["win_rate"],
        "avg win (pips)": lambda r: r["metrics"]["avg_win_pips"], "avg loss (pips)": lambda r: r["metrics"]["avg_loss_pips"],
        "expectancy (pips)": lambda r: r["metrics"]["expectancy_pips"], "total (pips)": lambda r: r["metrics"]["total_pips"],
        "max drawdown, closed trades (pips)": lambda r: r["metrics"]["max_drawdown_pips"],
        "max drawdown, marked to market (pips)": lambda r: r["mtm_drawdown"],
        "avg hold (trading days)": lambda r: r["trades"]["hold_days"].mean(),
        "avg hold (calendar days)": lambda r: r["trades"]["calendar_days"].mean(),
        "total swap (pips)": lambda r: r["trades"]["swap_pips"].sum(),
        "mean cost per trade (pips)": lambda r: r["metrics"]["mean_cost_pips"],
        "daily Sharpe": lambda r: r["metrics"]["sharpe_daily"], "t": lambda r: r["stats"]["t"], "one-sided p": lambda r: r["stats"]["p"],
        "BH q (3 trials)": lambda r: r["q"],
    }
    return pd.DataFrame({"metric": list(rows), **{v: [f(r) for f in rows.values()] for v, r in res.items()}}, dtype=object)


def scenario_table(res: dict) -> pd.DataFrame:
    rows = []
    for v, r in res.items():
        t = r["trades"]
        k = len(t)
        no_swap = t["gross_pips"] - t["cost_pips"]
        fixed = t["gross_pips"] - FIXED_COST_PIPS
        rows.append({"variant": v, "gross": t["gross_pips"].mean(), "cost_for, no swap": no_swap.mean(),
                     "cost_for + swap (headline)": t["net_pips"].mean(), f"{FIXED_COST_PIPS} pip, no swap": fixed.mean(),
                     f"{FIXED_COST_PIPS} pip + swap": (fixed - t["swap_pips"]).mean(), "total gross": t["gross_pips"].sum(),
                     "total cost": t["cost_pips"].sum(), "total swap": t["swap_pips"].sum(), "trades": k})
    return pd.DataFrame(rows)


def control_table(res: dict) -> pd.DataFrame:
    rows = []
    for v, r in res.items():
        for name, c in (("random placement + direction", r["random"]), ("own trades, random direction", r["direction"])):
            for label, key, e in (("with swap", "swap", r["metrics"]["expectancy_pips"]),
                                  ("no swap", "no_swap", r["no_swap"]["expectancy_pips"])):
                rows.append({"variant": v, "baseline": name, "swap": label, "strategy": e, "median": float(np.median(c[key])),
                             "p5": float(np.quantile(c[key], 0.05)), "p95": float(np.quantile(c[key], 0.95)),
                             "runs below strategy": rank(c[key], e)})
    return pd.DataFrame(rows)


def passes(r: dict) -> bool:
    e = r["metrics"]["expectancy_pips"]
    return bool(e > 0 and r["stats"]["t"] > 2 and r["q"] < 0.05 and e > np.quantile(r["random"]["swap"], 0.95)
                and e > np.quantile(r["direction"]["swap"], 0.95))


def verdict(res: dict) -> str:
    parts = []
    for v, r in res.items():
        e = r["metrics"]["expectancy_pips"]
        parts.append(f"- **{v}:** {r['metrics']['trades']} trades, expectancy {e:.1f} pips, t = {r['stats']['t']:.2f}, q = {r['q']:.3f}, "
                     f"above {rank(r['random']['swap'], e)}/{CONTROL_RUNS} random placements and "
                     f"{rank(r['direction']['swap'], e)}/{CONTROL_RUNS} random-direction runs. "
                     + ("Meets all checks." if passes(r) else "Does not meet all checks."))
    for v, r in res.items():
        t = r["trades"]
        if t["gross_pips"].sum() > 0 >= t["net_pips"].sum():
            parts.append(f"- **Swap decides {v}:** gross {t['gross_pips'].mean():.1f} pips per trade, {t['net_no_swap_pips'].mean():.1f} after cost, "
                         f"{t['net_pips'].mean():.1f} after swap. Before swap it is above {rank(r['random']['no_swap'], r['no_swap']['expectancy_pips'])}/{CONTROL_RUNS} "
                         f"random placements, so even then it is inside the random range.")
        elif t["gross_pips"].sum() <= 0:
            parts.append(f"- **{v} loses before costs:** gross {t['gross_pips'].mean():.1f} pips per trade. Cost and swap only add to it.")
    good = [v for v, r in res.items() if passes(r)]
    tail = (f"{', '.join(good)} meets the train checks (expectancy > 0, t > 2, q < 0.05, above both baselines' p95)." if good else
            "No variant meets the train checks together (expectancy > 0, t > 2, q < 0.05, above both baselines' p95).")
    return "\n".join(parts) + "\n\n" + tail


def late_minutes(bars: pd.DataFrame) -> np.ndarray:
    """Minutes between 17:00 New York, the nominal start of each bar, and the bar's first minute."""
    day = pd.DatetimeIndex(bars["trading_day"])
    previous = day - pd.to_timedelta(np.where(day.dayofweek == 0, 3, 1), unit="D")
    wall = pd.DatetimeIndex(bars["first_minute"]).tz_convert(NY).tz_localize(None)
    nominal = previous + pd.Timedelta(hours=17)
    nominal = nominal.where(day.dayofweek != 0, nominal + pd.Timedelta(days=2))         # Monday opens on Sunday
    return ((wall - nominal) / pd.Timedelta(minutes=1)).to_numpy()


def late_fills(t: pd.DataFrame, late: np.ndarray) -> int:
    days = np.concatenate([t["entry_i"].to_numpy(int), t.loc[t["exit_reason"] == "signal", "exit_i"].to_numpy(int)])
    return int((late[days] > 30).sum())


def render(res: dict, bars: pd.DataFrame, info: dict) -> str:
    names = list(res)
    pct = bars["flagged_pct"]
    short = bars[bars["minutes"] < 1200]
    late = late_minutes(bars)
    lines = [
        "# Strategy: daily trend v1, train 2015-2021",
        "",
        f"Generated {info['created_utc']} by `src/strategies/daily_trend.py` (HEAD `{(info['git_commit'] or '')[:7]}`, uncommitted script changes: "
        f"{str(info['git_dirty']).lower()}). Data: `{M1_PATH}` through the split guard, train only (SHA-256 `{info['m1_sha'][:16]}…`). "
        "Validation and test were not read.",
        "",
        "## Rules (frozen before running)",
        "",
        "- **v1a Donchian 20/10:** close above the last 20 days' high = long, below their low = short. Exit on a close through the opposite 10-day low or high.",
        "- **v1b Donchian 55/20:** the same with 55 and 20.",
        "- **v1c MA 50/200:** SMA 50 above SMA 200 = long, below = short. Reverses on a cross.",
        "- **Timing:** signal at the daily close (17:00 New York), fill at the next day's open.",
        f"- **Cost:** `cost_for(entry)` at {info['percentile']}, once per trade.",
        f"- **Swap:** {SWAP_PIPS_PER_NIGHT} pip per night on both sides, Wednesday x {SWAP_WEDNESDAY_MULTIPLE}. This is an assumption, not a measured rate.",
        "",
        "Where the rules are silent, I fixed these choices before running:",
        "",
        "- Donchian windows exclude the signal day.",
        "- A night is one 17:00 rollover: a trade pays for the weekdays from its entry day up to, but not including, its exit day.",
        "- v1c takes its side as soon as both averages exist, without waiting for a first cross.",
        "- A position still open on the last train day closes at that day's close.",
        "- Flagged minutes are measured, not removed. No day is dropped.",
        "",
        "## Things to know before reading the numbers",
        "",
        f"- **Cost is not ~1.0 pip here.** Every daily open sits in the rollover or weekly-open window, so `cost_for` returns "
        f"{info['cost_median']:.1f} pips at the median entry (mean {info['cost_mean']:.2f}). The results use `cost_for`, as specified; a fixed {FIXED_COST_PIPS} pip version is in the scenario table.",
        "- **The engine's entry blocks are off.** They reject rollover and weekly-open entries, so they would reject every daily open. This strategy has its own daily loop.",
        "- **Prices are bid only.** The open is the first bid after the rollover, when the spread is at its widest.",
        f"- **v1c starts late.** It needs 200 days, so its first possible fill is {info['first_fill_v1c']:%Y-%m-%d}.",
        "",
        "## Daily bars",
        "",
        f"- **Bars:** {len(bars):,} from {bars['trading_day'].iloc[0]:%Y-%m-%d} to {bars['trading_day'].iloc[-1]:%Y-%m-%d}. Weekdays: "
        + ", ".join(f"{k} {v}" for k, v in info["weekday_counts"].items()) + ".",
        "- **Sunday:** with a 17:00 New York close, the Sunday session (from 17:00) is already the start of Monday's bar, so there is no short Sunday bar. "
        f"Minutes that had to be moved from a weekend label: {info['weekend_minutes']}.",
        f"- **Short bars:** {len(short)} bars have under 1,200 minutes (holidays, data gaps and the partial first day): "
        + ", ".join(f"{d:%Y-%m-%d} ({m})" for d, m in zip(short["trading_day"], short["minutes"])) + ". They still count as days.",
        f"- **Weekdays with no bar:** {', '.join(info['missing_weekdays'])}. Swap is still charged for them.",
        f"- **Late opens:** {int((late > 0).sum())} bars start after 17:00 New York, {int((late > 30).sum())} of them by more than 30 minutes. "
        "Fills on bars more than 30 minutes late: " + "; ".join(f"{v} {late_fills(res[v]['trades'], late)}" for v in names) + ".",
        f"- **Flagged minutes** ({', '.join(BAR_FLAGS)}): {bars['flagged_minutes'].sum() / bars['minutes'].sum() * 100:.3f}% overall. Per bar: median {pct.median():.2f}%, "
        f"p95 {pct.quantile(0.95):.2f}%, max {pct.max():.1f}%. Bars above 10%: {int((pct > 10).sum())}, mostly DST-switch Mondays, whose Sunday session is flagged. Per-day values: `daily_flags.csv`.",
        "- **Flagged entries:** " + "; ".join(f"{v} {int((bars['flagged_pct'].to_numpy()[res[v]['trades']['entry_i'].to_numpy()] > 10).sum())} of {len(res[v]['trades'])}" for v in names)
        + " entry bars have over 10% flagged minutes.",
        "",
        "## Results (after cost and swap)",
        "",
        md_table(metric_table(res)),
        "",
        "Sharpe and t use net pips per trade or day. The closed-trade drawdown sees only exits; the marked-to-market one also counts open losses, measured at each daily open.",
        "",
        "## With and without swap (expectancy per trade, pips)",
        "",
        md_table(scenario_table(res)),
        "",
        "## Random baselines (expectancy, pips)",
        "",
        md_table(control_table(res)),
        "",
        f"- **Random placement + direction:** {CONTROL_RUNS} runs (seed {CONTROL_SEED}). Same trade count, same holding lengths in shuffled order, random start days without overlap after the warm-up, random direction. Costs and swap by the same rules.",
        f"- **Own trades, random direction:** {CONTROL_RUNS} runs (seed {CONTROL_SEED + 1}). Same entries and exits, direction chosen by coin flip. This isolates the choice of direction.",
        "",
        "## Long and short (after cost and swap)",
        "",
    ]
    lines.append(md_table(pd.DataFrame([{"variant": v, "side": s, **{k: res[v]["sides"][s][k] for k in
                                         ("trades", "win_rate", "expectancy_pips", "total_pips", "t_stat")}}
                                        for v in names for s in ("long", "short")])))
    lines += ["", "## By year of exit", ""]
    for v in names:
        y = res[v]["yearly"].merge(res[v]["yearly_no_swap"][["year", "net_pips"]].rename(columns={"net_pips": "net_no_swap_pips"}), on="year")
        lines += [f"**{v}**", "", md_table(y), ""]
    lines += ["## Exits", ""]
    for v in names:
        t = res[v]["trades"]
        lines.append(f"- **{v}:** " + ", ".join(f"{k} {n}" for k, n in t["exit_reason"].value_counts().items())
                     + f". Largest winner {t['net_pips'].max():.0f} pips, largest loser {t['net_pips'].min():.0f} pips.")
    lines += ["", "## Verdict", "", info["verdict"], "",
              f"Trial log: 3 rows were added (v1a, v1b, v1c), for a total of {info['trials_total']}. The swap-free and fixed-cost views are views of these 3 trials, not extra trials. "
              "The logged net includes `cost_for` and swap; the log has no swap column, so the swap rate is in `params`.",
              "", "Trades (pips only, no price levels): `trades_v1a.csv`, `trades_v1b.csv`, `trades_v1c.csv`."]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def script_git_state(root: Path) -> dict:
    gs = git_state(root)
    mine = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", *SCRIPTS], capture_output=True, text=True)
    gs["git_dirty"] = bool(gs["git_dirty"]) or bool(mine.stdout.strip())
    return gs


def run(root: Path = Path("."), reports_dir: Path = Path("reports"), trials_path: Path | None = TRIALS) -> dict:
    root = Path(root)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = root / reports_dir / f"strategy_daily_trend_{stamp}"
    if out.exists():
        raise FileExistsError(out)
    ctx = load_context(root)
    tr = ctx.splits["train"]
    m1, _ = read_m1_split(root / M1_PATH, "train", ctx.splits, ["timestamp_utc", "open", "high", "low", "close", *BAR_FLAGS])
    t_col = m1["timestamp_utc"]
    if not ((t_col >= tr.start) & (t_col < tr.end)).all():
        raise AssertionError("data outside the train split")
    bars = daily_bars(m1)
    cost = ctx.cost_model.cost_for(pd.DatetimeIndex(bars["first_minute"]), ctx.percentile)
    cost_by_day = cost["total_pips"].to_numpy(float)
    gs = script_git_state(root)
    m1_sha = sha256_file(root / M1_PATH)
    res = {}
    for v, spec in VARIANTS.items():
        t = build_trades(bars, target_for(bars, spec), cost_by_day)
        res[v] = evaluate(bars, t, cost_by_day, spec, tr.start, tr.end)
    for v, q in zip(res, bh_qvalues([res[v]["stats"]["p"] for v in res])):
        res[v]["q"] = float(q)
    if trials_path is not None:
        for v, r in res.items():
            log_trial(root / trials_path, {
                "run_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "strategy": f"daily_trend_{v}",
                "params": json.dumps({**FROZEN, **VARIANTS[v], "variant": v}, sort_keys=True), "split": "train",
                "timeframe": "D1_NY17", "cost_percentile": ctx.percentile, "data_sha256": m1_sha, **gs,
                **{k: (round(float(x), 6) if x is not None and np.isfinite(x) else None) for k, x in r["metrics"].items()}})
    trials_total = sum(1 for _ in open(root / TRIALS, encoding="utf-8")) - 1 if (root / TRIALS).exists() else 0
    days = pd.DatetimeIndex(bars["trading_day"])
    expected = pd.bdate_range(days[0], days[-1])
    raw = pd.DatetimeIndex(m1["timestamp_utc"]).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)
    info = {"created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **gs, "m1_sha": m1_sha, "percentile": ctx.percentile,
            "trials_total": trials_total, "cost_median": float(np.median(cost_by_day)), "cost_mean": float(cost_by_day.mean()),
            "first_fill_v1c": days[first_fill(VARIANTS["v1c"])], "weekend_minutes": int((raw.dayofweek >= 5).sum()),
            "missing_weekdays": [f"{d:%Y-%m-%d}" for d in expected.difference(days)],
            "weekday_counts": {n: int((days.dayofweek == i).sum()) for i, n in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"])},
            "verdict": verdict(res)}
    out.mkdir(parents=True)
    keep = ["direction", "entry_day", "exit_day", "entry_time", "exit_time", "gross_pips", "cost_pips", "swap_nights", "swap_pips",
            "net_no_swap_pips", "net_pips", "hold_days", "calendar_days", "exit_reason"]
    for v, r in res.items():
        with open(out / f"trades_{v}.csv", "x", encoding="utf-8", newline="") as h:
            r["trades"][keep].to_csv(h, index=False, float_format="%.6g", lineterminator="\n")
    with open(out / "daily_flags.csv", "x", encoding="utf-8", newline="") as h:
        bars[["trading_day", "minutes", "flagged_minutes", "flagged_pct", "first_minute", "last_minute"]].to_csv(
            h, index=False, float_format="%.4f", lineterminator="\n")
    with open(out / "summary.md", "x", encoding="utf-8") as h:
        h.write(render(res, bars, info))
    with open(out / "run.json", "x", encoding="utf-8") as h:
        json.dump({**{k: v for k, v in info.items() if k != "verdict"}, "frozen": FROZEN, "variants": VARIANTS,
                   "metrics": {v: r["metrics"] for v, r in res.items()}, "metrics_no_swap": {v: r["no_swap"] for v, r in res.items()},
                   "control": {"runs": CONTROL_RUNS, "seed": CONTROL_SEED}, "script_sha256": sha256_file(Path(__file__)),
                   "environment": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__}},
                  h, indent=2, default=str)
    return {"res": res, "bars": bars, "out_dir": out, "info": info}


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    r = run()
    print(json.dumps({v: x["metrics"] for v, x in r["res"].items()}, indent=2, default=str))
    print(f"written: {r['out_dir']}")


if __name__ == "__main__":
    main()
