"""Backtest engine v1: one position, fixed 1 lot, next-bar-open execution.

Timing (look-ahead protection):
  At the close of bar i the signal sees a History whose arrays end at bar i
  (numpy views; there is nothing later to read). Any order it causes fills at the
  OPEN of bar i+1. A time exit fills at the open of the first bar starting at or
  after entry_time + hold_bars * timeframe (or the exit_clock_utc time, if earlier).

Entries are skipped (exits never are) when the entry bar
  - is not the bar right after the signal bar (e.g. after a weekend or data gap),
  - has any_gap or any_flag,
  - falls in a rollover, weekly-open or market-closed period (CostModel.cost_for flags).

Cost: every trade pays cost_for(entry_time) round-trip pips (spread at the configured
percentile + commission + slippage), once. Prices are HistData bid; P&L in pips,
1 lot = 10 USD per pip for EURUSD.

Every run_backtest call appends one row to reports/trials/trials.csv (never rewritten).
Data is read through the split guard; the default split is train.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import subprocess
from dataclasses import dataclass, field
from math import sqrt
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from src.data.bars import bar_file, read_bars
from src.data.cost_model import CostModel, load_cost_config
from src.data.inventory import sha256_file
from src.data.splits import DEFAULT_SPLITS, load_splits

PIP = 1e-4
TF_MINUTES = {"M15": 15, "H1": 60}
BARS_DIR = Path("data/processed/eurusd_bars/v1")
COST_DIR = Path("data/processed/cost_model/v1")
COST_CONFIG = Path("config/cost_model_v1.yaml")
TRIALS = Path("reports/trials/trials.csv")
TRIAL_COLUMNS = ["run_utc", "strategy", "params", "split", "timeframe", "trades", "win_rate", "avg_win_pips",
                 "avg_loss_pips", "expectancy_pips", "total_pips", "max_drawdown_pips", "sharpe_daily", "t_stat",
                 "cost_percentile", "mean_cost_pips", "data_sha256", "git_commit", "git_dirty"]
SCRIPTS = ["src/backtest/engine.py", "src/backtest/baselines.py", "src/data/cost_model.py"]


class History:
    """What a signal may see at the close of bar i: arrays up to and including bar i, nothing later."""

    __slots__ = ("i", "time", "open", "high", "low", "close", "clean", "position", "bars_in_position")

    def __init__(self, data: dict, i: int, position: int, bars_in_position: int):
        end = i + 1
        self.i = i
        self.time = data["time"][:end]
        self.open = data["open"][:end]
        self.high = data["high"][:end]
        self.low = data["low"][:end]
        self.close = data["close"][:end]
        self.clean = data["clean"][:end]
        self.position = position
        self.bars_in_position = bars_in_position


Signal = Callable[[History], "int | None"]


@dataclass
class Strategy:
    """signal returns the desired position (+1 long, -1 short, 0 flat) or None (no opinion)."""
    name: str
    signal: Signal
    params: dict = field(default_factory=dict)
    hold_bars: int | None = None        # time exit after this many bars; None = no time exit
    exit_on_signal: bool = True         # close when the signal asks for 0 or the opposite side
    exit_clock_utc: str | None = None   # "HH:MM": also exit at this UTC time of day, whichever comes first


def prepare(bars: pd.DataFrame, cost_model: CostModel, percentile: str | None = None) -> dict:
    """Arrays for the loop, with the round-trip cost and the entry-block flags at each bar's start."""
    b = bars.sort_values("bar_start_utc").reset_index(drop=True)
    times = pd.DatetimeIndex(b["bar_start_utc"])
    cost = cost_model.cost_for(times, percentile)
    blocked = (cost["is_rollover"] | cost["is_weekly_open"] | cost["is_market_closed"]).to_numpy()
    return {
        "time": times.tz_convert("UTC").tz_localize(None).to_numpy(), "open": b["open"].to_numpy(float), "high": b["high"].to_numpy(float),
        "low": b["low"].to_numpy(float), "close": b["close"].to_numpy(float),
        "clean": (~b["any_gap"].astype(bool) & ~b["any_flag"].astype(bool)).to_numpy(),
        "cost": cost["total_pips"].to_numpy(float), "blocked": blocked,
        "percentile": str(cost["percentile"].iloc[0]) if len(cost) else percentile,
    }


def clock_after(when: np.datetime64, hhmm: str) -> np.datetime64:
    """The first UTC time-of-day hhmm strictly after `when` (same day, else the next day)."""
    h, m = (int(x) for x in hhmm.split(":"))
    clock = when.astype("datetime64[D]").astype(when.dtype) + np.timedelta64(h * 60 + m, "m")
    return clock if clock > when else clock + np.timedelta64(1, "D")


def backtest(data: dict, strategy: Strategy, timeframe: str) -> pd.DataFrame:
    step = np.timedelta64(TF_MINUTES[timeframe], "m")
    t, o, c = data["time"], data["open"], data["close"]
    n = len(t)
    trades = []
    pos, entry_i, due = 0, None, None

    def close_at(j: int, price: float, when, reason: str) -> None:
        gross = (price - o[entry_i]) / PIP * pos
        trades.append({"direction": "long" if pos > 0 else "short", "entry_time": t[entry_i], "exit_time": when,
                       "entry_price": o[entry_i], "exit_price": price, "gross_pips": round(gross, 6),
                       "cost_pips": data["cost"][entry_i], "bars_held": j - entry_i, "exit_reason": reason})

    for i in range(n - 1):
        nxt = i + 1
        if pos and due is not None and t[nxt] >= due:
            close_at(nxt, o[nxt], t[nxt], "time")
            pos, entry_i, due = 0, None, None
        held = (i - entry_i + 1) if pos else 0
        desired = strategy.signal(History(data, i, pos, held))
        if desired not in (None, -1, 0, 1):
            raise ValueError(f"signal returned {desired!r}; expected -1, 0, 1 or None")
        if pos and strategy.exit_on_signal and desired is not None and desired != pos:
            close_at(nxt, o[nxt], t[nxt], "signal")
            pos, entry_i, due = 0, None, None
        if pos == 0 and desired in (-1, 1) and t[nxt] - t[i] == step and data["clean"][nxt] and not data["blocked"][nxt]:
            pos, entry_i = desired, nxt
            due = t[nxt] + step * strategy.hold_bars if strategy.hold_bars else None
            if strategy.exit_clock_utc:
                clock = clock_after(t[nxt], strategy.exit_clock_utc)
                due = clock if due is None else min(due, clock)
    if pos:
        close_at(n - 1, c[n - 1], t[n - 1] + step, "end_of_data")
    out = pd.DataFrame(trades, columns=["direction", "entry_time", "exit_time", "entry_price", "exit_price",
                                        "gross_pips", "cost_pips", "bars_held", "exit_reason"])
    out["entry_time"] = pd.to_datetime(out["entry_time"], utc=True)
    out["exit_time"] = pd.to_datetime(out["exit_time"], utc=True)
    out["net_pips"] = (out["gross_pips"] - out["cost_pips"]).round(6)
    return out


def max_drawdown(pnl) -> float:
    equity = np.concatenate([[0.0], np.cumsum(np.asarray(pnl, float))])
    return float((np.maximum.accumulate(equity) - equity).max())


def daily_sharpe(trades: pd.DataFrame, start, end) -> float:
    """Annualised (sqrt 252) Sharpe of daily net pips (UTC exit date).

    Every weekday in [start, end) is a day, plus any other date with an exit (e.g. Sunday); no exits = 0.
    """
    days = pd.bdate_range(pd.Timestamp(start).tz_convert(None).normalize(),
                          pd.Timestamp(end).tz_convert(None).normalize() - pd.Timedelta(days=1))
    daily = trades.groupby(trades["exit_time"].dt.tz_convert(None).dt.normalize())["net_pips"].sum()
    series = daily.reindex(days.union(daily.index), fill_value=0.0)
    sd = series.std(ddof=1)
    return float(series.mean() / sd * sqrt(252)) if sd > 0 else np.nan


def metrics(trades: pd.DataFrame, start, end) -> dict:
    net = trades["net_pips"].to_numpy(float)
    n = len(net)
    wins, losses = net[net > 0], net[net <= 0]
    sd = net.std(ddof=1) if n > 1 else np.nan
    return {
        "trades": n, "win_rate": float(len(wins) / n) if n else np.nan,
        "avg_win_pips": float(wins.mean()) if len(wins) else np.nan,
        "avg_loss_pips": float(losses.mean()) if len(losses) else np.nan,
        "expectancy_pips": float(net.mean()) if n else np.nan, "total_pips": float(net.sum()),
        "max_drawdown_pips": max_drawdown(net), "sharpe_daily": daily_sharpe(trades, start, end) if n else np.nan,
        "t_stat": float(net.mean() / (sd / sqrt(n))) if n > 1 and sd > 0 else np.nan,
        "mean_cost_pips": float(trades["cost_pips"].mean()) if n else np.nan,
    }


def yearly(trades: pd.DataFrame) -> pd.DataFrame:
    g = trades.groupby(trades["exit_time"].dt.year)["net_pips"]
    return pd.DataFrame({"trades": g.size(), "net_pips": g.sum(), "expectancy_pips": g.mean(),
                         "win_rate": g.apply(lambda s: float((s > 0).mean()))}).rename_axis("year").reset_index()


def git_state(root: Path) -> dict:
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        return {"git_commit": None, "git_dirty": None}
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", *SCRIPTS],
                           capture_output=True, text=True)
    return {"git_commit": head.stdout.strip(), "git_dirty": bool(dirty.stdout.strip())}


def log_trial(path: Path, record: dict) -> None:
    """Append one row; create the file with a header if missing; refuse a file with a different header."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with open(path, encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle), None)
        if header != TRIAL_COLUMNS:
            raise ValueError(f"{path} has an unexpected header; not appending")
        mode = "a"
    else:
        mode = "x"
    with open(path, mode, encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=TRIAL_COLUMNS, lineterminator="\n")
        if mode == "x":
            w.writeheader()
        w.writerow({k: record.get(k) for k in TRIAL_COLUMNS})


@dataclass
class Context:
    """Loaded inputs shared by several runs."""
    root: Path
    splits: dict
    cost_model: CostModel
    percentile: str
    data: dict          # (timeframe, split) -> prepared arrays
    meta: dict          # (timeframe, split) -> {"start", "end", "sha256"}


def load_context(root: Path = Path("."), percentile: str | None = None) -> Context:
    root = Path(root)
    cfg = load_cost_config(root / COST_CONFIG)
    return Context(root, load_splits(root / DEFAULT_SPLITS), CostModel.load(root / COST_DIR, cfg),
                   percentile or cfg["trading_costs"]["spread_percentile"], {}, {})


def get_data(ctx: Context, timeframe: str, split: str = "train", unlock_test: bool = False) -> dict:
    key = (timeframe, split)
    if key not in ctx.data:
        bars = read_bars(ctx.root / BARS_DIR, timeframe, split, ctx.splits, unlock_test=unlock_test)  # split guard
        ctx.data[key] = prepare(bars, ctx.cost_model, ctx.percentile)
        s = ctx.splits[split]
        ctx.meta[key] = {"start": s.start, "end": s.end,
                         "sha256": sha256_file(ctx.root / BARS_DIR / bar_file(timeframe, split))}
    elif ctx.splits[split].locked and unlock_test is not True:
        read_bars(ctx.root / BARS_DIR, timeframe, split, ctx.splits)   # raises: cached data is still guarded
    return ctx.data[key]


def run_backtest(ctx: Context, strategy: Strategy, timeframe: str, split: str = "train",
                 unlock_test: bool = False, trials_path: Path | None = TRIALS) -> dict:
    data = get_data(ctx, timeframe, split, unlock_test)
    trades = backtest(data, strategy, timeframe)
    meta = ctx.meta[(timeframe, split)]
    m = metrics(trades, meta["start"], meta["end"])
    record = {"run_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "strategy": strategy.name,
              "params": json.dumps({**strategy.params, "hold_bars": strategy.hold_bars,
                                    "exit_on_signal": strategy.exit_on_signal,
                                    "exit_clock_utc": strategy.exit_clock_utc}, sort_keys=True),
              "split": split, "timeframe": timeframe, "cost_percentile": ctx.percentile,
              "data_sha256": meta["sha256"], **git_state(ctx.root),
              **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in m.items()}}
    if trials_path is not None:
        log_trial(ctx.root / trials_path, record)
    return {"trades": trades, "metrics": m, "yearly": yearly(trades), "record": record}
