"""Exploratory statistics on the TRAIN split (2015-2021) of the M15 / H1 bars.

Validation and test are never read: bars come from read_bars(..., "train", ...)
and every frame is checked to lie inside the train range. Bars with any_gap or
any_flag are dropped. A bar's return is close - open, in pips.

Families of tests (one BH / FDR correction over all of them):
  1. hour_weekday   mean return and P(up) per UTC weekday x hour (H1)
  2. autocorr       lag 1-8 autocorrelation, M15 and H1, all bars and per session
  3. big_moves      H1 returns 1, 4, 24 hours after a bar with |return| > p95, by direction
  4. sessions       Asia / London / NY session returns: correlation and sign agreement
  5. month_end      London 15:00-17:00 window (4pm fix) on the last weekday of the month vs other days

p-values use the normal approximation (large samples), heteroskedasticity-robust
statistics for correlations, day-clustered errors for overlapping forward returns,
and seeded permutation tests for the small month-end sample.
Each row also carries move/cost and edge/cost ratios, with the cost from
CostModel.cost_for at the default spread percentile (p75).

Run:
    .venv/bin/python -m src.research.exploratory_stats
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import subprocess
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.cost_model import CostModel, load_cost_config
from src.data.inventory import sha256_file
from src.data.splits import DEFAULT_SPLITS, load_splits
from src.data.bars import bar_file, read_bars

PIP = 1e-4
TF_MINUTES = {"M15": 15, "H1": 60}
SESSIONS = {"asia": (0, 7), "london": (7, 12), "ny": (12, 21)}   # UTC hours [start, end)
LAGS = range(1, 9)
HORIZONS = (1, 4, 24)
FIX_WINDOW_LONDON = ("15:00", "17:00")
MIN_CELL = 30
N_PERM = 20000
SEED = 20261102
ALPHA = 0.05
BARS_DIR = Path("data/processed/eurusd_bars/v1")
COST_DIR = Path("data/processed/cost_model/v1")
COST_CONFIG = Path("config/cost_model_v1.yaml")
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SCRIPTS = ["src/research/exploratory_stats.py", "src/data/cost_model.py", "src/data/bars.py", "src/data/splits.py"]


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def p_normal(z: float) -> float:
    return float(erfc(abs(z) / sqrt(2))) if np.isfinite(z) else np.nan


def bh_qvalues(p) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (q-values); NaN p stays NaN and is not counted."""
    p = np.asarray(p, dtype=float)
    q = np.full(p.shape, np.nan)
    ok = np.flatnonzero(~np.isnan(p))
    m = len(ok)
    if m == 0:
        return q
    order = ok[np.argsort(p[ok], kind="mergesort")]
    ranked = p[order] * m / np.arange(1, m + 1)
    q[order] = np.minimum(1.0, np.minimum.accumulate(ranked[::-1])[::-1])
    return q


def mean_test(x) -> dict:
    x = np.asarray(x, dtype=float)
    n = len(x)
    se = x.std(ddof=1) / sqrt(n) if n > 1 else np.nan
    z = x.mean() / se if n > 1 and se > 0 else np.nan
    return {"n": n, "estimate": float(x.mean()) if n else np.nan, "z": z, "p": p_normal(z)}


def cluster_mean_test(x, clusters) -> dict:
    """Mean vs 0 with cluster-robust (e.g. per-day) standard error."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 2:
        return {"n": n, "estimate": np.nan, "z": np.nan, "p": np.nan}
    e = pd.Series(x - x.mean()).groupby(np.asarray(clusters)).sum()
    g = len(e)
    se = sqrt((e ** 2).sum() * g / max(g - 1, 1)) / n
    z = x.mean() / se if se > 0 else np.nan
    return {"n": n, "estimate": float(x.mean()), "z": z, "p": p_normal(z), "clusters": g}


def sign_test(x) -> dict:
    """P(x > 0) vs 0.5 among non-zero values (normal approximation to the binomial)."""
    x = np.asarray(x, dtype=float)
    nz = x[x != 0]
    n = len(nz)
    up = int((nz > 0).sum())
    z = (up - n / 2) / sqrt(n / 4) if n else np.nan
    return {"n": n, "estimate": up / n if n else np.nan, "z": z, "p": p_normal(z)}


def robust_corr(x, y) -> dict:
    """Correlation with a heteroskedasticity-robust test of zero: z = sum(xy) / sqrt(sum(x^2 y^2))."""
    x = np.asarray(x, dtype=float) - np.mean(x)
    y = np.asarray(y, dtype=float) - np.mean(y)
    n = len(x)
    denom = sqrt((x ** 2).sum() * (y ** 2).sum())
    rho = float((x * y).sum() / denom) if denom > 0 else np.nan
    v = sqrt(((x * y) ** 2).sum())
    z = float((x * y).sum() / v) if v > 0 else np.nan
    return {"n": n, "estimate": rho, "z": z, "p": p_normal(z), "se": abs(rho / z) if z else np.nan}


def perm_mean_diff(a, b, rng, n_perm: int = N_PERM) -> dict:
    """Two-sided permutation test of mean(a) - mean(b)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    pooled = np.concatenate([a, b])
    obs = a.mean() - b.mean()
    na = len(a)
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        hits += abs(pooled[:na].mean() - pooled[na:].mean()) >= abs(obs) - 1e-12
    return {"n": na, "n_other": len(b), "estimate": float(obs), "z": np.nan, "p": (hits + 1) / (n_perm + 1)}


def signflip_mean(a, rng, n_perm: int = N_PERM) -> dict:
    """Two-sided sign-flip permutation test of mean(a) = 0."""
    a = np.asarray(a, float)
    obs = a.mean()
    signs = rng.choice([-1.0, 1.0], size=(n_perm, len(a)))
    hits = int((np.abs((signs * a).mean(axis=1)) >= abs(obs) - 1e-12).sum())
    return {"n": len(a), "estimate": float(obs), "z": np.nan, "p": (hits + 1) / (n_perm + 1)}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def clean_bars(bars: pd.DataFrame) -> pd.DataFrame:
    b = bars[~bars["any_gap"] & ~bars["any_flag"]].copy()
    b["ret"] = ((b["close"] - b["open"]) / PIP).round(6)
    return b.sort_values("bar_start_utc").reset_index(drop=True)


def load_train(bars_dir: Path, timeframe: str, splits) -> tuple[pd.DataFrame, int]:
    train = splits["train"]
    raw = read_bars(bars_dir, timeframe, "train", splits)   # guarded; never validation or test
    if not ((raw["bar_start_utc"] >= train.start) & (raw["bar_start_utc"] < train.end)).all():
        raise AssertionError("bars outside the train range")
    return clean_bars(raw), len(raw)


def session_of(hours) -> np.ndarray:
    hours = np.asarray(hours)
    out = np.full(hours.shape, "other", dtype=object)
    for name, (lo, hi) in SESSIONS.items():
        out[(hours >= lo) & (hours < hi)] = name
    return out


def lag_pairs(b: pd.DataFrame, k: int, minutes: int) -> pd.DataFrame:
    """Pairs (x = return k bars earlier, y = return) where both clean bars exist exactly k*minutes apart."""
    prev = b[["bar_start_utc", "ret"]].rename(columns={"ret": "x"})
    prev["bar_start_utc"] = prev["bar_start_utc"] + pd.Timedelta(minutes=k * minutes)
    return b[["bar_start_utc", "ret"]].rename(columns={"ret": "y"}).merge(prev, on="bar_start_utc", how="inner")


def forward_returns(b: pd.DataFrame, horizon_bars: int, minutes: int) -> pd.Series:
    """close(t + h) - close(t) in pips, indexed like b; NaN when the target bar is missing or unclean."""
    target = b["bar_start_utc"] + pd.Timedelta(minutes=horizon_bars * minutes)
    close = b.set_index("bar_start_utc")["close"]
    return pd.Series(((close.reindex(target).to_numpy() - b["close"].to_numpy()) / PIP).round(6), index=b.index)


def session_returns(h1: pd.DataFrame) -> pd.DataFrame:
    """One row per UTC date (Mon-Fri) with each session's close(last) - open(first), only if every hour is clean."""
    h = h1.assign(date=h1["bar_start_utc"].dt.normalize(), hour=h1["bar_start_utc"].dt.hour)
    h = h[h["bar_start_utc"].dt.dayofweek < 5]
    cols = {}
    for name, (lo, hi) in SESSIONS.items():
        s = h[(h["hour"] >= lo) & (h["hour"] < hi)].groupby("date")
        agg = s.agg(n=("ret", "size"), first_open=("open", "first"), last_close=("close", "last"))
        full = agg[agg["n"] == hi - lo]
        cols[name] = ((full["last_close"] - full["first_open"]) / PIP).round(6)
    return pd.DataFrame(cols).sort_index()


def last_weekday_of_month(dates: pd.DatetimeIndex) -> np.ndarray:
    d = pd.DatetimeIndex(dates)
    month_end = d + pd.offsets.MonthEnd(0)
    last = month_end - pd.to_timedelta(np.maximum(month_end.dayofweek - 4, 0), unit="D")
    return np.asarray(d.normalize() == last.normalize())


def fix_window_returns(m15: pd.DataFrame, start_utc, end_utc) -> pd.DataFrame:
    """London 15:00-17:00 window per weekday, converted to UTC with London DST; all 8 M15 bars must be clean."""
    days = pd.date_range(pd.Timestamp(start_utc).tz_convert(None).normalize(),
                         pd.Timestamp(end_utc).tz_convert(None).normalize(), freq="D")
    days = days[days.dayofweek < 5]
    lo, hi = FIX_WINDOW_LONDON
    w_start = pd.DatetimeIndex([pd.Timestamp(f"{d.date()} {lo}", tz="Europe/London") for d in days]).tz_convert("UTC")
    w_end = pd.DatetimeIndex([pd.Timestamp(f"{d.date()} {hi}", tz="Europe/London") for d in days]).tz_convert("UTC")
    n_bars = int((w_end[0] - w_start[0]) / pd.Timedelta(minutes=15)) if len(days) else 0
    m = m15.set_index("bar_start_utc")
    rows = []
    for d, s, e in zip(days, w_start, w_end):
        if s < start_utc or e > end_utc:
            continue
        w = m.loc[(m.index >= s) & (m.index < e)]
        if len(w) != n_bars:
            continue
        rows.append({"date": d, "window_start_utc": s, "ret": round((w["close"].iloc[-1] - w["open"].iloc[0]) / PIP, 6)})
    out = pd.DataFrame(rows)
    if len(out):
        out["month_end"] = last_weekday_of_month(pd.DatetimeIndex(out["date"]))
    return out


# ---------------------------------------------------------------------------
# Families
# ---------------------------------------------------------------------------
def row(family, test_id, description, res, unit, move=np.nan, edge=np.nan, cost=np.nan, **extra) -> dict:
    return {"family": family, "test_id": test_id, "description": description, "n": res.get("n"),
            "estimate": res.get("estimate"), "unit": unit, "z": res.get("z"), "p": res.get("p"),
            "move_pips": move, "edge_pips": edge, "cost_pips": cost, **extra}


def hour_weekday(h1: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    g = h1.assign(weekday=h1["bar_start_utc"].dt.dayofweek, hour=h1["bar_start_utc"].dt.hour)
    table, tests = [], []
    for (wd, hr), c in g.groupby(["weekday", "hour"]):
        if len(c) < MIN_CELL:
            continue
        r = c["ret"].to_numpy()
        mt, st = mean_test(r), sign_test(r)
        move, cost = float(np.median(np.abs(r))), float(c["cost"].median())
        cell = f"{WEEKDAYS[wd]} {hr:02d}"
        table.append({"weekday": wd, "weekday_name": WEEKDAYS[wd], "hour_utc": hr, "n": len(r),
                      "mean_pips": mt["estimate"], "p_up": st["estimate"], "std_pips": float(r.std(ddof=1)),
                      "median_abs_pips": move, "cost_pips": cost, "move_cost": move / cost,
                      "edge_cost": abs(mt["estimate"]) / cost, "p_mean": mt["p"], "p_up_test": st["p"]})
        tests.append(row("hour_weekday", f"mean {cell}", f"H1 mean return, {cell}:00 UTC", mt, "pips",
                         move, abs(mt["estimate"]), cost))
        tests.append(row("hour_weekday", f"p_up {cell}", f"H1 P(up), {cell}:00 UTC", st, "probability",
                         move, abs(mt["estimate"]), cost))
    return pd.DataFrame(table), tests


def autocorr(bars: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, list[dict]]:
    table, tests = [], []
    for tf, b in bars.items():
        cost = b.set_index("bar_start_utc")["cost"]
        for k in LAGS:
            pairs = lag_pairs(b, k, TF_MINUTES[tf])
            pairs["session"] = session_of(pairs["bar_start_utc"].dt.hour)
            for sess in ("all", *SESSIONS):
                p = pairs if sess == "all" else pairs[pairs["session"] == sess]
                res = robust_corr(p["x"], p["y"])
                edge = float(np.mean(np.sign(p["x"]) * p["y"]))
                move = float(np.median(np.abs(p["y"])))
                c = float(cost.reindex(p["bar_start_utc"]).median())
                table.append({"timeframe": tf, "lag": k, "session": sess, "n": res["n"], "rho": res["estimate"],
                              "se": res["se"], "p": res["p"], "edge_pips": edge, "move_pips": move, "cost_pips": c})
                tests.append(row("autocorr", f"{tf} lag{k} {sess}", f"{tf} return autocorrelation, lag {k}, {sess}",
                                 res, "rho", move, abs(edge), c, sign_rule_edge_pips=edge))
    return pd.DataFrame(table), tests


def big_moves(h1: pd.DataFrame) -> tuple[pd.DataFrame, list[dict], float]:
    threshold = float(np.quantile(np.abs(h1["ret"]), 0.95))
    trig = np.abs(h1["ret"]) > threshold
    cost_next = h1.set_index("bar_start_utc")["cost"]
    table, tests = [], []
    for k in HORIZONS:
        fwd = forward_returns(h1, k, 60)
        for direction, mask in (("up", trig & (h1["ret"] > 0)), ("down", trig & (h1["ret"] < 0))):
            sel = mask & fwd.notna()
            f = fwd[sel].to_numpy()
            dates = h1.loc[sel, "bar_start_utc"].dt.normalize().to_numpy()
            res = cluster_mean_test(f, dates)
            entry = h1.loc[sel, "bar_start_utc"] + pd.Timedelta(hours=1)
            c = float(cost_next.reindex(entry).median()) if sel.any() else np.nan
            if np.isnan(c):
                c = float(h1["cost"].median())
            cont = f if direction == "up" else -f   # positive = continuation
            move = float(np.median(np.abs(f)))
            table.append({"horizon_h": k, "direction": direction, "n": res["n"], "clusters": res.get("clusters"),
                          "mean_fwd_pips": res["estimate"], "continuation_pips": float(cont.mean()),
                          "se": abs(res["estimate"] / res["z"]) if res["z"] else np.nan, "p": res["p"],
                          "p_continue": float((cont > 0).mean()), "median_abs_fwd_pips": move, "cost_pips": c})
            tests.append(row("big_moves", f"after {direction} +{k}h",
                             f"H1 return {k}h after a {direction} bar with |ret| > p95 ({threshold:.1f} pips)",
                             res, "pips", move, abs(res["estimate"]), c))
    return pd.DataFrame(table), tests, threshold


def sessions_family(sess: pd.DataFrame, cost_model: CostModel) -> tuple[pd.DataFrame, list[dict]]:
    pairs = {"asia->london": ("asia", "london", 0), "london->ny": ("london", "ny", 0),
             "asia->ny": ("asia", "ny", 0), "ny->next asia": ("ny", "asia", 1)}
    table, tests = [], []
    for name, (a, b, shift) in pairs.items():
        nxt = sess[b].dropna()
        prv = sess[a].dropna()
        if shift:   # next trading day = the next later date that has a full `b` session
            idx = np.searchsorted(nxt.index.to_numpy(), prv.index.to_numpy(), side="right")
            ok = idx < len(nxt)
            df = pd.DataFrame({"x": prv.to_numpy()[ok], "y": nxt.to_numpy()[idx[ok]],
                               "next_date": nxt.index.to_numpy()[idx[ok]]})
        else:
            j = pd.concat([prv.rename("x"), nxt.rename("y")], axis=1).dropna()
            df = j.reset_index().rename(columns={"index": "next_date", "date": "next_date"})
        entry = pd.DatetimeIndex(df["next_date"]) + pd.Timedelta(hours=SESSIONS[b][0])
        c = float(cost_model.cost_for(entry)["total_pips"].median())
        corr = robust_corr(df["x"], df["y"])
        agree = sign_test(np.sign(df["x"]) * np.sign(df["y"]))
        edge = float(np.mean(np.sign(df["x"]) * df["y"]))
        move = float(np.median(np.abs(df["y"])))
        table.append({"pair": name, "n": corr["n"], "corr": corr["estimate"], "se": corr["se"], "p_corr": corr["p"],
                      "p_same_sign": agree["estimate"], "p_sign_test": agree["p"], "edge_pips": edge,
                      "median_abs_next_pips": move, "cost_pips": c})
        tests.append(row("sessions", f"corr {name}", f"correlation of {a} and {'next ' if shift else ''}{b} session returns",
                         corr, "rho", move, abs(edge), c, sign_rule_edge_pips=edge))
        tests.append(row("sessions", f"same sign {name}", f"P(same sign) {a} -> {'next ' if shift else ''}{b}",
                         agree, "probability", move, abs(edge), c, sign_rule_edge_pips=edge))
    return pd.DataFrame(table), tests


def month_end_family(fix: pd.DataFrame, cost_model: CostModel, rng) -> tuple[pd.DataFrame, list[dict]]:
    me, other = fix[fix["month_end"]], fix[~fix["month_end"]]
    c = float(cost_model.cost_for(pd.DatetimeIndex(me["window_start_utc"]))["total_pips"].median())
    move = float(np.median(np.abs(me["ret"])))
    edge = abs(float(me["ret"].mean()))
    t_abs = perm_mean_diff(np.abs(me["ret"]), np.abs(other["ret"]), rng)
    t_sign = signflip_mean(me["ret"], rng)
    t_diff = perm_mean_diff(me["ret"], other["ret"], rng)
    table = pd.DataFrame([
        {"group": g, "n": len(x), "mean_abs_pips": float(np.abs(x["ret"]).mean()),
         "median_abs_pips": float(np.median(np.abs(x["ret"]))), "mean_pips": float(x["ret"].mean()),
         "std_pips": float(x["ret"].std(ddof=1)), "p_up": float((x["ret"] > 0).mean())}
        for g, x in (("month_end", me), ("other_weekdays", other))])
    tests = [
        row("month_end", "abs move month-end vs other", "London 15-17 |return|: last weekday of month minus other days",
            t_abs, "pips", move, np.nan, c),
        row("month_end", "signed month-end vs 0", "London 15-17 mean return on the last weekday of month",
            t_sign, "pips", move, edge, c),
        row("month_end", "signed month-end vs other", "London 15-17 mean return: month-end minus other days",
            t_diff, "pips", move, edge, c),
    ]
    return table, tests


def bid_mid_check(fxcm_dir: Path) -> pd.DataFrame:
    """Hourly bid vs mid returns in the FXCM reference weeks (all weekdays pooled, plus Friday).

    HistData prices are bid. When the spread widens or narrows inside an hour, the bid moves by
    about half that change even if the mid does not, so bid returns at those hours are partly spread.
    """
    from src.data.fxcm_audit import read_fxcm_csv
    frames = [read_fxcm_csv(p).assign(file=str(p.relative_to(fxcm_dir)))
              for p in sorted(fxcm_dir.glob("m1/EURUSD/*/*.csv.gz"))]
    d = pd.concat(frames, ignore_index=True)
    d["t"] = d["timestamp_label"].dt.tz_localize("UTC")
    h = (d.set_index("t").groupby(["file", pd.Grouper(freq="h")])
         .agg(bo=("bid_open", "first"), bc=("bid_close", "last"), ao=("ask_open", "first"), ac=("ask_close", "last"))
         .dropna().reset_index())
    h["bid_ret"] = (h["bc"] - h["bo"]) / PIP
    h["mid_ret"] = ((h["bc"] + h["ac"]) - (h["bo"] + h["ao"])) / 2 / PIP
    h["spread_change"] = ((h["ac"] - h["bc"]) - (h["ao"] - h["bo"])) / PIP
    h["hour_utc"], h["friday"] = h["t"].dt.hour, h["t"].dt.dayofweek == 4
    rows = []
    for label, sub in (("all weekdays", h), ("Friday", h[h["friday"]])):
        g = sub.groupby("hour_utc").agg(n=("bid_ret", "size"), bid_ret=("bid_ret", "mean"), mid_ret=("mid_ret", "mean"),
                                        spread_change=("spread_change", "mean")).reset_index()
        rows.append(g.assign(days=label, bid_minus_mid=g["bid_ret"] - g["mid_ret"]))
    return pd.concat(rows, ignore_index=True)


def analyse(bars: dict[str, pd.DataFrame], fix: pd.DataFrame, cost_model: CostModel) -> dict:
    rng = np.random.default_rng(SEED)
    hw, t1 = hour_weekday(bars["H1"])
    ac, t2 = autocorr(bars)
    bm, t3, threshold = big_moves(bars["H1"])
    sess_table = session_returns(bars["H1"])
    ss, t4 = sessions_family(sess_table, cost_model)
    me, t5 = month_end_family(fix, cost_model, rng)
    findings = pd.DataFrame(t1 + t2 + t3 + t4 + t5)
    findings["q_bh"] = bh_qvalues(findings["p"])
    findings["significant_fdr"] = findings["q_bh"] < ALPHA
    findings["move_cost"] = findings["move_pips"] / findings["cost_pips"]
    findings["edge_cost"] = findings["edge_pips"] / findings["cost_pips"]
    findings["move_cost_gt2"] = findings["move_cost"] > 2
    findings["edge_cost_gt2"] = findings["edge_cost"] > 2
    return {"findings": findings, "hour_weekday": hw, "autocorr": ac, "big_moves": bm, "big_move_threshold": threshold,
            "sessions": ss, "session_returns": sess_table, "month_end": me, "fix_windows": fix}


# ---------------------------------------------------------------------------
# Charts (static PNG, light surface; reference palette of the dataviz method)
# ---------------------------------------------------------------------------
INK, INK2, MUTED, GRID, BASE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE, ORANGE = "#2a78d6", "#eb6834"
DIVERGING = ["#184f95", "#3987e5", "#9ec5f4", "#f0efec", "#f4b3ad", "#e34948", "#a8231f"]
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": BASE,
                         "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
                         "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.6, "font.size": 9,
                         "axes.titlesize": 10, "axes.titleweight": "bold", "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.dpi": 150, "svg.hashsalt": "fixed"})
    return plt


def _save(fig, path: Path) -> None:
    with open(path, "xb") as handle:
        fig.savefig(handle, format="png", bbox_inches="tight", metadata={"Software": None})


def chart_heatmap(hw: pd.DataFrame, value: str, title: str, path: Path, diverging: bool, marks=None) -> None:
    plt = _plt()
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm, Normalize
    days = sorted(hw["weekday"].unique())
    grid = hw.pivot(index="hour_utc", columns="weekday", values=value).reindex(index=range(24), columns=days)
    fig, ax = plt.subplots(figsize=(1.0 * len(days) + 2.2, 7.2))
    if diverging:
        lim = float(np.nanmax(np.abs(grid.to_numpy()))) or 1.0
        cmap, norm = LinearSegmentedColormap.from_list("div", DIVERGING), TwoSlopeNorm(0, -lim, lim)
    else:
        cmap, norm = LinearSegmentedColormap.from_list("seq", SEQUENTIAL), Normalize(np.nanmin(grid.to_numpy()), np.nanmax(grid.to_numpy()))
    cmap.set_bad(SURFACE)
    im = ax.imshow(grid.to_numpy(), aspect="auto", cmap=cmap, norm=norm)
    for (i, j), v in np.ndenumerate(grid.to_numpy()):
        if np.isfinite(v):
            light = abs(norm(v) - 0.5) > 0.3 if diverging else norm(v) > 0.5
            label = f"{v:.2f}" if abs(v) < 10 else f"{v:.0f}"
            star = "*" if marks is not None and marks.get((days[j], i)) else ""
            ax.text(j, i, label + star, ha="center", va="center", fontsize=7, color=SURFACE if light else INK)
    ax.set_xticks(range(len(days)), [WEEKDAYS[d] for d in days])
    ax.set_yticks(range(24), [f"{h:02d}" for h in range(24)])
    ax.set_ylabel("UTC hour (bar start)")
    ax.set_title(title, loc="left")
    cb = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.02)
    cb.outline.set_visible(False)
    _save(fig, path)
    plt.close(fig)


def chart_autocorr(ac: pd.DataFrame, findings: pd.DataFrame, path: Path) -> None:
    plt = _plt()
    sig = set(findings.loc[(findings["family"] == "autocorr") & findings["significant_fdr"], "test_id"])
    sessions = ["all", *SESSIONS]
    fig, axes = plt.subplots(2, len(sessions), figsize=(12, 5.2), sharey=True)
    for i, tf in enumerate(TF_MINUTES):
        for j, sess in enumerate(sessions):
            ax = axes[i, j]
            d = ac[(ac["timeframe"] == tf) & (ac["session"] == sess)].sort_values("lag")
            colors = [BLUE if f"{tf} lag{k} {sess}" in sig else "#9ec5f4" for k in d["lag"]]
            band = 1.96 * d["se"].median()
            ax.fill_between([0.5, 8.5], -band, band, color=GRID, lw=0, zorder=0)
            ax.bar(d["lag"], d["rho"], color=colors, width=0.6, edgecolor=SURFACE, linewidth=1, zorder=2)
            ax.axhline(0, color=BASE, lw=0.8)
            ax.set_xticks(list(LAGS))
            ax.set_title(f"{tf} · {sess}", loc="left", fontsize=9)
            if j == 0:
                ax.set_ylabel("autocorrelation")
            if i == 1:
                ax.set_xlabel("lag (bars)")
    fig.suptitle("Return autocorrelation, train 2015-2021 (dark bar = significant after FDR; band = ±1.96 robust SE)",
                 x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    _save(fig, path)
    plt.close(fig)


def chart_big_moves(bm: pd.DataFrame, threshold: float, path: Path) -> None:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(HORIZONS))
    for off, (direction, color) in zip((-0.17, 0.17), (("up", BLUE), ("down", ORANGE))):
        d = bm[bm["direction"] == direction].set_index("horizon_h").reindex(list(HORIZONS))
        ax.bar(x + off, d["mean_fwd_pips"], width=0.32, color=color, label=f"after {direction} bar",
               edgecolor=SURFACE, linewidth=1)
        ax.errorbar(x + off, d["mean_fwd_pips"], yerr=1.96 * d["se"], fmt="none", ecolor=INK2, elinewidth=1, capsize=3)
    ax.axhline(0, color=BASE, lw=0.8)
    ax.set_xticks(x, [f"+{h}h" for h in HORIZONS])
    ax.set_ylabel("mean forward return (pips)")
    ax.set_title(f"H1 return after a bar with |return| > p95 ({threshold:.1f} pips), 95% CI (day-clustered)", loc="left")
    ax.legend(frameon=False)
    _save(fig, path)
    plt.close(fig)


def chart_sessions(ss: pd.DataFrame, path: Path) -> None:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7, 3.4))
    y = np.arange(len(ss))
    ax.barh(y, ss["corr"], color=BLUE, height=0.5, edgecolor=SURFACE)
    ax.errorbar(ss["corr"], y, xerr=1.96 * ss["se"], fmt="none", ecolor=INK2, elinewidth=1, capsize=3)
    ax.axvline(0, color=BASE, lw=0.8)
    ax.set_yticks(y, ss["pair"])
    ax.invert_yaxis()
    ax.set_xlabel("correlation of session returns (95% CI, robust)")
    ax.set_title("Does one session's return predict the next?", loc="left")
    _save(fig, path)
    plt.close(fig)


def chart_month_end(fix: pd.DataFrame, path: Path) -> None:
    plt = _plt()
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    groups = (("month-end", fix[fix["month_end"]]["ret"], BLUE), ("other weekdays", fix[~fix["month_end"]]["ret"], ORANGE))
    for ax, transform, label in ((axes[0], np.abs, "|return| (pips)"), (axes[1], lambda v: v, "return (pips)")):
        for i, (name, r, color) in enumerate(groups):
            v = transform(r.to_numpy())
            m, se = v.mean(), v.std(ddof=1) / sqrt(len(v))
            ax.bar(i, m, color=color, width=0.5, edgecolor=SURFACE)
            ax.errorbar(i, m, yerr=1.96 * se, fmt="none", ecolor=INK2, elinewidth=1, capsize=3)
        ax.axhline(0, color=BASE, lw=0.8)
        ax.set_xticks([0, 1], [f"{g[0]}\n(n={len(g[1])})" for g in groups])
        ax.set_ylabel(f"mean {label}")
    fig.suptitle("London 15:00-17:00 window (4pm fix), mean ± 95% CI", x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    _save(fig, path)
    plt.close(fig)


def chart_pvalues(findings: pd.DataFrame, path: Path) -> None:
    plt = _plt()
    p = np.sort(findings["p"].dropna().to_numpy())
    m = len(p)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(np.arange(1, m + 1), p, color=BLUE, lw=2, label="sorted p-values")
    ax.plot(np.arange(1, m + 1), ALPHA * np.arange(1, m + 1) / m, color=ORANGE, lw=2, label=f"BH line (q = {ALPHA})")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("rank")
    ax.set_ylabel("p-value")
    ax.set_title(f"All {m} tests: p-values vs Benjamini-Hochberg line", loc="left")
    ax.legend(frameon=False)
    _save(fig, path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def md_table(df: pd.DataFrame, floatfmt: str = "{:.3g}") -> str:
    if df.empty:
        return "_none_"
    def fmt(v):
        if isinstance(v, (bool, np.bool_)):
            return "yes" if v else "no"
        if isinstance(v, (float, np.floating)):
            return "–" if np.isnan(v) else (f"{v:.2e}" if 0 < abs(v) < 1e-3 else floatfmt.format(v))
        return str(v)
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "\n".join("| " + " | ".join(fmt(v) for v in r) + " |" for r in df.itertuples(index=False))


FINDING_COLS = ["test_id", "n", "estimate", "unit", "p", "q_bh", "move_pips", "edge_pips", "cost_pips", "move_cost", "edge_cost"]
ROLLOVER_HOURS = {20, 21, 22}


def near_rollover(test_id: str) -> bool:
    parts = test_id.split()
    return parts[0] in ("mean", "p_up") and int(parts[-1]) in ROLLOVER_HOURS


def render_summary(r: dict, run_info: dict, bid_mid: pd.DataFrame) -> str:
    f = r["findings"].copy()
    f["near_rollover_hour"] = f["test_id"].map(near_rollover)
    sig = f[f["significant_fdr"]].sort_values("q_bh")
    move2 = f[f["move_cost_gt2"]]
    both = sig[sig["move_cost_gt2"]]
    strict = sig[sig["edge_cost_gt2"]]
    tests = run_info["tests"]
    fam = ", ".join(f"{k} {v}" for k, v in tests["by_family"].items())
    bm = bid_mid[bid_mid["hour_utc"].isin([20, 21, 22, 23])].round(2)
    me = r["month_end"]
    lines = [
        "# Exploratory statistics: EURUSD train split (2015-2021)",
        "",
        f"Generated {run_info['created_utc']} by `src/research/exploratory_stats.py` "
        f"(HEAD `{(run_info['git_commit'] or '')[:7]}`, uncommitted script changes: {str(run_info['git_dirty']).lower()}).",
        "",
        "- **Data:** TRAIN split only. Validation and test were not read: bars came through the guarded `read_bars(..., \"train\")`, and their range was checked.",
        f"- **Bars used:** M15 {run_info['clean_bars']['M15']:,} of {run_info['raw_bars']['M15']:,}, H1 {run_info['clean_bars']['H1']:,} of {run_info['raw_bars']['H1']:,}. Bars with `any_gap` or `any_flag` were dropped.",
        "- **Return:** close - open of a bar, in pips, from HistData **bid** prices.",
        f"- **Cost:** `cost_for` at p75, i.e. FXCM spread + {run_info['cost']['commission_pips_round_trip']} commission + {run_info['cost']['slippage_pips']} slippage. These are broker assumptions.",
        f"- **Tests:** {tests['total']} in total ({fam}). One Benjamini-Hochberg correction covers all of them, at q < {ALPHA}.",
        "",
        "Ratios:",
        "",
        "- **move/cost** = median |relevant return| / median cost. This is the ratio the task asked for. It measures how far price moves, not whether the direction can be predicted. On H1 almost every cell is above 2, so this criterion alone filters very little.",
        "- **edge/cost** = |expected gain of the simple rule the finding implies| / cost. For example: the mean return for an hour cell; the mean of sign(previous) × next for an autocorrelation or a session pair; the mean forward return after a big move. This stricter ratio is shown alongside.",
        "",
        "## a) Significant after FDR",
        "",
        md_table(sig[FINDING_COLS + ["near_rollover_hour"]]),
        "",
        f"## b) move/cost > 2 ({len(move2)} of {len(f)} tests)",
        "",
        "Count per family: " + ", ".join(f"{k} {int(v)}/{int(n)}" for k, v, n in
                                         zip(f.groupby("family").size().index, f.groupby("family")["move_cost_gt2"].sum(),
                                             f.groupby("family").size())) + ".",
        f"Only {int(f['edge_cost_gt2'].sum())} tests have edge/cost > 2: "
        + (", ".join(f.loc[f["edge_cost_gt2"], "test_id"]) or "none") + ".",
        "",
        "## c) In both a) and b): the most interesting",
        "",
        md_table(both[FINDING_COLS + ["near_rollover_hour"]]),
        "",
        f"Significant **and** edge/cost > 2 (stricter): {len(strict)}. "
        + (", ".join(strict["test_id"]) if len(strict) else "none") + ".",
        "",
        "### How to read these",
        "",
        "- **Hours next to rollover (20-22 UTC) and Friday 21 UTC:** these are bid prices. HistData has no ask, but the FXCM reference weeks (`bid_mid_check.csv`) show the effect.",
        "  - Around rollover the spread first widens, then narrows. When it narrows (22 UTC) the bid rises faster than the mid; when it widens (Friday before the close) the bid falls faster.",
        "  - So part of the significant mean return in these cells is spread, not price.",
        "  - These cells also lose many bars to `any_gap` or `any_flag`. The bars that survive are the cleaner hours, which is a selection effect.",
        "- **Month-end |move|:** volatility in the London 15:00-17:00 (4pm fix) window is much higher on the last weekday of the month. This is a size effect, not a direction. The signed tests tell whether a direction exists.",
        "- **Autocorrelation:** the significant coefficients are small. On M15, lag 1 is about -0.03, with edge/cost well below 1. Statistically real but economically small, and possibly bid-ask bounce or microstructure.",
        "- **Generalisation:** every finding is from 2015-2021 only. Validation (2022-2023) should check them before anything is built on them. Nothing was tested on test data.",
        "",
        "## Bid vs mid around rollover (FXCM reference weeks, pips per H1 bar)",
        "",
        md_table(bm[["days", "hour_utc", "n", "bid_ret", "mid_ret", "bid_minus_mid", "spread_change"]]),
        "",
        "## 1. Hour × weekday (H1)",
        "",
        "Full table: `hour_weekday.csv`. Charts: `charts/hour_weekday_mean.png` and `charts/hour_weekday_move_cost.png`.",
        "",
        md_table(r["hour_weekday"].sort_values("p_mean").head(10)[["weekday_name", "hour_utc", "n", "mean_pips", "p_up", "std_pips", "median_abs_pips", "cost_pips", "move_cost", "edge_cost", "p_mean", "p_up_test"]]),
        "",
        "## 2. Autocorrelation (lag 1-8)",
        "",
        "Full table: `autocorr.csv`. Chart: `charts/autocorr.png`. Rows with p < 0.05 before correction:",
        "",
        md_table(r["autocorr"][r["autocorr"]["p"] < 0.05][["timeframe", "lag", "session", "n", "rho", "p", "edge_pips", "cost_pips"]]),
        "",
        f"## 3. After big moves (H1, |return| > p95 = {r['big_move_threshold']:.1f} pips)",
        "",
        "Chart: `charts/big_moves.png`. Standard errors are clustered by day.",
        "",
        md_table(r["big_moves"][["horizon_h", "direction", "n", "clusters", "mean_fwd_pips", "continuation_pips", "p", "p_continue", "median_abs_fwd_pips", "cost_pips"]]),
        "",
        "## 4. Sessions (Asia 00-07, London 07-12, NY 12-21 UTC)",
        "",
        "Chart: `charts/sessions.png`. A session counts only if all of its H1 bars are clean.",
        "",
        md_table(r["sessions"]),
        "",
        "## 5. Month-end London 4pm fix (London 15:00-17:00 local, converted to UTC with London DST)",
        "",
        "Chart: `charts/month_end.png`. Permutation tests use 20,000 permutations with a fixed seed.",
        "",
        md_table(me),
        "",
        md_table(f[f["family"] == "month_end"][["test_id", "n", "estimate", "p", "q_bh", "move_cost", "edge_cost"]]),
        "",
        "## Method notes",
        "",
        "- **Means and P(up):** normal approximation. Every cell has at least 30 bars.",
        "- **Correlations:** a heteroskedasticity-robust z, sum(xy) / sqrt(sum(x²y²)).",
        "- **Forward returns:** day-clustered standard errors, because the windows of triggers on the same day overlap.",
        "- **Big-move forward returns:** these use the close of the bar k hours later. The bars in between are not required to be clean.",
        "- **Cost:** for a cell or test, the median `cost_for` at the trade's entry time.",
        "- **Sunday bars:** these have their own column in the hour × weekday table. Sessions and month-end use Mon-Fri only.",
        "- **Charts:** `charts/pvalues.png` shows all p-values against the BH line.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def git_state(root: Path) -> dict:
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        return {"git_commit": None, "git_dirty": None}
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", *SCRIPTS],
                           capture_output=True, text=True)
    return {"git_commit": head.stdout.strip(), "git_dirty": bool(dirty.stdout.strip())}


def load_inputs(root: Path) -> tuple[dict, pd.DataFrame, CostModel, dict]:
    splits = load_splits(root / DEFAULT_SPLITS)
    cfg = load_cost_config(root / COST_CONFIG)
    cost_model = CostModel.load(root / COST_DIR, cfg)
    bars, raw_counts = {}, {}
    for tf in TF_MINUTES:
        b, n_raw = load_train(root / BARS_DIR, tf, splits)
        b["cost"] = cost_model.cost_for(pd.DatetimeIndex(b["bar_start_utc"]))["total_pips"].to_numpy()
        bars[tf], raw_counts[tf] = b, n_raw
    train = splits["train"]
    fix = fix_window_returns(bars["M15"], train.start, train.end)
    meta = {"raw_bars": raw_counts, "clean_bars": {tf: len(b) for tf, b in bars.items()},
            "train": {"start_utc": str(train.start), "end_utc_exclusive": str(train.end)},
            "cost": {"percentile": cfg["trading_costs"]["spread_percentile"],
                     "commission_pips_round_trip": cfg["trading_costs"]["commission_pips_round_trip"],
                     "slippage_pips": cfg["trading_costs"]["slippage_pips"]}}
    return bars, fix, cost_model, meta


def write_csv(df: pd.DataFrame, path: Path) -> None:
    with open(path, "x", encoding="utf-8", newline="") as handle:
        df.to_csv(handle, index=False, float_format="%.6g", lineterminator="\n")


def run(root: Path, reports_dir: Path = Path("reports"), stamp: str | None = None) -> dict:
    root = Path(root)
    stamp = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = root / reports_dir / f"exploratory_stats_{stamp}"
    if out.exists():
        raise FileExistsError(f"{out} exists")
    bars, fix, cost_model, meta = load_inputs(root)
    r = analyse(bars, fix, cost_model)
    out.mkdir(parents=True)
    charts = out / "charts"
    charts.mkdir()
    for name in ("findings", "hour_weekday", "autocorr", "big_moves", "sessions", "month_end"):
        write_csv(r[name], out / f"{name}.csv")
    marks = {(int(t.weekday), int(t.hour_utc)): True for t in r["hour_weekday"].itertuples()
             if r["findings"].set_index("test_id").loc[f"mean {WEEKDAYS[t.weekday]} {t.hour_utc:02d}", "significant_fdr"]}
    chart_heatmap(r["hour_weekday"], "mean_pips", "H1 mean return (pips) by UTC weekday x hour (* = significant after FDR)",
                  charts / "hour_weekday_mean.png", diverging=True, marks=marks)
    chart_heatmap(r["hour_weekday"], "move_cost", "Median |H1 move| / round-trip cost (p75)",
                  charts / "hour_weekday_move_cost.png", diverging=False)
    chart_autocorr(r["autocorr"], r["findings"], charts / "autocorr.png")
    chart_big_moves(r["big_moves"], r["big_move_threshold"], charts / "big_moves.png")
    chart_sessions(r["sessions"], charts / "sessions.png")
    chart_month_end(r["fix_windows"], charts / "month_end.png")
    chart_pvalues(r["findings"], charts / "pvalues.png")
    run_info = {
        "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "split": "train only", **meta,
        "inputs_sha256": {**{f"{BARS_DIR}/{bar_file(tf, 'train')}": sha256_file(root / BARS_DIR / bar_file(tf, "train"))
                             for tf in TF_MINUTES},
                          **{f"{COST_DIR}/{n}": sha256_file(root / COST_DIR / n)
                             for n in ("hour_of_week.csv", "segments.csv", "model.json")},
                          str(COST_CONFIG): sha256_file(root / COST_CONFIG)},
        **git_state(root), "scripts_sha256": {s: sha256_file(root / s) for s in SCRIPTS if (root / s).exists()},
        "settings": {"min_cell": MIN_CELL, "n_perm": N_PERM, "seed": SEED, "alpha": ALPHA,
                     "sessions_utc": SESSIONS, "fix_window_london": FIX_WINDOW_LONDON,
                     "big_move_threshold_pips": r["big_move_threshold"]},
        "tests": {"total": int(r["findings"]["p"].notna().sum()),
                  "by_family": r["findings"].groupby("family").size().to_dict()},
        "environment": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                        "matplotlib": __import__("matplotlib").__version__},
    }
    with open(out / "run.json", "x", encoding="utf-8") as handle:
        json.dump(run_info, handle, indent=2, default=str)
    bid_mid = bid_mid_check(root / "data/reference/fxcm/v1")
    write_csv(bid_mid, out / "bid_mid_check.csv")
    with open(out / "summary.md", "x", encoding="utf-8") as handle:
        handle.write(render_summary(r, run_info, bid_mid))
    return {**r, "out_dir": out, "run": run_info}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    r = run(Path.cwd())
    f = r["findings"]
    print(json.dumps({"tests": r["run"]["tests"], "significant_fdr": int(f["significant_fdr"].sum())}, indent=2))
    print(f"written: {r['out_dir']}")


if __name__ == "__main__":
    main()
