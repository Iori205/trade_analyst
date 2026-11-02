"""One-time validation test, run exactly as pre-registered in docs/preregistration_validation_v1.md.

Guards before any validation data is read:
  - the pre-registration's SHA-256 must equal the value logged in reports/trials/trials.csv;
  - every frozen file listed in the pre-registration must still have its recorded SHA-256;
  - reports/validation_v1.lock is created with exclusive mode; if it exists the run is refused,
    so validation can be read by this script only once.

Run (once):
    .venv/bin/python -m src.research.validation_v1
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import platform
import re
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.baselines import monday_13
from src.backtest.engine import BARS_DIR, TRIALS, git_state, load_context, log_trial, metrics, run_backtest
from src.data.bars import bar_file, read_bars
from src.data.inventory import sha256_file
from src.data.splits import read_m1_split
from src.research.ml_discovery import (
    M1_PATH, candidates, features, make_model, random_trades, rule_trades, trade_stats, triple_barrier, variant_name,
)

PREREG = Path("docs/preregistration_validation_v1.md")
LOCK = Path("reports/validation_v1.lock")
DIRECTION, TP, SL, HORIZON_H = "short", 2.0, 1.5, 4
CONTROL_RUNS, CONTROL_SEED, CONTROL_HOURS = 1000, 20261105, range(4, 14)
ALPHA = 0.025
T_MIN = 2.0
YEARS = (2022, 2023)
SCRIPT = "src/research/validation_v1.py"


class ValidationGuardError(PermissionError):
    pass


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------
def frozen_hashes(prereg_text: str) -> dict[str, str]:
    """`| path | `sha` |` rows of the pre-registration's frozen-files table."""
    return dict(re.findall(r"^\| ([\w./-]+) \| `([0-9a-f]{64})` \|$", prereg_text, flags=re.M))


def logged_prereg_sha(trials_path: Path) -> str | None:
    with open(trials_path, encoding="utf-8", newline="") as h:
        rows = [r for r in csv.DictReader(h) if r["strategy"] == "preregistration_validation_v1"]
    if len(rows) != 1:
        return None
    return json.loads(rows[0]["params"])["sha256"]


def check_guards(root: Path, prereg: Path = PREREG, trials: Path = TRIALS) -> dict:
    sha = sha256_file(root / prereg)
    logged = logged_prereg_sha(root / trials)
    if logged != sha:
        raise ValidationGuardError(f"pre-registration SHA-256 {sha} does not match the trial log ({logged})")
    frozen = frozen_hashes((root / prereg).read_text(encoding="utf-8"))
    if not frozen:
        raise ValidationGuardError("no frozen files found in the pre-registration")
    changed = {p: s for p, s in frozen.items() if sha256_file(root / p) != s}
    if changed:
        raise ValidationGuardError(f"frozen files changed since pre-registration: {sorted(changed)}")
    return {"prereg_sha256": sha, "frozen": frozen}


def acquire_lock(root: Path, prereg_sha: str, lock: Path = LOCK) -> Path:
    path = root / lock
    try:
        with open(path, "x", encoding="utf-8") as h:   # exclusive: a second run fails here
            json.dump({"created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "prereg_sha256": prereg_sha, "note": "validation v1 has been run; do not delete"}, h, indent=2)
    except FileExistsError:
        raise ValidationGuardError(f"{path} exists: validation v1 was already run") from None
    return path


# ---------------------------------------------------------------------------
# Criteria
# ---------------------------------------------------------------------------
def evaluate_a(trades: pd.DataFrame, control: np.ndarray) -> dict:
    st = trade_stats(trades)
    exp_ = float(trades["net_pips"].mean()) if len(trades) else np.nan
    p95 = float(np.nanquantile(control, 0.95)) if len(control) else np.nan
    by_year = {y: (float(trades.loc[trades["entry_time"].dt.year == y, "net_pips"].mean())
                   if (trades["entry_time"].dt.year == y).any() else np.nan) for y in YEARS}
    crit = {
        "1. expectancy > 0": bool(exp_ > 0),
        f"2. t > {T_MIN:g} and one-sided p < {ALPHA}": bool(np.isfinite(st["t"]) and st["t"] > T_MIN and st["p"] < ALPHA),
        "3. above control p95": bool(np.isfinite(exp_) and exp_ > p95),
        "4. expectancy >= 0 in 2022 and 2023": bool(all(np.isfinite(v) and v >= 0 for v in by_year.values())),
    }
    return {"expectancy": exp_, "t": st["t"], "p": st["p"], "control_p95": p95, "by_year": by_year,
            "criteria": crit, "passed": all(crit.values())}


def evaluate_b(trades: pd.DataFrame) -> dict:
    st = trade_stats(trades)
    exp_ = float(trades["net_pips"].mean()) if len(trades) else np.nan
    crit = {"1. expectancy > 0": bool(exp_ > 0),
            f"2. t > {T_MIN:g} and one-sided p < {ALPHA}": bool(np.isfinite(st["t"]) and st["t"] > T_MIN and st["p"] < ALPHA)}
    return {"expectancy": exp_, "t": st["t"], "p": st["p"], "criteria": crit, "passed": all(crit.values())}


# ---------------------------------------------------------------------------
# Candidate A
# ---------------------------------------------------------------------------
def candidate_a(ctx) -> dict:
    splits, root = ctx.splits, ctx.root
    tr_s, va_s = splits["train"], splits["validation"]
    h1 = pd.concat([read_bars(root / BARS_DIR, "H1", "train", splits),
                    read_bars(root / BARS_DIR, "H1", "validation", splits)]).sort_values("bar_start_utc").reset_index(drop=True)
    if (h1["bar_start_utc"] >= va_s.end).any():
        raise AssertionError("bars beyond validation")
    X = features(h1)
    cands = candidates(h1, ctx.cost_model, ctx.percentile)
    is_tr = (h1["bar_start_utc"] < tr_s.end).to_numpy()
    is_va = (h1["bar_start_utc"] >= va_s.start).to_numpy()
    cols = ["timestamp_utc", "high", "low", "close", "utc_unresolved"]
    m1 = {}
    for name in ("train", "validation"):
        df, _ = read_m1_split(root / M1_PATH, name, splits, cols)
        m1[name] = df[~df["utc_unresolved"]].drop_duplicates("timestamp_utc", keep="first").sort_values("timestamp_utc").reset_index(drop=True)
    name = variant_name(DIRECTION, TP, SL, HORIZON_H)
    c_tr, c_va = cands[is_tr].reset_index(drop=True), cands[is_va].reset_index(drop=True)
    x_tr, x_va = X[is_tr].reset_index(drop=True), X[is_va].reset_index(drop=True)
    lab_tr = triple_barrier(c_tr, m1["train"], int(tr_s.end.value))[name]
    lab_va = triple_barrier(c_va, m1["validation"], int(va_s.end.value))[name]

    fit_mask = (lab_tr["valid"].to_numpy() & (c_tr["entry_time"] >= pd.Timestamp("2015-01-01", tz="UTC")).to_numpy()
                & (c_tr["entry_time"] < va_s.start - pd.Timedelta(hours=HORIZON_H)).to_numpy())
    model = make_model("hgb")
    model.fit(x_tr[fit_mask], lab_tr["y"].to_numpy()[fit_mask])
    p = model.predict_proba(x_va)[:, 1]
    trades = rule_trades(p, c_va, lab_va, TP, SL, DIRECTION)

    rng = np.random.default_rng(CONTROL_SEED)
    entry_ns = c_va["entry_time"].astype("int64").to_numpy()
    exit_ns = lab_va["exit_ns"].to_numpy()
    years = c_va["entry_time"].dt.year.to_numpy()
    hours = c_va["entry_time"].dt.hour.to_numpy()
    pool_mask = lab_va["valid"].to_numpy() & np.isin(hours, list(CONTROL_HOURS))
    target = trades["entry_time"].dt.year.value_counts().to_dict()
    control, control_n = [], []
    ret = lab_va["ret_pips"].to_numpy() - c_va["cost_pips"].to_numpy()
    for _ in range(CONTROL_RUNS):
        idx = []
        for y in YEARS:
            idx += random_trades(rng, np.flatnonzero(pool_mask & (years == y)), target.get(y, 0), entry_ns, exit_ns)
        control.append(float(ret[idx].mean()) if idx else np.nan)
        control_n.append(len(idx))
    return {"trades": trades, "control": np.array(control), "control_n": np.array(control_n),
            "fit_rows": int(fit_mask.sum()), "fit_tp_rate": float(lab_tr["y"].to_numpy()[fit_mask].mean()),
            "val_candidates": int(c_va["eligible"].sum()), "val_labelled": int(lab_va["valid"].sum()),
            "val_eligible_ev": int((~np.isnan(p) & lab_va["valid"].to_numpy()).sum()),
            "control_pool": {y: int((pool_mask & (years == y)).sum()) for y in YEARS},
            "p_quantiles": np.nanquantile(p[lab_va["valid"].to_numpy()], [0.05, 0.5, 0.95]).tolist() if lab_va["valid"].any() else []}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def fmt(v) -> str:
    if isinstance(v, (float, np.floating)):
        return "–" if np.isnan(v) else (f"{v:.2e}" if 0 < abs(v) < 1e-3 else f"{v:,.3f}")
    return str(v)


def md_table(df: pd.DataFrame) -> str:
    head = "| " + " | ".join(map(str, df.columns)) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "\n".join("| " + " | ".join(fmt(v) for v in r) + " |" for r in df.itertuples(index=False))


def year_table(t: pd.DataFrame) -> pd.DataFrame:
    g = t.groupby(t["entry_time"].dt.year)["net_pips"]
    out = pd.DataFrame({"trades": g.size(), "expectancy_pips": g.mean(), "total_pips": g.sum(),
                        "win_rate": g.apply(lambda s: float((s > 0).mean()))}).reindex(list(YEARS))
    out["trades"] = out["trades"].fillna(0).astype(int)
    return out.rename_axis("year").reset_index()


def charts(a: dict, ev_a: dict, out: Path) -> None:
    from src.backtest.baselines import BASE, BLUE, INK2, ORANGE, SURFACE, _plt, _save
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.hist(a["control"][np.isfinite(a["control"])], bins=40, color="#9ec5f4", edgecolor=SURFACE)
    ax.axvline(ev_a["control_p95"], color=INK2, lw=1.5, ls="--")
    ax.text(ev_a["control_p95"], ax.get_ylim()[1] * 0.95, " control p95", color=INK2, va="top", fontsize=8)
    if np.isfinite(ev_a["expectancy"]):
        ax.axvline(ev_a["expectancy"], color=ORANGE, lw=2.5)
        ax.text(ev_a["expectancy"], ax.get_ylim()[1] * 0.8, " candidate A", color=INK2, va="top", fontsize=8)
    ax.axvline(0, color=BASE, lw=0.8)
    ax.set_xlabel("expectancy per trade after costs (pips)")
    ax.set_ylabel("control runs")
    ax.set_title(f"Validation 2022-2023: candidate A vs {CONTROL_RUNS} random short controls (04-13 UTC)", loc="left")
    _save(fig, out / "control_distribution.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    h = a["trades"]["entry_time"].dt.hour.value_counts().reindex(range(24), fill_value=0)
    ax.bar(h.index, h.to_numpy(), color=BLUE, width=0.7, edgecolor=SURFACE)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlabel("entry hour (UTC)")
    ax.set_ylabel("trades")
    ax.set_title("Candidate A: entry hours on validation", loc="left")
    _save(fig, out / "entry_hours_a.png")
    plt.close(fig)


def render(a: dict, ev_a: dict, b: dict, ev_b: dict, info: dict) -> str:
    def crit_rows(ev):
        return "\n".join(f"| {k} | {'**PASSED**' if v else '**FAILED**'} |" for k, v in ev["criteria"].items())
    ta, tb = a["trades"], b["trades"]
    hours_a = ta["entry_time"].dt.hour.value_counts().sort_index()
    ctrl = a["control"][np.isfinite(a["control"])]
    lines = [
        "# Validation v1 (2022-2023): one-time pre-registered test",
        "",
        f"Run {info['created_utc']} by `{SCRIPT}` (SHA-256 `{info['script_sha256'][:16]}…`), HEAD `{(info['git_commit'] or '')[:7]}`.",
        "",
        f"- **Pre-registration:** `{PREREG}`, SHA-256 `{info['prereg_sha256']}`. It matched the trial log before the run, and all {info['n_frozen']} frozen file hashes matched.",
        f"- **Lock:** `{LOCK}` was created before validation was read. This script refuses to run a second time.",
        "- **Test split:** not read.",
        "- **Validation data:** bars and the M1 path for UTC 2022-01-01 to 2023-12-31, excluding `low_quality_period` (2023-02-01 to 2023-07-31), as the split config defines.",
        f"  - Validation H1 file SHA-256 `{info['val_h1_sha256'][:16]}…`.",
        "",
        "## Result",
        "",
        f"- **Candidate A** (`{variant_name(DIRECTION, TP, SL, HORIZON_H)}`): **{'PASSED' if ev_a['passed'] else 'FAILED'}**",
        f"- **Candidate B** (Monday 13:00 UTC long): **{'PASSED' if ev_b['passed'] else 'FAILED'}**",
        "",
        "Multiple testing: Bonferroni over the 2 candidates, one-sided α = 0.025 each.",
        "",
        "## Candidate A",
        "",
        "| criterion | result |",
        "|---|---|",
        crit_rows(ev_a),
        "",
        f"- **Trades:** {len(ta)}.",
        f"- **Expectancy after costs:** {fmt(ev_a['expectancy'])} pips; t = {fmt(ev_a['t'])}, one-sided p = {fmt(ev_a['p'])}.",
        f"- **Control:** p95 {fmt(ev_a['control_p95'])}, median {fmt(float(np.median(ctrl)) if len(ctrl) else np.nan)} pips; {int((ctrl < ev_a['expectancy']).sum()) if len(ctrl) else 0} of {len(ctrl)} control runs are below A.",
        f"- **Model:** fitted once on {a['fit_rows']:,} train labels (TP-first rate {a['fit_tp_rate']:.3f}).",
        f"  - Validation candidates: {a['val_candidates']:,} eligible, {a['val_labelled']:,} with a valid label.",
        f"  - Predicted p on validation: p5/p50/p95 = {', '.join(f'{x:.3f}' for x in a['p_quantiles'])}.",
        "",
        "By year:",
        "",
        md_table(year_table(ta)),
        "",
        "Outcomes: " + (", ".join(f"{k} {v}" for k, v in ta["outcome"].value_counts().items()) if len(ta) else "none") + ".",
        "",
        "Entry hours (UTC): " + (", ".join(f"{h:02d}h {n}" for h, n in hours_a.items()) if len(ta) else "none") + ".",
        "",
        f"Control pool (valid labels, entry 04-13 UTC): " + ", ".join(f"{y} {n:,}" for y, n in a["control_pool"].items())
        + f". Control trades per run: median {int(np.median(a['control_n']))}.",
        "",
        "Charts: `charts/control_distribution.png` and `charts/entry_hours_a.png`. Trades: `trades_a.csv`. Control runs: `control_a.csv`.",
        "",
        "## Candidate B",
        "",
        "| criterion | result |",
        "|---|---|",
        crit_rows(ev_b),
        "",
        f"- **Trades:** {len(tb)}.",
        f"- **Expectancy after costs:** {fmt(ev_b['expectancy'])} pips; t = {fmt(ev_b['t'])}, one-sided p = {fmt(ev_b['p'])}.",
        "- **Entry hour:** always 13:00 UTC, Monday.",
        "",
        "By year:",
        "",
        md_table(year_table(tb)),
        "",
        "Trades: `trades_b.csv`.",
        "",
        "## What this means",
        "",
        info["meaning"],
        "",
        "## Trial log",
        "",
        "Both candidates' validation results were added to `reports/trials/trials.csv` (split `validation`). Validation v1 is now used up for these two hypotheses. Following the pre-registration, nothing is re-tuned or re-run on it.",
    ]
    return "\n".join(lines) + "\n"


def meaning(ev_a: dict, ev_b: dict) -> str:
    if ev_a["passed"] or ev_b["passed"]:
        ok = [n for n, e in (("A", ev_a), ("B", ev_b)) if e["passed"]]
        return (f"Candidate(s) {', '.join(ok)} met every pre-registered criterion on unseen 2022-2023 data. "
                "This is evidence, not proof. The locked test split (2024-2026) is the final check, and it should be run "
                "once, only after a new pre-registration with the same frozen rules.")
    return ("Neither candidate met its pre-registered criteria on 2022-2023, so neither edge from train is confirmed. "
            "As pre-registered, no parameters are changed and nothing is re-run on validation. Any new idea needs a new "
            "hypothesis developed on train only. Validation is no longer clean for these two hypotheses.")


def run(root: Path = Path("."), reports_dir: Path = Path("reports")) -> dict:
    import sklearn
    root = Path(root)
    g = check_guards(root)
    acquire_lock(root, g["prereg_sha256"])
    ctx = load_context(root)
    a = candidate_a(ctx)
    ev_a = evaluate_a(a["trades"], a["control"])
    va = ctx.splits["validation"]
    m_a = metrics(a["trades"], va.start, va.end)
    gs = git_state(root)
    val_sha = sha256_file(root / BARS_DIR / bar_file("H1", "validation"))
    log_trial(root / TRIALS, {
        "run_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "strategy": "validation_v1_A_hgb_short_tp2_sl1.5_h4",
        "params": json.dumps({"prereg_sha256": g["prereg_sha256"], "passed": ev_a["passed"],
                              "criteria": ev_a["criteria"], "control_p95": ev_a["control_p95"]}, sort_keys=True),
        "split": "validation", "timeframe": "H1", "cost_percentile": ctx.percentile, "data_sha256": val_sha, **gs,
        **{k: (round(float(v), 6) if v is not None and np.isfinite(v) else None) for k, v in m_a.items()}})
    b = run_backtest(ctx, monday_13(), "H1", split="validation")      # logs its own trial row
    ev_b = evaluate_b(b["trades"])
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = root / reports_dir / f"validation_v1_{stamp}"
    out.mkdir(parents=True)
    (out / "charts").mkdir()
    for fname, df in (("trades_a.csv", a["trades"]),
                      ("trades_b.csv", b["trades"].drop(columns=["entry_price", "exit_price"])),
                      ("control_a.csv", pd.DataFrame({"run": range(CONTROL_RUNS), "trades": a["control_n"],
                                                      "expectancy_pips": a["control"]}))):
        with open(out / fname, "x", encoding="utf-8", newline="") as h:
            df.to_csv(h, index=False, float_format="%.6g", lineterminator="\n")
    charts(a, ev_a, out / "charts")
    info = {"created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **gs,
            "prereg_sha256": g["prereg_sha256"], "n_frozen": len(g["frozen"]), "val_h1_sha256": val_sha,
            "script_sha256": sha256_file(Path(__file__)), "meaning": meaning(ev_a, ev_b)}
    with open(out / "summary.md", "x", encoding="utf-8") as h:
        h.write(render(a, ev_a, b, ev_b, info))
    with open(out / "run.json", "x", encoding="utf-8") as h:
        json.dump({**info, "candidate_a": {k: v for k, v in ev_a.items()}, "candidate_b": ev_b,
                   "metrics_a": m_a, "metrics_b": b["metrics"],
                   "environment": {"python": platform.python_version(), "pandas": pd.__version__,
                                   "numpy": np.__version__, "sklearn": sklearn.__version__}}, h, indent=2, default=str)
    return {"a": a, "ev_a": ev_a, "b": b, "ev_b": ev_b, "out_dir": out}


def main() -> None:
    r = run()
    print(json.dumps({"A": {k: r["ev_a"][k] for k in ("passed", "expectancy", "t", "p", "control_p95", "by_year", "criteria")},
                      "B": {k: r["ev_b"][k] for k in ("passed", "expectancy", "t", "p", "criteria")}}, indent=2, default=str))
    print(f"written: {r['out_dir']}")


if __name__ == "__main__":
    main()
