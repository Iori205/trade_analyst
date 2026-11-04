"""Candle Range Theory (CRT) v1 on H4 built from M15, TRAIN split, two variants, with a random-direction control.

Rules (frozen by the project owner before any result was seen; never tuned on results):
  H4 blocks: UTC 00/04/08/12/16/20, built from M15 bars.
  C1 = range candle (high1, low1); C2 = the next H4 block.
    Short setup: high2 > high1 and low1 < close2 < high1.
    Long setup:  low2 < low1  and low1 < close2 < high1.
    Both sides swept -> skip.
  Entry: open of C3 (the block after C2). SL: high2 (short) / low2 (long), no buffer.
  v1a: TP = midpoint of C1.  v1b: TP = the opposite side of C1 (low1 short / high1 long).
  Time limit 3 H4 bars (12 h). The M1 path decides which barrier is hit first; same minute = SL.
  No entry in rollover / weekly-open / market-closed periods (cost_for flags) or on a flagged M15 bar.

Implementation choices where the rules are silent (fixed before running, listed in the report):
  - C1, C2 and C3 must be consecutive blocks (C2 = C1 + 4 h, C3 = C2 + 4 h). H4 OHLC comes from the M15
    bars that exist in the block.
  - C3's open = the open of the M15 bar starting exactly at the C3 block start; if that bar is missing,
    flagged (any_gap / any_flag) or blocked, there is no trade.
  - Entry must lie strictly between SL and TP. Otherwise the target was already passed (or SL gapped),
    and the setup is skipped and counted.
  - If the 12 h window has an M1 gap over 30 minutes (weekend, holiday, data gap), the trade is closed at
    the last M1 close before the gap ("gap_exit"). The same applies at the end of the train split.
  - Barrier fills are exactly at the level; gaps through a level are not modelled.
  - One position at a time: the next entry must be at or after the previous exit.
  - Cost: cost_for(entry_time) at p75 + commission + slippage, once per trade.
Control: the same entry times and the same TP / SL distances, with a random direction per trade,
1000 runs (seed fixed). Control trades may overlap, because their exits differ from the strategy's.

Run:
    .venv/bin/python -m src.strategies.crt
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.engine import BARS_DIR, TRIALS, git_state, load_context, log_trial, metrics, yearly
from src.data.bars import bar_file, read_bars
from src.data.inventory import sha256_file
from src.data.splits import read_m1_split
from src.research.ml_discovery import M1_PATH, first_hit, trade_stats

PIP = 1e-4
NS_MIN = 60_000_000_000
H4 = pd.Timedelta(hours=4)
HORIZON = pd.Timedelta(hours=12)
MAX_GAP_MIN = 30
CONTROL_RUNS = 1000
CONTROL_SEED = 20261106
VARIANTS = {"v1a": "midpoint", "v1b": "opposite"}
FROZEN = {"h4_blocks_utc": [0, 4, 8, 12, 16, 20], "source": "M15", "entry": "C3 open", "sl": "C2 extreme, no buffer",
          "tp": VARIANTS, "time_limit_h": 12, "same_minute": "SL", "skip_both_sides_swept": True}


# ---------------------------------------------------------------------------
# Setups
# ---------------------------------------------------------------------------
def h4_blocks(m15: pd.DataFrame) -> pd.DataFrame:
    b = m15.sort_values("bar_start_utc")
    key = b["bar_start_utc"].dt.floor("4h")
    g = b.groupby(key)
    return pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                         "close": g["close"].last(), "bars": g.size()}).rename_axis("block_start").reset_index()


def find_setups(h4: pd.DataFrame) -> pd.DataFrame:
    """C1/C2 pairs of consecutive blocks with a valid one-sided sweep; C3 start = C2 start + 4 h."""
    c1 = h4.rename(columns=lambda c: f"{c}1" if c != "block_start" else "c1_start")
    c2 = h4.rename(columns=lambda c: f"{c}2" if c != "block_start" else "c2_start")
    c1["c2_start"] = c1["c1_start"] + H4
    s = c1.merge(c2, on="c2_start", how="inner")
    inside = (s["close2"] > s["low1"]) & (s["close2"] < s["high1"])
    up, down = s["high2"] > s["high1"], s["low2"] < s["low1"]
    s["direction"] = np.select([inside & up & ~down, inside & down & ~up], [-1, 1], default=0)
    s["both_swept"] = inside & up & down
    s["c3_start"] = s["c2_start"] + H4
    return s


# ---------------------------------------------------------------------------
# M1 path
# ---------------------------------------------------------------------------
def path_outcome(m1: dict, t_e: int, price: float, direction: int, tp: float, sl: float, end_ns: int) -> tuple:
    """(outcome, ret_pips, exit_ns) for one trade on the M1 bid path; outcome in tp / sl / time / gap_exit / no_data."""
    mt, mh, ml, mc = m1["t"], m1["h"], m1["l"], m1["c"]
    s = int(np.searchsorted(mt, t_e))
    if s >= len(mt) or mt[s] - t_e >= 15 * NS_MIN:
        return "no_data", np.nan, t_e
    cutoff = min(t_e + int(HORIZON.value), end_ns)
    k = int(np.searchsorted(mt, cutoff)) - s                # minutes inside [t_e, cutoff)
    if k <= 0:
        return "no_data", np.nan, t_e
    tt = mt[s:s + k]
    reason = "time"
    big = np.flatnonzero(np.diff(tt) > MAX_GAP_MIN * NS_MIN)
    if len(big):
        k, reason = int(big[0]) + 1, "gap_exit"
        tt = tt[:k]
    elif cutoff - tt[-1] > MAX_GAP_MIN * NS_MIN or cutoff < t_e + int(HORIZON.value):
        reason = "gap_exit"                                 # data stops before the horizon (weekend) or split end
    hh, ll = mh[s:s + k], ml[s:s + k]
    if direction > 0:
        ft, fs = first_hit(hh >= tp), first_hit(ll <= sl)
    else:
        ft, fs = first_hit(ll <= tp), first_hit(hh >= sl)
    if fs < k and fs <= ft:
        return "sl", direction * (sl - price) / PIP, int(tt[fs]) + NS_MIN
    if ft < k:
        return "tp", direction * (tp - price) / PIP, int(tt[ft]) + NS_MIN
    return reason, direction * (mc[s + k - 1] - price) / PIP, (cutoff if reason == "time" else int(tt[k - 1]) + NS_MIN)


def candidates(setups: pd.DataFrame, m15: pd.DataFrame, cost_model, percentile: str) -> pd.DataFrame:
    """Join each setup to its C3 entry bar, with the engine's entry checks and the cost at entry."""
    bars = m15.set_index("bar_start_utc")
    s = setups[setups["direction"] != 0].copy()
    e = bars.reindex(s["c3_start"])
    s["entry_price"] = e["open"].to_numpy()
    s["entry_clean"] = (e["open"].notna() & ~e["any_gap"].fillna(True).astype(bool)
                        & ~e["any_flag"].fillna(True).astype(bool)).to_numpy()
    cost = cost_model.cost_for(pd.DatetimeIndex(s["c3_start"]), percentile)
    s["blocked"] = (cost["is_rollover"] | cost["is_weekly_open"] | cost["is_market_closed"]).to_numpy()
    s["cost_pips"] = cost["total_pips"].to_numpy()
    return s.reset_index(drop=True)


def levels(c: pd.DataFrame, variant: str) -> tuple[np.ndarray, np.ndarray]:
    short = c["direction"] < 0
    sl = np.where(short, c["high2"], c["low2"])
    mid = (c["high1"] + c["low1"]) / 2
    tp = mid.to_numpy() if variant == "v1a" else np.where(short, c["low1"], c["high1"])
    return tp.astype(float), sl.astype(float)


def simulate(c: pd.DataFrame, m1: dict, variant: str, end_ns: int) -> dict:
    """Strategy trades (one position at a time) and, per taken trade, the outcome with the direction flipped."""
    tp, sl = levels(c, variant)
    price, d = c["entry_price"].to_numpy(float), c["direction"].to_numpy()
    geometry = np.where(d < 0, (tp < price) & (price < sl), (sl < price) & (price < tp))
    ok = c["entry_clean"].to_numpy() & ~c["blocked"].to_numpy() & geometry
    t_e = c["c3_start"].astype("int64").to_numpy()
    rows, flipped, free_at = [], [], -1
    for i in np.flatnonzero(ok):
        if t_e[i] < free_at:
            continue
        out, ret, exit_ns = path_outcome(m1, t_e[i], price[i], d[i], tp[i], sl[i], end_ns)
        if out == "no_data":
            continue
        free_at = exit_ns
        tp_dist, sl_dist = abs(tp[i] - price[i]), abs(sl[i] - price[i])
        fd = -d[i]
        f_out, f_ret, f_exit = path_outcome(m1, t_e[i], price[i], fd, price[i] + fd * tp_dist, price[i] - fd * sl_dist, end_ns)
        rows.append({"direction": "long" if d[i] > 0 else "short", "entry_time": c["c3_start"].iloc[i],
                     "exit_time": pd.Timestamp(exit_ns, tz="UTC"), "outcome": out, "gross_pips": ret,
                     "cost_pips": c["cost_pips"].iloc[i], "tp_dist_pips": tp_dist / PIP, "sl_dist_pips": sl_dist / PIP})
        flipped.append(f_ret)
    t = pd.DataFrame(rows, columns=["direction", "entry_time", "exit_time", "outcome", "gross_pips", "cost_pips",
                                    "tp_dist_pips", "sl_dist_pips"])
    t["net_pips"] = t["gross_pips"] - t["cost_pips"]
    t["flipped_net_pips"] = np.asarray(flipped, float) - t["cost_pips"].to_numpy(float)
    counts = {"setups": int(len(c)), "entry_bar_missing_or_flagged": int((~c["entry_clean"]).sum()),
              "blocked_rollover_weekly_open_closed": int((c["entry_clean"] & c["blocked"]).sum()),
              "bad_geometry": int((c["entry_clean"] & ~c["blocked"] & ~geometry).sum()),
              "eligible": int(ok.sum()), "trades": len(t)}
    return {"trades": t, "counts": counts}


def control(trades: pd.DataFrame, runs: int = CONTROL_RUNS, seed: int = CONTROL_SEED) -> np.ndarray:
    """Expectancy of `runs` random-direction versions of the same trades (same entries, same TP/SL distances)."""
    if trades.empty:
        return np.array([])
    rng = np.random.default_rng(seed)
    keep = rng.random((runs, len(trades))) < 0.5
    same, flip = trades["net_pips"].to_numpy(float), trades["flipped_net_pips"].to_numpy(float)
    return np.where(keep, same, flip).mean(axis=1)


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


ROWS = ["trades", "win_rate", "avg_win_pips", "avg_loss_pips", "expectancy_pips", "total_pips", "max_drawdown_pips",
        "sharpe_daily", "t_stat", "mean_cost_pips"]


def charts(res: dict, out: Path) -> None:
    from src.backtest.baselines import AQUA, BASE, BLUE, INK2, MUTED, ORANGE, SURFACE, _plt, _save
    plt = _plt()
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    for ax, (v, r) in zip(axes, res.items()):
        ctrl = r["control"]
        ax.hist(ctrl, bins=40, color="#9ec5f4", edgecolor=SURFACE)
        ax.axvline(np.quantile(ctrl, 0.95), color=INK2, ls="--", lw=1.5)
        ax.axvline(r["metrics"]["expectancy_pips"], color=ORANGE, lw=2.5)
        ax.axvline(0, color=BASE, lw=0.8)
        ax.set_title(f"{v}: CRT (orange) vs random direction (p95 dashed)", loc="left", fontsize=9)
        ax.set_xlabel("expectancy per trade after costs (pips)")
    axes[0].set_ylabel("control runs")
    _save(fig, out / "control.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 3.4))
    for (v, r), color in zip(res.items(), (BLUE, AQUA)):
        t = r["trades"]
        ax.plot(t["exit_time"], t["net_pips"].cumsum(), color=color, lw=2, label=f"{v} after costs")
        ax.plot(t["exit_time"], t["gross_pips"].cumsum(), color=color, lw=0.8, alpha=0.6, label=f"{v} before costs")
    ax.axhline(0, color=BASE, lw=0.8)
    ax.set_ylabel("cumulative pips")
    ax.set_title("CRT v1 on train 2015-2021", loc="left")
    ax.legend(frameon=False, ncols=2, fontsize=8)
    ax.tick_params(colors=MUTED)
    _save(fig, out / "equity.png")
    plt.close(fig)


def render(res: dict, info: dict) -> str:
    names = list(res)
    table = pd.DataFrame({"metric": ROWS + ["one-sided p", "control median", "control p95", "control runs below"],
                          **{v: [res[v]["metrics"][k] for k in ROWS]
                             + [res[v]["stats"]["p"], float(np.median(res[v]["control"])),
                                float(np.quantile(res[v]["control"], 0.95)),
                                int((res[v]["control"] < res[v]["metrics"]["expectancy_pips"]).sum())] for v in names}},
                         dtype=object)
    lines = [
        "# Strategy: CRT (Candle Range Theory) v1, train 2015-2021",
        "",
        f"Generated {info['created_utc']} by `src/strategies/crt.py` (HEAD `{(info['git_commit'] or '')[:7]}`, uncommitted script changes: "
        f"{str(info['git_dirty']).lower()}). Data: M15 and M1 from the train split only (M15 SHA-256 `{info['m15_sha'][:16]}…`). Validation and test were not read.",
        "",
        "## Rules (frozen before running)",
        "",
        "- **H4 blocks:** UTC 00/04/08/12/16/20, built from M15. C1 is the range candle; C2 is the next block.",
        "  - Short: high2 > high1 and low1 < close2 < high1.",
        "  - Long: low2 < low1 and low1 < close2 < high1.",
        "  - If both sides are swept, skip.",
        "- **Entry:** C3 open. SL = high2 (short) / low2 (long), with no buffer.",
        "- **TP:** v1a = C1 midpoint; v1b = the opposite side of C1.",
        "- **Exit:** at most 12 h. The M1 path decides which barrier is hit first; if both are hit in the same minute, it counts as SL.",
        "- **No entry** in rollover, weekly-open or closed periods, or on a flagged bar.",
        "",
        "Where the rules are silent, I fixed these choices before running:",
        "",
        "- C1, C2 and C3 must be consecutive blocks.",
        "- C3 open = the M15 bar that starts exactly at the block start.",
        "- The entry price must lie strictly between SL and TP; otherwise the setup is skipped.",
        "- An M1 gap over 30 minutes inside the window (weekend or holiday) closes the trade at the last close before the gap.",
        "- One position at a time.",
        f"- Cost = `cost_for(entry)` at {info['percentile']} + 0.6 commission + 0.2 slippage, once per trade.",
        "",
        "## Setup funnel",
        "",
        md_table(pd.DataFrame([{"variant": v, **res[v]["counts"]} for v in names])),
        "",
        f"Setups by side: short {info['setups_short']:,}, long {info['setups_long']:,}. Skipped because both sides were swept: {info['both_swept']:,}.",
        "",
        "## Results (after costs, pips)",
        "",
        md_table(table),
        "",
        "## Long and short",
        "",
    ]
    for v in names:
        lines += [f"**{v}**", "", md_table(pd.DataFrame([{"side": s, **{k: res[v]["sides"][s][k] for k in
                                                                       ("trades", "win_rate", "avg_win_pips", "avg_loss_pips",
                                                                        "expectancy_pips", "total_pips", "t_stat")}}
                                                         for s in ("long", "short")])), ""]
    lines += ["## By year", ""]
    for v in names:
        lines += [f"**{v}**", "", md_table(res[v]["yearly"]), ""]
    lines += ["## Outcomes and distances", ""]
    for v in names:
        t = res[v]["trades"]
        lines += [f"- **{v}:** " + ", ".join(f"{k} {n}" for k, n in t["outcome"].value_counts().items())
                  + f". Median TP distance {t['tp_dist_pips'].median():.1f} pips, median SL distance {t['sl_dist_pips'].median():.1f} pips."]
    lines += [
        "",
        "## Control",
        "",
        f"- **Setup:** {CONTROL_RUNS} runs (seed {CONTROL_SEED}). Same entry times, same TP and SL distances in pips, random direction for each trade.",
        "- **What it measures:** whether CRT's choice of direction beats a coin flip with the same trade geometry and the same costs.",
        "- **Overlap:** control trades may overlap, because their exits differ from the strategy's.",
        "",
        "Charts: `charts/control.png` and `charts/equity.png`. Trades (pips only, no price levels): `trades_v1a.csv` and `trades_v1b.csv`.",
        "",
        "## Verdict",
        "",
        info["verdict"],
        "",
        f"Trial log: 2 rows were added (v1a and v1b), for a total of {info['trials_total']}.",
    ]
    return "\n".join(lines) + "\n"


def verdict(res: dict) -> str:
    parts = []
    for v, r in res.items():
        e = r["metrics"]["expectancy_pips"]
        p95 = float(np.quantile(r["control"], 0.95)) if len(r["control"]) else np.nan
        ok = e > 0 and r["stats"]["t"] > 2 and e > p95
        parts.append(f"- **{v}:** expectancy {e:.2f} pips, t = {r['stats']['t']:.2f}, one-sided p = {r['stats']['p']:.3g}, "
                     f"control p95 {p95:.2f}. " + ("Positive, t > 2, and above the control p95." if ok else
                                                   "Does not meet expectancy > 0, t > 2 and above the control p95 together."))
    good = [v for v, r in res.items() if r["metrics"]["expectancy_pips"] > 0 and r["stats"]["t"] > 2
            and r["metrics"]["expectancy_pips"] > np.quantile(r["control"], 0.95)]
    tail = (f"{', '.join(good)} could be pre-registered for a validation test. Note that validation 2022-2023 was already "
            "used for two other hypotheses; it is clean only for new ones like this." if good else
            "CRT v1 shows no edge on train after costs, so it is not a candidate for validation.")
    return "\n".join(parts) + "\n\n" + tail


def run(root: Path = Path("."), reports_dir: Path = Path("reports"), trials_path: Path | None = TRIALS) -> dict:
    root = Path(root)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = root / reports_dir / f"strategy_crt_{stamp}"
    if out.exists():
        raise FileExistsError(out)
    ctx = load_context(root)
    tr = ctx.splits["train"]
    m15 = read_bars(root / BARS_DIR, "M15", "train", ctx.splits).sort_values("bar_start_utc").reset_index(drop=True)
    df, _ = read_m1_split(root / M1_PATH, "train", ctx.splits, ["timestamp_utc", "high", "low", "close", "utc_unresolved"])
    df = df[~df["utc_unresolved"]].drop_duplicates("timestamp_utc", keep="first").sort_values("timestamp_utc")
    for t in (m15["bar_start_utc"], df["timestamp_utc"]):
        if not ((t >= tr.start) & (t < tr.end)).all():
            raise AssertionError("data outside the train split")
    m1 = {"t": df["timestamp_utc"].astype("int64").to_numpy(), "h": df["high"].to_numpy(float),
          "l": df["low"].to_numpy(float), "c": df["close"].to_numpy(float)}
    setups = find_setups(h4_blocks(m15))
    cands = candidates(setups, m15, ctx.cost_model, ctx.percentile)
    gs = git_state(root)
    m15_sha = sha256_file(root / BARS_DIR / bar_file("M15", "train"))
    res = {}
    for v in VARIANTS:
        sim = simulate(cands, m1, v, int(tr.end.value))
        t = sim["trades"]
        m = metrics(t, tr.start, tr.end)
        res[v] = {"trades": t, "counts": sim["counts"], "metrics": m, "stats": trade_stats(t), "yearly": yearly(t),
                  "sides": {s: metrics(t[t["direction"] == s], tr.start, tr.end) for s in ("long", "short")},
                  "control": control(t)}
        if trials_path is not None:
            log_trial(root / trials_path, {
                "run_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "strategy": f"crt_{v}",
                "params": json.dumps({**FROZEN, "variant": v, "tp": VARIANTS[v]}, sort_keys=True), "split": "train",
                "timeframe": "M15/H4", "cost_percentile": ctx.percentile, "data_sha256": m15_sha, **gs,
                **{k: (round(float(x), 6) if x is not None and np.isfinite(x) else None) for k, x in m.items()}})
    trials_total = sum(1 for _ in open(root / TRIALS, encoding="utf-8")) - 1 if (root / TRIALS).exists() else 0
    info = {"created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **gs, "m15_sha": m15_sha,
            "percentile": ctx.percentile, "trials_total": trials_total,
            "setups_short": int((setups["direction"] < 0).sum()), "setups_long": int((setups["direction"] > 0).sum()),
            "both_swept": int(setups["both_swept"].sum()), "verdict": verdict(res)}
    out.mkdir(parents=True)
    (out / "charts").mkdir()
    for v in VARIANTS:
        with open(out / f"trades_{v}.csv", "x", encoding="utf-8", newline="") as h:
            res[v]["trades"].to_csv(h, index=False, float_format="%.6g", lineterminator="\n")
    charts(res, out / "charts")
    with open(out / "summary.md", "x", encoding="utf-8") as h:
        h.write(render(res, info))
    with open(out / "run.json", "x", encoding="utf-8") as h:
        json.dump({**{k: v for k, v in info.items() if k != "verdict"}, "frozen": FROZEN,
                   "metrics": {v: res[v]["metrics"] for v in res}, "counts": {v: res[v]["counts"] for v in res},
                   "control": {"runs": CONTROL_RUNS, "seed": CONTROL_SEED},
                   "script_sha256": sha256_file(Path(__file__)),
                   "environment": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__}},
                  h, indent=2, default=str)
    return {"res": res, "out_dir": out, "info": info}


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    r = run()
    print(json.dumps({v: {"metrics": x["metrics"], "counts": x["counts"]} for v, x in r["res"].items()}, indent=2, default=str))
    print(f"written: {r['out_dir']}")


if __name__ == "__main__":
    main()
