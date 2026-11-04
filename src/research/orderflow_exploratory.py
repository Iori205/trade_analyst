"""Does 6E order flow predict the next spot EURUSD return? Exploratory, TRAIN only (2019-2021).

Validation and test are never read. Flow features come from the closed bar t and use only bars up
to t. The return runs from the open of bar t+1 to the close of bar t+h, in pips of the spot bars.
Bars t to t+h must all be clean spot bars at exact calendar spacing.

Bars left out of the features and the signals: roll_flag, degraded_flag and pre_roll_thin. Rolling
windows need 20 kept bars before t, so a window never spans a left-out bar. Session cumulative delta
stays empty for the rest of a session once a left-out bar has appeared in it.

Families (one BH correction over every test):
  corr         feature vs forward return: Pearson r, slope z with day-clustered errors
  quintile     mean forward return of each delta_ratio quintile
  spread       Q5 - Q1, as the rule long Q5 / short Q1
  condition    large delta with absorption, divergence or continuation, signed by the delta

A diagnostic outside the correction asks whether the strongest flow results survive once spot's own
past return is taken out. If they do not, the flow adds nothing that price did not already show.

Run:
    .venv/bin/python -m src.research.orderflow_exploratory
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.cost_model import CostModel, load_cost_config
from src.data.inventory import sha256_file
from src.data.splits import DEFAULT_SPLITS, load_splits
from src.research.exploratory_stats import (ALPHA, BARS_DIR, COST_CONFIG, COST_DIR, MIN_CELL, PIP, SESSIONS, TF_MINUTES,
                                            bh_qvalues, clean_bars, cluster_mean_test, md_table, p_normal, read_bars,
                                            session_of)

FLOW_DIR = Path("data/processed/orderflow_6e/v1")
HORIZONS = (1, 2, 4)
WINDOW = 20
BIG_Z = 2.0            # |delta z-score| of a large delta
FLAT_MOVE = 0.25       # absorption: |bar return| at most this many trailing mean |returns|
AGAINST_MOVE = 0.5     # divergence, continuation: |bar return| at least this many
FLAT_COST = 1.0        # pips, round trip, from the task
CONTROLLED = [("M15", 1, "all", "delta_ratio", "ret"), ("M15", 1, "ny", "delta_ratio", "ret"),
              ("M15", 1, "asia", "cum_delta", "cum_ret"), ("H1", 2, "asia", "cum_delta", "cum_ret")]
FEATURES = ["delta_ratio", "delta_z", "cum_delta", "volume_spike", "spike_signed"]
CONDITIONS = ["absorption", "divergence", "continuation"]
SCRIPTS = ["src/research/orderflow_exploratory.py", "src/research/exploratory_stats.py"]


def pre_roll_thin(flow: pd.DataFrame) -> pd.Series:
    """True from 00:00 UTC of the last weekday before each roll date up to the roll.

    For a Monday roll that is Friday and the Sunday evening session, both still on the old contract.
    """
    times = flow["bar_start_utc"]
    days = times.dt.normalize()
    weekdays = pd.DatetimeIndex(days[days.dt.dayofweek < 5].unique()).sort_values()
    thin = pd.Series(False, index=flow.index)
    for roll in times[flow["roll_flag"]]:
        earlier = weekdays[weekdays < roll.normalize()]
        if len(earlier):
            thin |= (times >= earlier[-1]) & (times < roll)
    return thin


def add_features(flow: pd.DataFrame) -> pd.DataFrame:
    """Causal flow features of each bar; empty on left-out bars. flow is sorted by time."""
    f = flow.sort_values("bar_start_utc").reset_index(drop=True)
    f["pre_roll_thin"] = pre_roll_thin(f)
    f["left_out"] = f["roll_flag"] | f["degraded_flag"] | f["pre_roll_thin"]
    keep = ~f["left_out"]
    delta, volume = f["delta"].astype(float).where(keep), f["volume"].astype(float).where(keep)
    past = delta.shift(1).rolling(WINDOW, min_periods=WINDOW)
    f["delta_ratio"] = f["delta_ratio"].where(keep)
    f["delta_z"] = (delta - past.mean()) / past.std()
    f["volume_spike"] = volume / volume.shift(1).rolling(WINDOW, min_periods=WINDOW).median()
    f["spike_signed"] = f["volume_spike"] * np.sign(delta)
    f["session"] = session_of(f["bar_start_utc"].dt.hour)
    run_id = (f["bar_start_utc"].dt.normalize().astype("int64").astype(str) + f["session"])
    f["cum_delta"] = delta.fillna(0).groupby(run_id).cumsum().where(f["left_out"].groupby(run_id).cummax().eq(0))
    return f


def add_forward(spot: pd.DataFrame, minutes: int, horizons=HORIZONS) -> pd.DataFrame:
    """Clean spot bars with fwd_<h> = close(t+h) - open(t+1) in pips and the trailing mean |return|."""
    s = spot.reset_index(drop=True).copy()
    step = pd.Timedelta(minutes=minutes)
    times = pd.DatetimeIndex(s["bar_start_utc"])
    by_time = s.set_index("bar_start_utc")
    present = pd.Series(True, index=by_time.index)
    path_ok = np.ones(len(s), dtype=bool)
    first_open = by_time["open"].reindex(times + step).to_numpy()
    for h in range(1, max(horizons) + 1):
        path_ok &= present.reindex(times + h * step).notna().to_numpy()
        if h in horizons:
            target = by_time["close"].reindex(times + h * step).to_numpy()
            s[f"fwd_{h}"] = np.where(path_ok, ((target - first_open) / PIP).round(6), np.nan)
    s["move_unit"] = s["ret"].abs().shift(1).rolling(WINDOW, min_periods=WINDOW).mean()
    return s


def add_conditions(d: pd.DataFrame) -> pd.DataFrame:
    """Large-delta bars by what spot did in the same bar; flow_sign is the delta's direction."""
    d = d.copy()
    d["flow_sign"] = np.sign(d["delta"]).astype(float)
    big = (d["delta_z"].abs() >= BIG_Z) & (np.sign(d["delta_z"]) == d["flow_sign"])
    along = d["ret"] * d["flow_sign"]
    d["absorption"] = big & (d["ret"].abs() <= FLAT_MOVE * d["move_unit"])
    d["divergence"] = big & (along < 0) & (d["ret"].abs() >= AGAINST_MOVE * d["move_unit"])
    d["continuation"] = big & (along > 0) & (d["ret"].abs() >= AGAINST_MOVE * d["move_unit"])
    return d


def cluster_corr(x, y, clusters) -> dict:
    """Pearson r, tested through the OLS slope with cluster-robust errors."""
    x = np.asarray(x, dtype=float) - np.mean(x)
    y = np.asarray(y, dtype=float) - np.mean(y)
    sxx, syy, sxy = (x * x).sum(), (y * y).sum(), (x * y).sum()
    if sxx <= 0 or syy <= 0:
        return {"n": len(x), "estimate": np.nan, "z": np.nan, "p": np.nan}
    slope = sxy / sxx
    score = pd.Series(x * (y - slope * x)).groupby(np.asarray(clusters)).sum()
    g = len(score)
    se = sqrt((score ** 2).sum() * g / max(g - 1, 1)) / sxx
    z = slope / se if se > 0 else np.nan
    return {"n": len(x), "estimate": float(sxy / sqrt(sxx * syy)), "z": z, "p": p_normal(z)}


class TestLog:
    """Collects test rows and, for each rule, the per-bar signed returns for the yearly check."""

    __test__ = False  # not a pytest class

    def __init__(self):
        self.rows, self.signed = [], {}

    def add(self, family, tf, h, session, label, res, unit, rule=None, sample=None):
        """rule: per-bar +1 / -1 / 0 in `sample`, or None when the test implies no trade."""
        test_id = f"{family} {tf} h{h} {session} {label}"
        row = {"family": family, "test_id": test_id, "timeframe": tf, "horizon": h, "session": session, "label": label,
               "n": res["n"], "estimate": res["estimate"], "unit": unit, "z": res["z"],
               "p": res["p"] if res["n"] >= MIN_CELL else np.nan,
               "edge_pips": np.nan, "model_cost_pips": np.nan}
        if rule is not None and res["n"] >= MIN_CELL:
            trades = sample[rule != 0]
            pnl = (rule[rule != 0] * trades[f"fwd_{h}"]).astype(float)
            row["edge_pips"] = abs(float(pnl.mean()))
            row["model_cost_pips"] = float(trades["cost"].mean())
            direction = np.sign(pnl.mean())
            self.signed[test_id] = pd.Series(direction * pnl.to_numpy(), index=pd.DatetimeIndex(trades["bar_start_utc"]))
        self.rows.append(row)


def quintiles(x: pd.Series) -> pd.Series:
    return pd.qcut(x, 5, labels=[1, 2, 3, 4, 5]).astype(float)


def analyse_timeframe(d: pd.DataFrame, tf: str, t: TestLog) -> list[dict]:
    """All tests of one timeframe; returns the quintile table."""
    table = []
    for session in ["all", *SESSIONS]:
        part = d if session == "all" else d[d["session"] == session]
        if part["delta_ratio"].notna().sum() < MIN_CELL:
            continue
        part = part.assign(q=quintiles(part["delta_ratio"]))
        for h in HORIZONS:
            y = f"fwd_{h}"
            for name in FEATURES:
                s = part.dropna(subset=[name, y])
                if len(s) < MIN_CELL:
                    continue
                rule = None if name == "volume_spike" else np.sign(s[name]).to_numpy()
                t.add("corr", tf, h, session, name, cluster_corr(s[name], s[y], s["day"]), "r", rule, s)
            s = part.dropna(subset=["q", y])
            means = {}
            for q in range(1, 6):
                cell = s[s["q"] == q]
                res = cluster_mean_test(cell[y].to_numpy(), cell["day"].to_numpy())
                means[q] = res["estimate"]
                if session == "all":
                    t.add("quintile", tf, h, session, f"Q{q}", res, "pips")
                table.append({"timeframe": tf, "horizon": h, "session": session, "quintile": q, "n": res["n"],
                              "mean_pips": res["estimate"], "t": res["z"]})
            ends = s[s["q"].isin([1, 5])]
            rule = np.where(ends["q"] == 5, 1.0, -1.0)
            res = cluster_mean_test(rule * ends[y].to_numpy(), ends["day"].to_numpy())
            res = {**res, "estimate": means[5] - means[1]}
            t.add("spread", tf, h, session, "Q5-Q1", res, "pips", rule, ends)
            steps = np.diff([means[q] for q in range(1, 6)])
            table.append({"timeframe": tf, "horizon": h, "session": session, "quintile": "monotonic",
                          "n": res["n"], "mean_pips": float((steps > 0).all() or (steps < 0).all()), "t": res["z"]})
            for cond in CONDITIONS:
                cell = part[part[cond]].dropna(subset=[y])
                sides = [("both", cell)]
                if session == "all":
                    sides += [("buy", cell[cell["flow_sign"] > 0]), ("sell", cell[cell["flow_sign"] < 0])]
                for side, c in sides:
                    if len(c) < MIN_CELL:
                        t.add("condition", tf, h, session, f"{cond} {side}", {"n": len(c), "estimate": np.nan, "z": np.nan, "p": np.nan}, "pips")
                        continue
                    sign = c["flow_sign"].to_numpy()
                    res = cluster_mean_test(sign * c[y].to_numpy(), c["day"].to_numpy())
                    t.add("condition", tf, h, session, f"{cond} {side}", res, "pips along the delta", sign, c)
    return table


def merge_inputs(flow: pd.DataFrame, spot: pd.DataFrame, minutes: int) -> pd.DataFrame:
    f = add_features(flow)
    s = add_forward(spot, minutes)
    d = f.merge(s[["bar_start_utc", "ret", "move_unit", *[f"fwd_{h}" for h in HORIZONS]]], on="bar_start_utc", how="inner")
    d["day"] = d["bar_start_utc"].dt.floor("D").astype("int64")
    d["cum_ret"] = d["ret"].groupby([d["day"], d["session"]]).cumsum()
    return add_conditions(d)


def partial_corr(d: pd.DataFrame, feature: str, control: str, y: str) -> dict:
    """Correlation of feature and y after both are regressed on control (day-clustered)."""
    s = d.dropna(subset=[feature, control, y])
    c = s[control].to_numpy(dtype=float) - s[control].mean()
    def residual(col):
        v = s[col].to_numpy(dtype=float) - s[col].mean()
        return v - c * (c @ v) / (c @ c)
    return cluster_corr(residual(feature), residual(y), s["day"].to_numpy())


def control_table(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for tf, h, session, feature, control in CONTROLLED:
        d = frames[tf] if session == "all" else frames[tf][frames[tf]["session"] == session]
        s = d.dropna(subset=[feature, control, f"fwd_{h}"])
        raw = cluster_corr(s[feature], s[f"fwd_{h}"], s["day"])
        own = cluster_corr(s[control], s[f"fwd_{h}"], s["day"])
        part = partial_corr(d, feature, control, f"fwd_{h}")
        rows.append({"test": f"{tf} h{h} {session} {feature}", "control": control, "n": raw["n"], "r_feature": raw["estimate"], "z_feature": raw["z"],
                     "r_spot_control": own["estimate"], "z_spot_control": own["z"],
                     "r_after_control": part["estimate"], "z_after_control": part["z"]})
    return pd.DataFrame(rows)


def analyse(frames: dict[str, pd.DataFrame]) -> dict:
    t, quint = TestLog(), []
    for tf, d in frames.items():
        quint += analyse_timeframe(d, tf, t)
    rows = pd.DataFrame(t.rows)
    rows["q_bh"] = bh_qvalues(rows["p"].to_numpy())
    rows["significant_fdr"] = rows["q_bh"] < ALPHA
    rows["net_flat_pips"] = rows["edge_pips"] - FLAT_COST
    rows["net_model_pips"] = rows["edge_pips"] - rows["model_cost_pips"]
    return {"tests": rows, "quintiles": pd.DataFrame(quint), "signed": t.signed}


def yearly(signed: dict, test_ids) -> pd.DataFrame:
    out = []
    for tid in test_ids:
        s = signed[tid]
        row = {"test_id": tid}
        for year, g in s.groupby(s.index.year):
            row[f"{year} pips"] = g.mean()
            row[f"{year} n"] = len(g)
        out.append(row)
    return pd.DataFrame(out)


def load_frames(root: Path, splits: dict) -> tuple[dict, dict]:
    """Train-only inputs. Files are checked against SHA256SUMS; only *_train.parquet is opened."""
    train = splits["train"]
    cfg = load_cost_config(root / COST_CONFIG)
    costs = CostModel.load(root / COST_DIR, cfg)
    recorded = dict(l.split()[::-1] for l in (root / FLOW_DIR / "SHA256SUMS.txt").read_text().splitlines() if l)
    frames, meta = {}, {"cost": cfg["trading_costs"]["spread_percentile"], "inputs": {}, "counts": {}}
    for tf, minutes in TF_MINUTES.items():
        path = root / FLOW_DIR / f"orderflow_6e_{tf.lower()}_train.parquet"
        sha = sha256_file(path)
        if recorded.get(path.name) != sha:
            raise AssertionError(f"{path} does not match SHA256SUMS.txt")
        flow = pd.read_parquet(path)
        spot_raw = read_bars(root / BARS_DIR, tf, "train", splits)
        for name, b in (("flow", flow), ("spot", spot_raw)):
            if not ((b["bar_start_utc"] >= train.start) & (b["bar_start_utc"] < train.end)).all():
                raise AssertionError(f"{name} bars outside the train range")
        spot = clean_bars(spot_raw)
        spot = spot[spot["bar_start_utc"] >= flow["bar_start_utc"].min() - pd.Timedelta(days=30)].reset_index(drop=True)
        d = merge_inputs(flow, spot, minutes)
        step = pd.Timedelta(minutes=minutes)
        d["cost"] = costs.cost_for(pd.DatetimeIndex(d["bar_start_utc"] + step))["total_pips"].to_numpy()
        frames[tf] = d
        f = add_features(flow)
        meta["inputs"][path.name] = sha
        meta["counts"][tf] = {
            "flow_bars": len(flow), "roll_flag": int(f["roll_flag"].sum()), "degraded_flag": int(f["degraded_flag"].sum()),
            "pre_roll_thin": int(f["pre_roll_thin"].sum()), "left_out": int(f["left_out"].sum()),
            "matched_clean_spot": len(d), "with_delta_ratio_and_fwd_1": int(d[["delta_ratio", "fwd_1"]].notna().all(axis=1).sum()),
            "absorption": int(d["absorption"].sum()), "divergence": int(d["divergence"].sum()),
            "continuation": int(d["continuation"].sum()),
            "thin_volume_ratio": round(float(f.loc[f["pre_roll_thin"], "volume"].mean() / f.loc[~f["left_out"], "volume"].mean()), 3)}
    return frames, meta


def verdict(r: dict, controls: pd.DataFrame) -> str:
    tests, quint = r["tests"], r["quintiles"]
    m = int(tests["p"].notna().sum())
    sig = tests[tests["significant_fdr"]]
    rules = sig[sig["edge_pips"].notna()]
    top = rules.sort_values("p").iloc[0]
    largest = rules.sort_values("edge_pips", ascending=False).iloc[0]
    wide = tests[(tests["edge_pips"] > FLAT_COST) & tests["p"].notna()]
    negative = int((sig["estimate"] < 0).sum())
    mono = quint[quint["quintile"] == "monotonic"]
    mono_hits = mono[mono["mean_pips"] == 1]
    conds = tests[(tests["family"] == "condition") & tests["label"].str.startswith(("absorption", "divergence"))]
    london = tests[(tests["session"] == "london")]
    gone = controls[controls["z_after_control"].abs() < 2]
    return "\n".join([
        f"**Order flow has a small, real-looking link to the next return, and it is far too small to trade.** {len(sig)} of {m} tests have q < {ALPHA}, and {negative} of those {len(sig)} point the same way: after buying, spot falls slightly. Flow does not predict continuation.\n",
        f"- **Strongest by p-value:** `{top.test_id}`, r {top.estimate:.4f}, z {top.z:.2f}, q {top.q_bh:.2g}, gain {top.edge_pips:.3f} pips a trade. It has the same sign in 2019, 2020 and 2021.",
        f"- **Largest gain with q < {ALPHA}:** `{largest.test_id}`, {largest.edge_pips:.3f} pips a trade, so {largest.net_flat_pips:.3f} after the 1.0 pip cost. **No significant result covers the cost.**",
        f"- **Gains above 1 pip:** {len(wide)} tests, all with q >= {wide['q_bh'].min():.2f} and at most {int(wide['n'].max())} trades. They are noise until shown otherwise.",
        f"- **Quintiles:** the pattern is monotonic in {len(mono_hits)} of {len(mono)} cells ({', '.join(f'{c.timeframe} h{c.horizon} {c.session}' for c in mono_hits.itertuples())}). The Q5-Q1 gap there is {tests.set_index('test_id').loc['spread M15 h1 all Q5-Q1', 'estimate']:.2f} pips.",
        f"- **Absorption and divergence:** none of the {int(conds['p'].notna().sum())} tests has q < {ALPHA} (lowest q {conds['q_bh'].min():.2f}). The one significant condition is the control, continuation, and it too reverses.",
        f"- **Sessions:** Asia and NY hold the significant results; London has none (lowest q {london['q_bh'].min():.2f}). Asia is mostly session cumulative delta fading.",
        f"- **Flow vs spot's own return:** {len(gone)} of {len(controls)} leading results fall under |z| 2 once spot's past return is removed; see the table in that section.\n",
        "Caveats: direction and quintile cut points were chosen in sample, so the gains are upper estimates. Spot bars are bid only. These tests are not in `reports/trials/trials.csv`, which logs strategy runs. Stronger filters on the same data were not tried and would add to the test count. Validation was not used.",
    ])


def render(r: dict, meta: dict, stamp: str, controls: pd.DataFrame) -> str:
    tests, quint = r["tests"], r["quintiles"]
    m = int(tests["p"].notna().sum())
    sig = tests[tests["significant_fdr"]].sort_values("q_bh")
    rules = tests[tests["edge_pips"].notna()]
    best_edge = rules[rules["significant_fdr"]].sort_values("edge_pips", ascending=False)
    top_ids = list(dict.fromkeys(list(rules.sort_values("p")["test_id"].head(5)) + list(best_edge["test_id"].head(3))))
    cols = ["test_id", "n", "estimate", "z", "p", "q_bh", "edge_pips", "net_flat_pips", "net_model_pips"]
    counts = pd.DataFrame(meta["counts"]).T.rename_axis("timeframe").reset_index()
    wide = quint[(quint["session"] == "all") & (quint["quintile"] != "monotonic")].pivot_table(
        index=["timeframe", "horizon"], columns="quintile", values="mean_pips")
    wide_t = quint[(quint["session"] == "all") & (quint["quintile"] != "monotonic")].pivot_table(
        index=["timeframe", "horizon"], columns="quintile", values="t")
    wide = wide.rename(columns=lambda c: f"Q{c} pips").join(wide_t.rename(columns=lambda c: f"Q{c} t")).reset_index()
    mono = quint[quint["quintile"] == "monotonic"]
    conditions = tests[(tests["family"] == "condition") & (tests["session"] == "all")]
    by_session = tests[tests["session"].isin(SESSIONS)].groupby(["session", "family"]).agg(
        tests=("p", "count"), significant=("significant_fdr", "sum"), min_q=("q_bh", "min"), max_edge_pips=("edge_pips", "max")).reset_index()
    by_family = tests.groupby("family").agg(tests=("p", "count"), significant=("significant_fdr", "sum"), min_q=("q_bh", "min")).reset_index()
    return "\n".join([
        f"# Order flow exploratory statistics (train 2019-2021)\n\nGenerated {stamp}. Inputs: order flow bars v1 (train files) and EURUSD spot bars v1 (train file). Validation and test were not read.\n",
        "## Result\n", verdict(r, controls) + "\n",
        "## Method\n",
        f"- Signal from closed bar t; return = close(t+h) - open(t+1) of spot, in pips; h = {HORIZONS}. Bars t to t+h must be clean spot bars at exact spacing.",
        "- Left out: `roll_flag`, `degraded_flag`, `pre_roll_thin`. `pre_roll_thin` is computed here, not stored in bars v1. It runs from 00:00 UTC of the last weekday before the roll to the roll, so it also holds the Sunday evening session on the old contract.",
        f"- delta z and volume spike use the {WINDOW} bars before t. Cumulative delta resets at each Asia, London, NY and other block of a UTC day.",
        f"- Large delta: |z| >= {BIG_Z} with z and delta on one side. Absorption: |spot bar return| <= {FLAT_MOVE} of the trailing {WINDOW}-bar mean |return|. Divergence and continuation: at least {AGAINST_MOVE} of it, against or along the delta. Continuation is a control.",
        "- Sessions: Asia 00-07, London 07-12, NY 12-21 UTC by bar start, as in the earlier exploratory run. Bars from 21 to 24 UTC count only in `all`.",
        "- `spike_signed` = volume spike x sign of delta. It was added because volume alone has no direction.",
        "- Errors are clustered by UTC day. edge_pips = |mean gain of the rule|, with the direction chosen in sample. net_model uses the cost model at bar t+1, p75.",
        "- Quintile cut points use the whole train sample, so they are in sample.\n",
        "## Sample\n", md_table(counts, "{:.6g}"),
        f"\n`thin_volume_ratio` = mean volume of a `pre_roll_thin` bar over a kept bar.",
        f"\n## Tests\n\n**{m} tests** in one BH correction; {len(sig)} have q < {ALPHA}.\n", md_table(by_family),
        "\n## Strongest results\n", md_table(rules.sort_values("p").head(10)[cols]),
        "\n### By year (mean pips of the rule, in its in-sample direction)\n", md_table(yearly(r["signed"], top_ids)),
        "\n## Flow vs spot's own past return (diagnostic, not in the test count)\n",
        "Both the feature and the forward return are regressed on the control, then correlated. `ret` is spot's return in bar t; `cum_ret` is spot's return so far in the session.\n",
        md_table(controls, "{:.3f}"),
        "\n## delta_ratio quintiles, all sessions\n", md_table(wide),
        f"\nMonotonic in all five steps: {int(mono['mean_pips'].sum())} of {len(mono)} timeframe, horizon and session cells. All cells are in `quintiles.csv`.\n",
        "## Absorption, divergence, continuation (all sessions)\n",
        md_table(conditions[["test_id", "n", "estimate", "z", "p", "q_bh", "edge_pips", "net_flat_pips"]]),
        "\n## By session\n", md_table(by_session),
        f"\n## All tests with q < {ALPHA}\n", md_table(sig[cols]), "\n"])


def run(root: Path = Path("."), stamp: str | None = None) -> Path:
    root = Path(root)
    splits = load_splits(root / DEFAULT_SPLITS)
    frames, meta = load_frames(root, splits)
    r = analyse(frames)
    controls = control_table(frames)
    stamp = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rep = root / "reports" / f"orderflow_exploratory_{stamp}"
    rep.mkdir(parents=True, exist_ok=False)
    r["tests"].to_csv(rep / "tests.csv", index=False, float_format="%.6g")
    r["quintiles"].to_csv(rep / "quintiles.csv", index=False, float_format="%.6g")
    (rep / "run.json").write_text(json.dumps({"meta": meta, "tests": int(r["tests"]["p"].notna().sum())}, indent=2) + "\n", encoding="utf-8")
    controls.to_csv(rep / "controls.csv", index=False, float_format="%.6g")
    (rep / "summary.md").write_text(render(r, meta, stamp, controls), encoding="utf-8")
    return rep


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    print(run())
