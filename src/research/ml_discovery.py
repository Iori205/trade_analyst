"""Data-driven strategy search: triple-barrier labels + ML, walk-forward inside the TRAIN split only.

Validation and test are never read: H1 bars come from read_bars(..., "train") and M1 from
read_m1_split(..., "train"); labels whose horizon would end after the train split are dropped.

Labels (per H1 bar i; decision at its close, entry = open of bar i+1)
  TP / SL = multiples of ATR(14, H1) at bar i: (TP, SL) in {(1,1), (1.5,1), (2,1), (2,1.5)}
  horizon in {4, 8, 24} hours; long and short separately -> 24 variants.
  The M1 path (bid high / low) from the entry minute decides which barrier is hit first;
  if both are hit in the same minute it counts as SL. No barrier: exit at the last M1 close
  before the horizon. A label is censored (dropped) if its window has an M1 gap > 30 min
  (weekend, holiday, data gap) or ends after the train split.
  Target y = 1 if TP was hit first.

Features (only information up to the close of bar i): entry hour, weekday, session, month-end
day, 1/4/24 h returns / ATR, ATR pips and its percentile in the last 30 days, distance to the
H4 EMA50 / ATR (last CLOSED H4 bar), distance to the previous day's and today's Asia high/low
/ ATR, and whether today has broken them so far.

Models: (a) DecisionTree(max_depth=3), (b) HistGradientBoosting. Walk-forward: fit 2015..Y-1,
predict Y for Y = 2018..2021; training rows whose entry is within one horizon of the test start
are embargoed. Trade when p*TP - (1-p)*SL - cost_for(entry) > 0, one position at a time, with
the engine's entry rules (contiguous clean next bar, not rollover / weekly open / closed).

Run:
    .venv/bin/python -m src.research.ml_discovery
"""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import platform
from math import erf, exp, log, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.engine import (
    BARS_DIR, COST_CONFIG, COST_DIR, TRIALS, git_state, log_trial, metrics,
)
from src.data.bars import bar_file, read_bars
from src.data.cost_model import CostModel, load_cost_config
from src.data.inventory import sha256_file
from src.data.splits import DEFAULT_SPLITS, load_splits, read_m1_split
from src.research.exploratory_stats import bh_qvalues, last_weekday_of_month, session_of

PIP = 1e-4
NS_MIN = 60_000_000_000
NS_H = 60 * NS_MIN
BARRIERS = [(1.0, 1.0), (1.5, 1.0), (2.0, 1.0), (2.0, 1.5)]
HORIZONS_H = [4, 8, 24]
DIRECTIONS = {"long": 1, "short": -1}
TEST_YEARS = [2018, 2019, 2020, 2021]
FIRST_YEAR = 2015
MAX_GAP_MIN = 30
ATR_N = 14
RANDOM_RUNS = 100
SEED = 20261104
MODELS = ("tree", "hgb")
M1_PATH = Path("data/processed/eurusd_m1/v1/eurusd_m1_utc.parquet")
FEATURES = ["hour_utc", "weekday", "session", "month_end", "ret_1h_atr", "ret_4h_atr", "ret_24h_atr", "atr_pips",
            "atr_pct_30d", "ema50_h4_dist_atr", "prev_high_dist_atr", "prev_low_dist_atr", "prev_high_broken",
            "prev_low_broken", "asia_high_dist_atr", "asia_low_dist_atr", "asia_high_broken", "asia_low_broken"]
SESSION_CODE = {"asia": 0, "london": 1, "ny": 2, "other": 3}
SCRIPTS = ["src/research/ml_discovery.py", "src/backtest/engine.py", "src/data/cost_model.py"]


def variant_name(direction: str, tp: float, sl: float, h: int) -> str:
    return f"{direction}_tp{tp:g}_sl{sl:g}_h{h}"


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------
def atr(h1: pd.DataFrame, n: int = ATR_N) -> pd.Series:
    prev = h1["close"].shift(1)
    tr = pd.concat([h1["high"] - h1["low"], (h1["high"] - prev).abs(), (h1["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def h4_ema_at(h1: pd.DataFrame, n: int = 50) -> pd.Series:
    """EMA(n) of closed H4 closes, as known at the close of each H1 bar (NaN until n H4 bars)."""
    start = h1["bar_start_utc"]
    block = start.dt.floor("4h")
    h4 = h1.groupby(block)["close"].last().rename("close").to_frame()
    h4["available"] = h4.index + pd.Timedelta(hours=4)          # all of the block's bars have closed by then
    ema = h4["close"].ewm(span=n, adjust=False).mean()
    h4["ema"] = ema.where(np.arange(len(h4)) >= n - 1)
    known = pd.DataFrame({"t": start + pd.Timedelta(hours=1)}).reset_index()
    merged = pd.merge_asof(known.sort_values("t"), h4[["available", "ema"]].sort_values("available"),
                           left_on="t", right_on="available", direction="backward")
    return merged.set_index("index")["ema"].reindex(h1.index)


def features(h1: pd.DataFrame) -> pd.DataFrame:
    """One row per H1 bar i (decision at its close). h1 must be sorted with a default RangeIndex."""
    h1 = h1.reset_index(drop=True)
    start = h1["bar_start_utc"]
    entry = start + pd.Timedelta(hours=1)
    a = atr(h1)
    close = h1["close"]
    by_time = pd.Series(close.to_numpy(), index=start)
    f = pd.DataFrame(index=h1.index)
    f["hour_utc"] = entry.dt.hour
    f["weekday"] = entry.dt.dayofweek
    f["session"] = pd.Series(session_of(entry.dt.hour), index=h1.index).map(SESSION_CODE)
    f["month_end"] = last_weekday_of_month(pd.DatetimeIndex(entry.dt.tz_convert(None).dt.normalize())).astype(int)
    for k in (1, 4, 24):
        past = by_time.reindex(start - pd.Timedelta(hours=k)).to_numpy()
        f[f"ret_{k}h_atr"] = (close.to_numpy() - past) / a.to_numpy()
    f["atr_pips"] = a / PIP
    f["atr_pct_30d"] = pd.Series(a.to_numpy(), index=start).rolling("30D").rank(pct=True).to_numpy()
    f["ema50_h4_dist_atr"] = (close - h4_ema_at(h1)) / a

    date = start.dt.normalize()
    daily = h1.groupby(date).agg(day_high=("high", "max"), day_low=("low", "min"))
    prev = daily.shift(1)
    prev_high, prev_low = date.map(prev["day_high"]), date.map(prev["day_low"])
    today_high = h1["high"].groupby(date).cummax()
    today_low = h1["low"].groupby(date).cummin()
    f["prev_high_dist_atr"] = (close - prev_high) / a
    f["prev_low_dist_atr"] = (close - prev_low) / a
    f["prev_high_broken"] = (today_high > prev_high).astype(float).where(prev_high.notna())
    f["prev_low_broken"] = (today_low < prev_low).astype(float).where(prev_low.notna())

    hour = start.dt.hour
    asia = h1[hour < 7].groupby(date[hour < 7]).agg(asia_high=("high", "max"), asia_low=("low", "min"))
    done = hour >= 6                                     # the 06:00 bar closes at 07:00: Asia is complete
    asia_high, asia_low = date.map(asia["asia_high"]).where(done), date.map(asia["asia_low"]).where(done)
    post = hour >= 7
    post_high = h1["high"].where(post).groupby(date).cummax()
    post_low = h1["low"].where(post).groupby(date).cummin()
    f["asia_high_dist_atr"] = (close - asia_high) / a
    f["asia_low_dist_atr"] = (close - asia_low) / a
    f["asia_high_broken"] = (post_high > asia_high).astype(float).where(asia_high.notna())
    f["asia_low_broken"] = (post_low < asia_low).astype(float).where(asia_low.notna())
    return f[FEATURES]


def candidates(h1: pd.DataFrame, cost_model: CostModel, percentile: str) -> pd.DataFrame:
    """Entry candidates with the engine's entry rules: bar i+1 contiguous, clean, not blocked by cost_for flags."""
    h1 = h1.reset_index(drop=True)
    nxt = h1.shift(-1)
    t_e = h1["bar_start_utc"] + pd.Timedelta(hours=1)
    contiguous = nxt["bar_start_utc"].eq(t_e)
    flagged = h1["any_gap"].astype(bool) | h1["any_flag"].astype(bool)
    clean = ~flagged.shift(-1, fill_value=True)
    cost = cost_model.cost_for(pd.DatetimeIndex(t_e), percentile)
    blocked = (cost["is_rollover"] | cost["is_weekly_open"] | cost["is_market_closed"]).to_numpy()
    a = atr(h1)
    return pd.DataFrame({"signal_start": h1["bar_start_utc"], "entry_time": t_e, "entry_price": nxt["open"],
                         "atr": a, "cost_pips": cost["total_pips"].to_numpy(),
                         "eligible": contiguous & clean & ~blocked & a.notna()})


# ---------------------------------------------------------------------------
# Triple-barrier labels on the M1 path
# ---------------------------------------------------------------------------
def first_hit(mask: np.ndarray) -> int:
    i = int(np.argmax(mask)) if len(mask) else 0
    return i if len(mask) and mask[i] else 10 ** 9


def triple_barrier(cands: pd.DataFrame, m1: pd.DataFrame, end_ns: int) -> dict:
    """Labels for every (direction, TP, SL, horizon) variant.

    Returns {variant: DataFrame(valid, y, ret_pips, outcome, exit_ns)} aligned with `cands`.
    """
    mt = m1["timestamp_utc"].astype("int64").to_numpy()
    mh, ml, mc = m1["high"].to_numpy(float), m1["low"].to_numpy(float), m1["close"].to_numpy(float)
    n = len(cands)
    t_e = cands["entry_time"].astype("int64").to_numpy()
    price, a, ok = cands["entry_price"].to_numpy(float), cands["atr"].to_numpy(float), cands["eligible"].to_numpy()
    tps = sorted({b[0] for b in BARRIERS})
    sls = sorted({b[1] for b in BARRIERS})
    out = {}
    for d in DIRECTIONS:
        for tp, sl in BARRIERS:
            for h in HORIZONS_H:
                out[variant_name(d, tp, sl, h)] = {"valid": np.zeros(n, bool), "y": np.zeros(n, np.int8),
                                                   "ret_pips": np.full(n, np.nan), "outcome": np.full(n, "", object),
                                                   "exit_ns": np.zeros(n, np.int64)}
    max_h = max(HORIZONS_H) * NS_H
    for i in np.flatnonzero(ok):
        s = int(np.searchsorted(mt, t_e[i]))
        e = int(np.searchsorted(mt, t_e[i] + max_h))
        if s >= len(mt) or mt[s] - t_e[i] > MAX_GAP_MIN * NS_MIN:
            continue
        hh, ll, tt = mh[s:e], ml[s:e], mt[s:e]
        gaps = np.diff(tt)
        first = {}
        for d, sign in DIRECTIONS.items():
            for m in tps:
                level = price[i] + sign * m * a[i]
                first[(d, "tp", m)] = first_hit(hh >= level) if sign > 0 else first_hit(ll <= level)
            for m in sls:
                level = price[i] - sign * m * a[i]
                first[(d, "sl", m)] = first_hit(ll <= level) if sign > 0 else first_hit(hh >= level)
        for h in HORIZONS_H:
            cutoff = t_e[i] + h * NS_H
            if cutoff > end_ns:
                continue
            k = int(np.searchsorted(tt, cutoff))
            if k == 0 or (k > 1 and gaps[:k - 1].max() > MAX_GAP_MIN * NS_MIN) or cutoff - tt[k - 1] > MAX_GAP_MIN * NS_MIN:
                continue
            for d, sign in DIRECTIONS.items():
                for tp, sl in BARRIERS:
                    v = out[variant_name(d, tp, sl, h)]
                    ft, fs = first[(d, "tp", tp)], first[(d, "sl", sl)]
                    v["valid"][i] = True
                    if fs < k and fs <= ft:
                        v["ret_pips"][i], v["outcome"][i], v["exit_ns"][i] = -sl * a[i] / PIP, "sl", tt[fs] + NS_MIN
                    elif ft < k:
                        v["ret_pips"][i], v["outcome"][i], v["exit_ns"][i] = tp * a[i] / PIP, "tp", tt[ft] + NS_MIN
                        v["y"][i] = 1
                    else:
                        v["ret_pips"][i] = sign * (mc[s + k - 1] - price[i]) / PIP
                        v["outcome"][i], v["exit_ns"][i] = "time", cutoff
    return {name: pd.DataFrame(v) for name, v in out.items()}


# ---------------------------------------------------------------------------
# Walk-forward, trading rule, random baseline
# ---------------------------------------------------------------------------
def make_model(kind: str):
    if kind == "tree":
        from sklearn.tree import DecisionTreeClassifier
        return DecisionTreeClassifier(max_depth=3, min_samples_leaf=200, random_state=0)
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=100,
                                          l2_regularization=1.0, early_stopping=False, random_state=0)


def fold_masks(entry_time: pd.Series, valid: np.ndarray, test_year: int, horizon_h: int) -> tuple[np.ndarray, np.ndarray]:
    """Train: entries from 2015 up to test start minus the embargo (one horizon). Test: entries in the test year."""
    test_start = pd.Timestamp(f"{test_year}-01-01", tz="UTC")
    test_end = pd.Timestamp(f"{test_year + 1}-01-01", tz="UTC")
    train = valid & (entry_time >= pd.Timestamp(f"{FIRST_YEAR}-01-01", tz="UTC")).to_numpy() \
        & (entry_time < test_start - pd.Timedelta(hours=horizon_h)).to_numpy()
    test = valid & ((entry_time >= test_start) & (entry_time < test_end)).to_numpy()
    return train, test


def walk_forward(X: pd.DataFrame, lab: pd.DataFrame, entry_time: pd.Series, horizon_h: int, kind: str) -> tuple[np.ndarray, list]:
    """Out-of-fold P(TP first) for the test years (NaN elsewhere) and the fitted models per fold."""
    p = np.full(len(X), np.nan)
    fitted = []
    valid = lab["valid"].to_numpy()
    for year in TEST_YEARS:
        tr, te = fold_masks(entry_time, valid, year, horizon_h)
        model = make_model(kind)
        model.fit(X[tr], lab["y"].to_numpy()[tr])
        if te.any():
            p[te] = model.predict_proba(X[te])[:, 1]
        fitted.append((year, model, tr, te))
    return p, fitted


def select_trades(order_idx: np.ndarray, entry_ns: np.ndarray, exit_ns: np.ndarray) -> list[int]:
    """Take candidates in time order, one position at a time (next entry at or after the previous exit)."""
    taken, free_at = [], -1
    for i in order_idx:
        if entry_ns[i] >= free_at:
            taken.append(int(i))
            free_at = exit_ns[i]
    return taken


def trades_frame(idx: list[int], cands: pd.DataFrame, lab: pd.DataFrame, direction: str) -> pd.DataFrame:
    t = pd.DataFrame({"direction": direction, "entry_time": cands["entry_time"].iloc[idx].reset_index(drop=True),
                      "exit_time": pd.to_datetime(lab["exit_ns"].to_numpy()[idx], utc=True),
                      "gross_pips": lab["ret_pips"].to_numpy()[idx], "cost_pips": cands["cost_pips"].to_numpy()[idx],
                      "outcome": lab["outcome"].to_numpy()[idx]})
    t["net_pips"] = t["gross_pips"] - t["cost_pips"]
    return t


def rule_trades(p: np.ndarray, cands: pd.DataFrame, lab: pd.DataFrame, tp: float, sl: float, direction: str) -> pd.DataFrame:
    a_pips = cands["atr"].to_numpy() / PIP
    ev = p * tp * a_pips - (1 - p) * sl * a_pips - cands["cost_pips"].to_numpy()
    want = np.flatnonzero(lab["valid"].to_numpy() & ~np.isnan(p) & (ev > 0))
    entry_ns = cands["entry_time"].astype("int64").to_numpy()
    idx = select_trades(want[np.argsort(entry_ns[want], kind="mergesort")], entry_ns, lab["exit_ns"].to_numpy())
    return trades_frame(idx, cands, lab, direction)


def random_trades(rng, pool: np.ndarray, n_target: int, entry_ns: np.ndarray, exit_ns: np.ndarray) -> list[int]:
    """Random non-overlapping entries from `pool` until n_target are taken (or the pool is exhausted)."""
    starts, ends, taken = [], [], []
    for i in rng.permutation(pool):
        if len(taken) >= n_target:
            break
        s, e = entry_ns[i], exit_ns[i]
        j = bisect.bisect_left(starts, s)
        if (j > 0 and ends[j - 1] > s) or (j < len(starts) and starts[j] < e):
            continue
        starts.insert(j, s)
        ends.insert(j, e)
        taken.append(int(i))
    return sorted(taken, key=lambda i: entry_ns[i])


def random_baseline(model_trades: pd.DataFrame, cands: pd.DataFrame, lab: pd.DataFrame, direction: str,
                    seed: int, runs: int = RANDOM_RUNS) -> pd.DataFrame:
    """Same direction, barriers, horizon and entry rules; random timing with the model's trade count per test year."""
    rng = np.random.default_rng(seed)
    entry_ns = cands["entry_time"].astype("int64").to_numpy()
    exit_ns = lab["exit_ns"].to_numpy()
    years = cands["entry_time"].dt.year.to_numpy()
    valid = lab["valid"].to_numpy()
    per_year = model_trades["entry_time"].dt.year.value_counts().to_dict()
    rows = []
    for r in range(runs):
        idx = []
        for y in TEST_YEARS:
            pool = np.flatnonzero(valid & (years == y))
            idx += random_trades(rng, pool, per_year.get(y, 0), entry_ns, exit_ns)
        t = trades_frame(idx, cands, lab, direction)
        rows.append({"run": r, "trades": len(t), "expectancy_pips": float(t["net_pips"].mean()) if len(t) else np.nan})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Multiple-testing corrections
# ---------------------------------------------------------------------------
def norm_cdf(x: float) -> float:
    return 0.5 * (1 + erf(x / sqrt(2)))


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation, |error| < 1.2e-9)."""
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02,
         -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01,
         -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00,
         4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    lo = 0.02425
    if p < lo:
        q = sqrt(-2 * log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - lo:
        return -norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def deflated_sharpe(sr: float, n_obs: int, skew: float, kurt: float, sr_trials: np.ndarray) -> float:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014): P(true SR > expected max SR of N unskilled trials).

    sr: per-trade Sharpe of the candidate; sr_trials: per-trade Sharpes of all N trials; kurt: non-excess kurtosis.
    """
    trials = np.asarray(sr_trials, float)
    trials = trials[np.isfinite(trials)]
    n = len(trials)
    if n < 2 or n_obs < 3 or not np.isfinite(sr):
        return np.nan
    g = 0.5772156649
    sr0 = sqrt(trials.var(ddof=1)) * ((1 - g) * norm_ppf(1 - 1 / n) + g * norm_ppf(1 - 1 / (n * exp(1))))
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    return norm_cdf((sr - sr0) * sqrt(n_obs - 1) / sqrt(denom)) if denom > 0 else np.nan


def trade_stats(t: pd.DataFrame) -> dict:
    x = t["net_pips"].to_numpy(float)
    n = len(x)
    sd = x.std(ddof=1) if n > 1 else np.nan
    sr = x.mean() / sd if n > 1 and sd > 0 else np.nan
    z = x - x.mean() if n else x
    skew = float((z ** 3).mean() / x.std() ** 3) if n > 2 and x.std() > 0 else 0.0
    kurt = float((z ** 4).mean() / x.std() ** 4) if n > 3 and x.std() > 0 else 3.0
    t_stat = sr * sqrt(n) if np.isfinite(sr) else np.nan
    # one-sided: H1 = expectancy > 0 (the search looks for profitable rules; significant losers are not findings)
    return {"sr_trade": sr, "skew": skew, "kurt": kurt, "t": t_stat, "p": 1 - norm_cdf(t_stat) if np.isfinite(t_stat) else np.nan}


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def load(root: Path) -> dict:
    splits = load_splits(root / DEFAULT_SPLITS)
    cfg = load_cost_config(root / COST_CONFIG)
    cost_model = CostModel.load(root / COST_DIR, cfg)
    percentile = cfg["trading_costs"]["spread_percentile"]
    h1 = read_bars(root / BARS_DIR, "H1", "train", splits).sort_values("bar_start_utc").reset_index(drop=True)
    m1, _ = read_m1_split(root / M1_PATH, "train", splits, ["timestamp_utc", "high", "low", "close", "utc_unresolved"])
    m1 = m1[~m1["utc_unresolved"]].drop_duplicates("timestamp_utc", keep="first").sort_values("timestamp_utc")
    train = splits["train"]
    for name, t in (("H1", h1["bar_start_utc"]), ("M1", m1["timestamp_utc"])):
        if not ((t >= train.start) & (t < train.end)).all():
            raise AssertionError(f"{name} data outside the train split")
    return {"splits": splits, "cost_model": cost_model, "percentile": percentile, "h1": h1, "m1": m1.reset_index(drop=True),
            "end_ns": int(train.end.value), "train": train}


def analyse(d: dict, progress=print) -> dict:
    h1 = d["h1"]
    X = features(h1)
    cands = candidates(h1, d["cost_model"], d["percentile"])
    progress("labelling ...")
    labels = triple_barrier(cands, d["m1"], d["end_ns"])
    rows, oof, models, randoms = [], {}, {}, {}
    oof_start = pd.Timestamp(f"{TEST_YEARS[0]}-01-01", tz="UTC")
    oof_end = pd.Timestamp(f"{TEST_YEARS[-1] + 1}-01-01", tz="UTC")
    for vi, (name, lab) in enumerate(labels.items()):
        direction, tp, sl, h = name.split("_")[0], *[float(x[2:]) for x in name.split("_")[1:3]], int(name.split("_h")[1])
        for kind in MODELS:
            progress(f"{name} {kind}")
            p, fitted = walk_forward(X, lab, cands["entry_time"], h, kind)
            t = rule_trades(p, cands, lab, tp, sl, direction)
            m = metrics(t, oof_start, oof_end)
            st = trade_stats(t)
            rnd = random_baseline(t, cands, lab, direction, SEED + 1000 * vi + MODELS.index(kind))
            key = f"{kind}_{name}"
            oof[key], models[key], randoms[key] = t, fitted, rnd
            yearly = t.groupby(t["entry_time"].dt.year)["net_pips"].agg(["size", "mean"]) if len(t) else pd.DataFrame()
            base = lab["valid"].to_numpy() & cands["entry_time"].between(oof_start, oof_end, inclusive="left").to_numpy()
            rows.append({"variant": key, "model": kind, "direction": direction, "tp_atr": tp, "sl_atr": sl, "horizon_h": h,
                         "labelled_oof": int(base.sum()), "tp_rate_oof": float(lab["y"].to_numpy()[base].mean()),
                         **{k: m.get(k, np.nan) for k in ("trades", "win_rate", "avg_win_pips", "avg_loss_pips",
                                                          "expectancy_pips", "total_pips", "max_drawdown_pips",
                                                          "sharpe_daily", "t_stat", "mean_cost_pips")},
                         **st,
                         **{f"exp_{y}": (float(yearly.loc[y, "mean"]) if y in yearly.index else np.nan) for y in TEST_YEARS},
                         **{f"n_{y}": (int(yearly.loc[y, "size"]) if y in yearly.index else 0) for y in TEST_YEARS},
                         "random_median": float(rnd["expectancy_pips"].median()),
                         "random_p95": float(rnd["expectancy_pips"].quantile(0.95)),
                         "random_below": int((rnd["expectancy_pips"] < m.get("expectancy_pips", np.nan)).sum())})
    res = pd.DataFrame(rows)
    res["q_bh"] = bh_qvalues(res["p"])
    srs = res["sr_trade"].to_numpy()
    res["dsr"] = [deflated_sharpe(r.sr_trade, int(r.trades or 0), r.skew, r.kurt, srs) for r in res.itertuples()]
    res["years_positive"] = res[[f"exp_{y}" for y in TEST_YEARS]].gt(0).sum(axis=1)
    return {"results": res, "oof": oof, "models": models, "randoms": randoms, "X": X, "cands": cands, "labels": labels}


def importance_and_rules(a: dict, top: list[str]) -> tuple[pd.DataFrame, dict]:
    from sklearn.inspection import permutation_importance
    from sklearn.tree import export_text
    X, rows, rules = a["X"], [], {}
    for key in top:
        model_kind, name = key.split("_", 1)
        lab = a["labels"][name]
        for year, model, tr, te in a["models"][key]:
            if te.sum() < 50:
                continue
            pi = permutation_importance(model, X[te], lab["y"].to_numpy()[te], scoring="neg_log_loss",
                                        n_repeats=5, random_state=0)
            rows += [{"variant": key, "test_year": year, "feature": f, "importance": float(v)}
                     for f, v in zip(FEATURES, pi.importances_mean)]
        tree_key = f"tree_{name}"
        last = a["models"][tree_key][-1][1]
        rules[name] = export_text(last, feature_names=FEATURES, decimals=3, show_weights=True)
    imp = pd.DataFrame(rows)
    imp = imp.groupby(["variant", "feature"])["importance"].mean().reset_index().sort_values(
        ["variant", "importance"], ascending=[True, False])
    return imp, rules


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def fmt(v) -> str:
    if isinstance(v, (float, np.floating)):
        return "–" if np.isnan(v) else (f"{v:.2e}" if 0 < abs(v) < 1e-3 else f"{v:,.3f}" if abs(v) < 1000 else f"{v:,.0f}")
    return str(v)


def md_table(df: pd.DataFrame) -> str:
    head = "| " + " | ".join(map(str, df.columns)) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "\n".join("| " + " | ".join(fmt(v) for v in r) + " |" for r in df.itertuples(index=False))


def charts(res: pd.DataFrame, top: list[str], out: Path) -> None:
    from src.backtest.baselines import AQUA, BASE, BLUE, INK2, ORANGE, SURFACE, _plt, _save
    plt = _plt()
    r = res.sort_values("expectancy_pips").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8, 9))
    y = np.arange(len(r))
    ax.hlines(y, r["random_median"], r["random_p95"], color="#c3c2b7", lw=3, label="random: median to p95")
    ax.scatter(r["expectancy_pips"], y, s=22, color=[BLUE if m == "tree" else ORANGE for m in r["model"]], zorder=3)
    ax.axvline(0, color=BASE, lw=0.8)
    ax.set_yticks(y, r["variant"], fontsize=7)
    ax.set_xlabel("out-of-fold expectancy 2018-2021, pips per trade after costs")
    ax.set_title("48 variants (blue = tree, orange = gradient boosting) vs matched random", loc="left")
    ax.legend(frameon=False, loc="lower right")
    _save(fig, out / "variants.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    w = 0.26
    for k, (key, color) in enumerate(zip(top, (BLUE, ORANGE, AQUA))):
        vals = res.set_index("variant").loc[key, [f"exp_{yr}" for yr in TEST_YEARS]].to_numpy(float)
        ax.bar(np.arange(len(TEST_YEARS)) + (k - 1) * w, vals, width=w, color=color, edgecolor=SURFACE, label=key)
    ax.axhline(0, color=BASE, lw=0.8)
    ax.set_xticks(range(len(TEST_YEARS)), TEST_YEARS)
    ax.set_ylabel("expectancy (pips per trade)")
    ax.set_title("Top 3 variants by year (out-of-fold)", loc="left")
    ax.legend(frameon=False, fontsize=7)
    ax.tick_params(axis="x", colors=INK2)
    _save(fig, out / "top3_by_year.png")
    plt.close(fig)


def render_summary(a: dict, imp: pd.DataFrame, rules: dict, top: list[str], info: dict) -> str:
    res = a["results"]
    cols = ["variant", "trades", "expectancy_pips", "t_stat", "p", "q_bh", "dsr", "win_rate", "years_positive",
            "random_median", "random_p95", "random_below"]
    best = res.set_index("variant").loc[top].reset_index()
    sig = res[res["q_bh"] < 0.05]
    beat = res[res["random_below"] >= 95]
    lines = [
        "# ML discovery: triple-barrier labels + walk-forward, train split 2015-2021",
        "",
        f"Generated {info['created_utc']} by `src/research/ml_discovery.py` (HEAD `{(info['git_commit'] or '')[:7]}`, "
        f"uncommitted script changes: {str(info['git_dirty']).lower()}). scikit-learn {info['sklearn']}.",
        "",
        "- **Data:** TRAIN split only (H1 bars and M1 path). Validation and test were not read. Labels whose horizon would end after 2021-12-31 were dropped.",
        f"- **Variants:** {len(res)} = 24 labels (4 TP/SL × 3 horizons × long/short) × 2 models. {info['trial_note']}",
        "- **Results below:** out-of-fold only (2018-2021), from an expanding-window walk-forward with an embargo of one horizon.",
        f"- **Trade rule:** trade when p·TP − (1−p)·SL − cost_for > 0, one position at a time, with the engine's entry rules. Cost = `cost_for` at {info['percentile']} + 0.6 commission + 0.2 slippage.",
        "",
        "## Top 3 variants (ranked by OOF t-stat)",
        "",
        md_table(best[cols]),
        "",
        "Expectancy by year (pips per trade; number of trades in brackets):",
        "",
        md_table(pd.DataFrame([{"variant": k, **{str(y): f"{fmt(res.set_index('variant').loc[k, f'exp_{y}'])} ({res.set_index('variant').loc[k, f'n_{y}']})" for y in TEST_YEARS}} for k in top])),
        "",
        "## Multiple-testing correction",
        "",
        f"- **BH-FDR across all {len(res)} variants** (one-sided p, H1: expectancy > 0): {len(sig)} with q < 0.05" + (f": {', '.join(sig['variant'])}." if len(sig) else "."),
        f"- **Deflated Sharpe Ratio:** N = {int(res['sr_trade'].notna().sum())} trials with a defined per-trade Sharpe (≥ 2 trades) out of {len(res)}. The best is {res['dsr'].max():.3f}. DSR > 0.95 would mean the result is unlikely to come from the best of N unskilled trials.",
        f"  - Sensitivity for {top[0]}: variants with very few trades have noisy Sharpe values, which inflate V[SR]. Estimating V[SR] only from variants with ≥ 30 trades gives DSR {dsr_subset(res, top[0], 30):.3f}; with ≥ 100 trades, {dsr_subset(res, top[0], 100):.3f}.",
        f"- **Matched random baseline:** same direction, barriers, horizon and entry rules, with random timing and the same number of trades per year, run {RANDOM_RUNS} times. {len(beat)} variants beat at least 95 of the 100 random runs" + (f": {', '.join(beat['variant'])}." if len(beat) else "."),
        "",
        f"- **Beating random is a low bar:** random timing loses about the cost on every trade. {int(((res['random_below'] >= 95) & (res['expectancy_pips'] <= 0)).sum())} of the {len(beat)} variants that beat random still have expectancy ≤ 0. In those variants the model's timing is better than chance, but not good enough to pay for the costs.",
        f"- **{int((res['trades'] == 0).sum())} variants made no trades:** for every bar in the out-of-fold years, p·TP − (1−p)·SL − cost ≤ 0.",
        "",
        "## Verdict",
        "",
        info["verdict"],
        "",
        "## All variants",
        "",
        "Full table: `variants.csv`. Chart: `charts/variants.png`.",
        "",
        md_table(res.sort_values("t_stat", ascending=False)[cols]),
        "",
        "## Feature importance (top 3 variants)",
        "",
        "Permutation importance on each out-of-fold test year (drop in negative log-loss), averaged over the years. The top 8 per variant:",
        "",
        md_table(imp.groupby("variant").head(8)),
        "",
        "## Decision-tree rules (depth 3, trained 2015-2020; the last fold)",
        "",
    ]
    for name, txt in rules.items():
        lines += [f"**{name}** (class 1 = TP first; weights = training samples per class)", "", "```", txt.rstrip(), "```", ""]
    lines += [
        "## Method notes and limitations",
        "",
        "- **Labels:** these use bid M1 high/low.",
        "  - A barrier fills exactly at its level. A gap through the level, which would give a worse fill, is not modelled.",
        "  - If both barriers are hit in the same minute, the outcome counts as SL.",
        "  - A window with an M1 gap over 30 minutes (weekend, holiday) is not labelled.",
        "- **Target:** y = TP hit first. Time exits count as y = 0 in the model, but the backtest uses their actual return.",
        "- **Features:** computed only from bars that have closed. The H4 EMA uses H4 blocks that have finished.",
        "- **Embargo:** training entries within one horizon before the test year are removed, so their label windows cannot overlap the test year.",
        "- **Models:** fixed hyper-parameters, no tuning.",
        "  - Tree: max_depth 3, min_samples_leaf 200.",
        "  - HGB: 200 iterations, learning rate 0.05, 15 leaves, min_samples_leaf 100, L2 1.0, no early stopping, random_state 0.",
        "- **Cost:** charged once per trade at entry.",
        f"- **Trial log:** it now has {info['trials_total']} rows. Selecting the best of these {len(res)} variants for validation is itself a selection, and the DSR above accounts for that.",
    ]
    return "\n".join(lines) + "\n"


def dsr_subset(res: pd.DataFrame, key: str, min_trades: int) -> float:
    """DSR of `key` with V[SR] and N taken only from variants with at least min_trades trades (sensitivity)."""
    r = res.set_index("variant").loc[key]
    srs = res.loc[res["trades"] >= min_trades, "sr_trade"].to_numpy()
    return deflated_sharpe(r["sr_trade"], int(r["trades"]), r["skew"], r["kurt"], srs)


def verdict(res: pd.DataFrame, top: list[str]) -> str:
    t = res.set_index("variant").loc[top]
    sig = int((res["q_bh"] < 0.05).sum())
    checks = pd.DataFrame({"BH q < 0.05": t["q_bh"] < 0.05, "DSR > 0.95": t["dsr"] > 0.95,
                           ">= 95/100 random": t["random_below"] >= 95,
                           "positive all 4 years": t["years_positive"] == len(TEST_YEARS), "trades >= 100": t["trades"] >= 100})
    rows = [f"- **{k}:** " + ", ".join(f"{c} {'yes' if v else 'no'}" for c, v in r.items()) for k, r in checks.iterrows()]
    good = checks.all(axis=1)
    best = checks.sum(axis=1).idxmax()
    failed = [c for c, v in checks.loc[best].items() if not v]
    if good.any():
        head = (f"{int(good.sum())} of the top 3 pass every check: {', '.join(checks.index[good])}. These are candidates for a "
                "single validation run with every rule fixed now.")
    elif len(failed) == 1:
        head = (f"None of the top 3 passes every check. {sig} of {len(res)} variants are significant after BH-FDR (one-sided). "
                f"The closest is **{best}**. It fails only \"{failed[0]}\" (DSR {t.loc[best, 'dsr']:.2f}; the sensitivity above "
                f"gives up to {dsr_subset(res, best, 100):.2f}). So it is significant on its own, but not convincing once we allow "
                f"for having picked the best of the trials. A single validation run of this one variant, with every rule and "
                "hyper-parameter fixed now and nothing else tested, would settle it. Whether to spend validation on it is "
                "your decision. The other variants are not candidates.")
    else:
        head = (f"None of the top 3 passes every check. {sig} of {len(res)} variants are significant after BH-FDR (one-sided). "
                "The search found no robust edge on train, so spending validation on these variants is not recommended.")
    return head + "\n\nChecks for the top 3:\n\n" + "\n".join(rows)


def run(root: Path = Path("."), reports_dir: Path = Path("reports"), stamp: str | None = None,
        trials_path: Path | None = TRIALS, note: str = "") -> dict:
    import sklearn
    root = Path(root)
    stamp = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = root / reports_dir / f"ml_discovery_{stamp}"
    if out.exists():
        raise FileExistsError(f"{out} exists")
    d = load(root)
    a = analyse(d)
    res = a["results"]
    top = list(res.sort_values("t_stat", ascending=False)["variant"].head(3))
    imp, rules = importance_and_rules(a, top)
    gs = git_state(root)
    data_sha = sha256_file(root / BARS_DIR / bar_file("H1", "train"))
    if trials_path is not None:
        for r in res.itertuples():
            log_trial(root / trials_path, {
                "run_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "strategy": f"ml_tb_{r.variant}",
                "params": json.dumps({"model": r.model, "direction": r.direction, "tp_atr": r.tp_atr, "sl_atr": r.sl_atr,
                                      "horizon_h": r.horizon_h, "atr": ATR_N, "walk_forward": "expanding, test 2018-2021",
                                      "embargo_h": r.horizon_h, "rule": "p*TP-(1-p)*SL-cost>0"}, sort_keys=True),
                "split": "train (OOF 2018-2021)", "timeframe": "H1", "cost_percentile": d["percentile"],
                "data_sha256": data_sha, **gs,
                **{k: (round(float(getattr(r, k)), 6) if pd.notna(getattr(r, k)) else None)
                   for k in ("trades", "win_rate", "avg_win_pips", "avg_loss_pips", "expectancy_pips", "total_pips",
                             "max_drawdown_pips", "sharpe_daily", "t_stat", "mean_cost_pips")}})
    trials_total = sum(1 for _ in open(root / TRIALS, encoding="utf-8")) - 1 if (root / TRIALS).exists() else 0
    trial_note = (f"All {len(res)} were added to `reports/trials/trials.csv`." if trials_path is not None else
                  f"This is a report-only re-run. The {len(res)} trials were already logged by an earlier run, so they were not logged again.")
    info = {"trial_note": trial_note,"created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **gs,
            "sklearn": sklearn.__version__, "percentile": d["percentile"], "trials_total": trials_total,
            "verdict": verdict(res, top)}
    out.mkdir(parents=True)
    (out / "charts").mkdir()
    for name, df in (("variants", res), ("feature_importance", imp)):
        with open(out / f"{name}.csv", "x", encoding="utf-8", newline="") as h:
            df.to_csv(h, index=False, float_format="%.6g", lineterminator="\n")
    with open(out / "tree_rules.txt", "x", encoding="utf-8") as h:
        h.write("\n\n".join(f"== {k} ==\n{v}" for k, v in rules.items()))
    for key in top:
        with open(out / f"trades_{key}.csv", "x", encoding="utf-8", newline="") as h:
            a["oof"][key].to_csv(h, index=False, float_format="%.6g", lineterminator="\n")
    charts(res, top, out / "charts")
    with open(out / "summary.md", "x", encoding="utf-8") as h:
        h.write((note + "\n\n" if note else "") + render_summary(a, imp, rules, top, info))
    with open(out / "run.json", "x", encoding="utf-8") as h:
        json.dump({**info, "top3": top, "features": FEATURES, "barriers": BARRIERS, "horizons_h": HORIZONS_H,
                   "test_years": TEST_YEARS, "random_runs": RANDOM_RUNS, "seed": SEED,
                   "inputs_sha256": {"h1_train": data_sha},
                   "scripts_sha256": {s: sha256_file(root / s) for s in SCRIPTS},
                   "environment": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                                   "sklearn": sklearn.__version__}}, h, indent=2, default=str)
    return {**a, "top": top, "out_dir": out, "info": info}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-trial-log", action="store_true",
                        help="report-only re-run of trials that are already logged (same code and data)")
    parser.add_argument("--note", default="", help="text put at the top of summary.md")
    args = parser.parse_args()
    r = run(trials_path=None if args.no_trial_log else TRIALS, note=args.note)
    print(r["results"].sort_values("t_stat", ascending=False).head(5)[["variant", "trades", "expectancy_pips", "t_stat", "q_bh", "dsr"]])
    print(f"written: {r['out_dir']}")


if __name__ == "__main__":
    main()
