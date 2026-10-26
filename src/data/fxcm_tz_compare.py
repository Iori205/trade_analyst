"""Day-by-day timezone test of HistData against FXCM (documented-UTC) bid candles.

Read-only. For each FXCM UTC weekday, HistData source-clock labels L are compared
with FXCM minute L + k for k in -720..+720 (label arithmetic only; nothing is
shifted on disk). Each day is judged with the pre-registered rule
(reference_compare.assess_peak), then days are grouped by era and DST regime
and each timezone candidate is scored per cell.

Run:
    .venv/bin/python -m src.data.fxcm_tz_compare --fxcm data/fxcm/53.csv [more files ...]
    .venv/bin/python -m src.data.fxcm_tz_compare --sunday-opens   # HistData only, no FXCM needed
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from src.data.audit import load_config, load_raw, md_table, validate_ohlc, write_new
from src.data.fxcm_audit import read_fxcm_csv, side_frame
from src.data.inventory import discover_raw_files, sha256_file
from src.data.investigate import dst_regime, holiday_calendar
from src.data.reference_compare import (
    MIN_CORRELATION, MIN_PEAK_RATIO, MIN_SHARED_MINUTES, PRICE_COLUMNS, assess_peak, histdata_files_for_window,
    join_at_offset, label_minutes, load_histdata_window, minute_returns, null_check,
    offset_scan, price_summary, rollover_minutes_utc,
)

MAX_OFFSET = 720
LONG_GAP_MINUTES = 30          # matches audit.short_gap_max_minutes
SESSION_OPEN_SKIP = 15         # minutes after a long gap excluded from returns
MIN_CELL_DAYS = 5              # pre-registered: decisive days per era/regime
MIN_MATCH_SHARE = 0.9          # pre-registered: share of decisive days matching
CLEARLY_WORSE_SHARE = 0.5      # a rival is "clearly worse" if it matches < 50% in some filled cell
COMMON_SOURCE_SHARE = 0.9      # identical OHLC share suggesting a shared upstream
# Source-clock hypotheses: label = local time of `zone` + shift. Predictions come from the tz database.
TZ_HYPOTHESES = {
    "H1_fixed_utc-5": ("Etc/GMT+5", 0),             # fixed UTC-5 (POSIX sign: Etc/GMT+5 is UTC-5)
    "H2_america_new_york": ("America/New_York", 0),
    "H3_zurich_minus_6h": ("Europe/Zurich", -360),  # Zurich local time minus 6 hours (EU switch dates)
}
# Provisional era boundary under test. Every weekday from 2018-11-05 to 2019-03-08 is both-standard,
# where all hypotheses agree, so any date in that span is indistinguishable from this one.
ERA_BOUNDARY = pd.Timestamp("2018-12-16")
ERAS = ("before_2018-12-16", "from_2018-12-16")
CANDIDATES = {
    "C1_fixed_utc-5": {ERAS[0]: "H1_fixed_utc-5", ERAS[1]: "H1_fixed_utc-5"},
    "C2_america_new_york": {ERAS[0]: "H2_america_new_york", ERAS[1]: "H2_america_new_york"},
    "C3_zurich_minus_6h": {ERAS[0]: "H3_zurich_minus_6h", ERAS[1]: "H3_zurich_minus_6h"},
    "C4_h2_then_h3_at_2018-12-16": {ERAS[0]: "H2_america_new_york", ERAS[1]: "H3_zurich_minus_6h"},
    "C4r_h3_then_h2_at_2018-12-16": {ERAS[0]: "H3_zurich_minus_6h", ERAS[1]: "H2_america_new_york"},
}
REGIME_ORDER = ["both_standard", "both_summer", "us_summer_eu_standard"]
NY_MARKET_OPEN = dt.time(17, 0)  # weekly open convention (broker practice, not an exchange rule)


def era_of(when) -> str:
    return ERAS[0] if pd.Timestamp(when).tz_localize(None) < ERA_BOUNDARY else ERAS[1]


def source_label(hypothesis: str, utc_instant) -> pd.Timestamp:
    """Naive source-clock label that `hypothesis` assigns to a UTC instant."""
    zone, shift = TZ_HYPOTHESES[hypothesis]
    u = pd.Timestamp(utc_instant)
    u = u.tz_localize("UTC") if u.tzinfo is None else u.tz_convert("UTC")
    return u.tz_convert(ZoneInfo(zone)).tz_localize(None) + pd.Timedelta(minutes=shift)


def predicted_offset_minutes(hypothesis: str, utc_instant) -> int:
    """k such that reference UTC minute = HistData label + k, under `hypothesis`."""
    u = pd.Timestamp(utc_instant)
    u = u.tz_localize("UTC") if u.tzinfo is None else u.tz_convert("UTC")
    return int((u.tz_localize(None) - source_label(hypothesis, u)) / pd.Timedelta(minutes=1))


def candidate_offset_minutes(candidate: str, utc_instant) -> int:
    return predicted_offset_minutes(CANDIDATES[candidate][era_of(utc_instant)], utc_instant)


def gap_mask_minutes(minutes: np.ndarray, long_gap: int = LONG_GAP_MINUTES, skip: int = SESSION_OPEN_SKIP) -> set[int]:
    """Minutes within `skip` of the first bar after a gap longer than `long_gap`."""
    m = np.sort(np.unique(minutes))
    starts = m[1:][np.diff(m) > long_gap]
    return {int(s + i) for s in starts for i in range(skip)}


def long_gaps(minutes: np.ndarray, lo: int, hi: int, long_gap: int = LONG_GAP_MINUTES) -> list[tuple[int, int]]:
    """(last bar, next bar) pairs with a gap > long_gap whose missing span overlaps [lo, hi)."""
    m = np.sort(np.unique(minutes))
    out = []
    for a, b in zip(m[:-1], m[1:]):
        if b - a - 1 > long_gap and a + 1 < hi and b > lo:
            out.append((int(a), int(b)))
    return out


def minute_text(m: int) -> str:
    return str(pd.Timestamp(np.datetime64(int(m), "m")))


def day_exclusion(day: pd.Timestamp, fx_minutes: np.ndarray) -> str:
    """Day-level reason to exclude a UTC day from decisive metrics, or ''."""
    if day.dayofweek >= 5:
        return "weekend (market closed / Sunday session open)"
    names = holiday_calendar(day.year).get(day.normalize())
    if names:
        return "holiday candidate: " + "; ".join(names)
    lo = int(label_minutes(pd.Series([day]))[0])
    gaps = long_gaps(fx_minutes, lo, lo + 1440)
    # A weekday ends at the Friday close; only gaps before the last FXCM bar of the day count
    day_bars = fx_minutes[(fx_minutes >= lo) & (fx_minutes < lo + 1440)]
    inner = [g for g in gaps if len(day_bars) and g[0] >= day_bars.min() and g[1] <= day_bars.max()]
    if inner:
        return "long FXCM gap: " + "; ".join(f"{minute_text(a)}->{minute_text(b)}" for a, b in inner)
    return ""


def compare_day(day: pd.Timestamp, hist: pd.DataFrame, bid: pd.DataFrame, ref: pd.DataFrame,
                hist_returns: pd.Series, fx_returns: pd.Series, hist_minutes: np.ndarray, fx_minutes: np.ndarray,
                max_offset: int = MAX_OFFSET) -> tuple[dict, pd.DataFrame]:
    lo = int(label_minutes(pd.Series([day]))[0])
    hi = lo + 1440
    exclude = rollover_minutes_utc(pd.Timestamp(day, tz="UTC")) | gap_mask_minutes(fx_minutes)
    day_ref = fx_returns[(fx_returns.index >= lo) & (fx_returns.index < hi)]
    excluded_minutes = int(day_ref.index.isin(list(exclude)).sum())
    scan = offset_scan(hist_returns, day_ref, range(-max_offset, max_offset + 1), exclude_ref_minutes=exclude)
    row = {"utc_day": day.date().isoformat(), "weekday": day.day_name(), "year": day.year, "era": era_of(day),
           "regime": dst_regime(pd.Series([day])).iloc[0], "fxcm_bars": int(((fx_minutes >= lo) & (fx_minutes < hi)).sum()),
           "fxcm_returns": len(day_ref), "minutes_excluded_rollover_or_session_open": excluded_minutes}
    if scan["pearson"].notna().any():
        peak = assess_peak(scan)
        sp = assess_peak(scan, "spearman")
        row.update({k: peak[k] for k in ("best_offset_minutes", "best_correlation", "best_shared_minutes",
                                         "runner_up_offset_minutes", "runner_up_correlation", "peak_ratio",
                                         "decisive_day")})
        row.update(spearman_best_offset=sp["best_offset_minutes"], spearman_best=sp["best_correlation"],
                   spearman_agrees=sp["best_offset_minutes"] == peak["best_offset_minutes"],
                   null_far_abs_corr_median=null_check(scan, peak["best_offset_minutes"])["far_abs_corr_median"])
    else:
        row.update(best_offset_minutes=None, decisive_day=False)
    # Weekday offsets are constant within a day (switches happen on Sundays); evaluate at 12:00 UTC
    preds = pd.Series({h: predicted_offset_minutes(h, day + pd.Timedelta(hours=12)) for h in TZ_HYPOTHESES})
    for h, k in preds.items():
        row[f"pred_{h}"] = int(k)
        hit = scan.loc[scan["offset_minutes"] == k]
        row[f"corr_at_{h}"] = round(float(hit["pearson"].iloc[0]), 4) if len(hit) and hit["pearson"].notna().any() else None
    row["hypotheses_matching_best"] = ",".join(h for h, k in preds.items() if k == row.get("best_offset_minutes")) or "none"
    # Long HistData gaps falling inside the day at the best offset
    if row.get("best_offset_minutes") is not None:
        k = row["best_offset_minutes"]
        hg = long_gaps(hist_minutes + k, lo, hi)
        inner = [g for g in hg if len(day_ref) and g[0] >= day_ref.index.min() and g[1] <= day_ref.index.max()]
        row["histdata_long_gaps_at_best"] = "; ".join(f"{minute_text(a - k)}->{minute_text(b - k)} (label)" for a, b in inner)
    # Price levels: exact labels (k = 0) and best offset
    for tag, k in (("exact", 0), ("best", row.get("best_offset_minutes"))):
        if k is None:
            continue
        j = join_at_offset(hist, ref, int(k), ref_ts_column="timestamp_label")
        keys = label_minutes(pd.to_datetime(j["reference_utc"], format="%m/%d/%Y %H:%M:%S.%f"))
        j = j[(keys >= lo) & (keys < hi)]
        both = j[j["present_in"] == "both"]
        row[f"{tag}_pairs"] = len(both)
        row[f"{tag}_fxcm_only"] = int((j["present_in"] == "reference_only").sum())
        if len(both):
            diffs = both[[f"{c}_diff_pips" for c in PRICE_COLUMNS]]
            row[f"{tag}_identical_ohlc_share"] = round(float((diffs == 0).all(axis=1).mean()), 4)
            row[f"{tag}_close_median_abs_diff_pips"] = round(float(diffs["close_diff_pips"].abs().median()), 3)
            row[f"{tag}_close_within_0_5_pip_share"] = round(float((diffs["close_diff_pips"].abs() <= 0.5).mean()), 4)
    scan = scan.assign(utc_day=row["utc_day"])
    return row, scan


def file_label(path: Path) -> str:
    """Year/week names repeat across years (2018/44.csv.gz, 2019/44.csv.gz), so keep the parent folder."""
    return "/".join(Path(path).parts[-2:])


def week_tests() -> dict[str, callable]:
    """Offset predictors compared per week: exact labels, each hypothesis, and the era-boundary combinations."""
    tests = {"exact_labels_k0": lambda when: 0}
    tests.update({h: (lambda when, h=h: predicted_offset_minutes(h, when)) for h in TZ_HYPOTHESES})
    tests.update({c: (lambda when, c=c: candidate_offset_minutes(c, when))
                  for c in CANDIDATES if CANDIDATES[c][ERAS[0]] != CANDIDATES[c][ERAS[1]]})
    return tests


def weekly_rows(path: Path, daily: list[dict], hist: pd.DataFrame, ref: pd.DataFrame, hist_returns: pd.Series,
                fx_returns: pd.Series, fx_minutes: np.ndarray, max_offset: int = MAX_OFFSET) -> list[dict]:
    """One row per (week file, test): presence match, OHLC pip differences, and the week's best/second offsets."""
    usable = [pd.Timestamp(r["utc_day"]) for r in daily if not r["exclusion_reason"]]
    if not usable:
        return []
    keep, exclude = [], set(gap_mask_minutes(fx_minutes))
    for day in usable:
        lo = int(label_minutes(pd.Series([day]))[0])
        keep.append((lo, lo + 1440))
        exclude |= rollover_minutes_utc(pd.Timestamp(day, tz="UTC"))
    idx = fx_returns.index.to_numpy()
    in_days = np.zeros(len(idx), dtype=bool)
    for lo, hi in keep:
        in_days |= (idx >= lo) & (idx < hi)
    scan = offset_scan(hist_returns, fx_returns[in_days], range(-max_offset, max_offset + 1), exclude_ref_minutes=exclude)
    peak = assess_peak(scan)
    mid = usable[len(usable) // 2] + pd.Timedelta(hours=12)
    regimes = sorted(set(dst_regime(pd.Series(usable))))
    base = {"fxcm_file": file_label(path), "week_days_used": ",".join(d.date().isoformat() for d in usable),
            "regime": "+".join(regimes), "era": era_of(mid), "best_offset_minutes": peak["best_offset_minutes"],
            "best_correlation": peak["best_correlation"], "second_offset_minutes": peak["runner_up_offset_minutes"],
            "second_correlation": peak["runner_up_correlation"], "peak_ratio": peak["peak_ratio"],
            "week_decisive": peak["decisive_day"]}
    fx_keys = label_minutes(ref["timestamp_label"])
    day_keys = np.zeros(len(fx_keys), dtype=bool)
    for lo, hi in keep:
        day_keys |= (fx_keys >= lo) & (fx_keys < hi)
    fx_bars = int(day_keys.sum())
    rows = []
    for name, predictor in week_tests().items():
        k = int(predictor(mid))
        j = join_at_offset(hist, ref, k, ref_ts_column="timestamp_label")
        keys = label_minutes(pd.to_datetime(j["reference_utc"], format="%m/%d/%Y %H:%M:%S.%f"))
        sel = np.zeros(len(j), dtype=bool)
        for lo, hi in keep:
            sel |= (keys >= lo) & (keys < hi)
        both = j[sel & (j["present_in"] == "both").to_numpy()]
        diffs = both[[f"{c}_diff_pips" for c in PRICE_COLUMNS]].abs()
        hit = scan.loc[scan["offset_minutes"] == k, "pearson"]
        rows.append({**base, "test": name, "predicted_offset_minutes": k,
                     "is_best_offset": k == peak["best_offset_minutes"],
                     "corr_at_predicted": round(float(hit.iloc[0]), 4) if len(hit) and hit.notna().all() else None,
                     "fxcm_bars": fx_bars, "timestamp_match_pct": round(100 * len(both) / fx_bars, 2) if fx_bars else None,
                     "identical_ohlc_pct": round(100 * float((diffs == 0).all(axis=1).mean()), 2) if len(both) else None,
                     "close_median_abs_pips": round(float(diffs["close_diff_pips"].median()), 3) if len(both) else None,
                     "close_p95_abs_pips": round(float(diffs["close_diff_pips"].quantile(0.95)), 3) if len(both) else None,
                     "ohlc_median_abs_pips": round(float(diffs.stack().median()), 3) if len(both) else None,
                     "ohlc_p95_abs_pips": round(float(diffs.stack().quantile(0.95)), 3) if len(both) else None})
    return rows


def compare_file(path: Path, raw_dir: Path, pattern: str, max_offset: int = MAX_OFFSET) -> tuple[list[dict], list[pd.DataFrame], dict, list[dict]]:
    fxcm = read_fxcm_csv(path)
    bid = side_frame(fxcm, "bid", path.name)
    ref = pd.DataFrame({"source_row": fxcm["source_row"], "timestamp_text": fxcm["timestamp_text"],
                        "timestamp_label": fxcm["timestamp_label"], **{f: fxcm[f"bid_{f}"] for f in PRICE_COLUMNS}})
    start, end = fxcm["timestamp_label"].min(), fxcm["timestamp_label"].max() + pd.Timedelta(minutes=1)
    pad = pd.Timedelta(minutes=max_offset + 1)
    paths = histdata_files_for_window(raw_dir, pattern, start - pad, end + pad)
    info = {"fxcm_file": str(path), "fxcm_sha256": sha256_file(path), "fxcm_rows": len(fxcm),
            "fxcm_first_label": str(start), "fxcm_last_label": str(end - pd.Timedelta(minutes=1)),
            "fxcm_bid_ohlc_violations": int(len(validate_ohlc(bid))),
            "histdata_files": [str(p) for p in paths]}
    if not paths:
        info["skipped"] = "no HistData file overlaps"
        return [], [], info, []
    hist = load_histdata_window(paths, start - pad, end + pad)
    hist_returns, fx_returns = minute_returns(hist, "timestamp"), minute_returns(bid, "timestamp")
    hist_minutes, fx_minutes = label_minutes(hist["timestamp"]), label_minutes(bid["timestamp"])
    rows, scans = [], []
    for day in pd.date_range(start.normalize(), (end - pd.Timedelta(minutes=1)).normalize(), freq="D"):
        reason = day_exclusion(day, fx_minutes)
        row, scan = compare_day(day, hist, bid, ref, hist_returns, fx_returns, hist_minutes, fx_minutes, max_offset)
        row["fxcm_file"] = file_label(path)
        row["exclusion_reason"] = reason
        if not reason and row.get("histdata_long_gaps_at_best"):
            row["exclusion_reason"] = "long HistData gap at best offset: " + row["histdata_long_gaps_at_best"]
        row["counts_as_decisive"] = bool(row.get("decisive_day")) and not row["exclusion_reason"]
        rows.append(row)
        scans.append(scan.assign(fxcm_file=file_label(path)))
    weekly = weekly_rows(path, rows, hist, ref, hist_returns, fx_returns, fx_minutes, max_offset)
    return rows, scans, info, weekly


def cell_summary(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for era in ERAS:
        for regime in REGIME_ORDER:
            cell = daily[(daily["era"] == era) & (daily["regime"] == regime)]
            dec = cell[cell["counts_as_decisive"]]
            row = {"era": era, "regime": regime, "days": len(cell), "excluded_days": int((cell["exclusion_reason"] != "").sum()),
                   "decisive_days": len(dec),
                   "best_offsets_seen": ",".join(f"{k:+d}x{n}" for k, n in dec["best_offset_minutes"].astype(int).value_counts().items())}
            for h in TZ_HYPOTHESES:
                row[f"match_{h}"] = int((dec["best_offset_minutes"] == dec[f"pred_{h}"]).sum()) if len(dec) else 0
            rows.append(row)
    return pd.DataFrame(rows)


def candidate_verdicts(cells: pd.DataFrame) -> pd.DataFrame:
    """Score each candidate per cell; a cell is 'filled' once it has MIN_CELL_DAYS decisive days."""
    rows = []
    for cand, by_era in CANDIDATES.items():
        filled = passed = 0
        contradicted, missing = [], []
        for c in cells.to_dict("records"):
            h = by_era[c["era"]]
            share = c[f"match_{h}"] / c["decisive_days"] if c["decisive_days"] else np.nan
            cell = f"{c['era']}/{c['regime']}"
            if c["decisive_days"] >= MIN_CELL_DAYS:
                filled += 1
                if share >= MIN_MATCH_SHARE:
                    passed += 1
                elif share < CLEARLY_WORSE_SHARE:
                    contradicted.append(f"{cell} ({share:.0%})")
            else:
                missing.append(f"{cell} ({c['decisive_days']} decisive)")
                if c["decisive_days"] and share < CLEARLY_WORSE_SHARE:
                    contradicted.append(f"{cell} ({share:.0%}, under-filled)")
        rows.append({"candidate": cand, "cells_filled": filled, "cells_passed": passed, "cells_total": len(cells),
                     "contradicted_in": "; ".join(contradicted), "cells_missing_evidence": "; ".join(missing),
                     "accepted": passed == len(cells)})
    out = pd.DataFrame(rows)
    out["recommendable"] = out["accepted"] & (out["accepted"].sum() == 1) & out.apply(
        lambda r: all(o["contradicted_in"] for _, o in out.iterrows() if o["candidate"] != r["candidate"]), axis=1)
    return out


def run(root: Path, config: dict, fxcm_paths: list[Path]) -> dict:
    data_cfg = config["data"]
    raw_dir = root / data_cfg["raw_dir"]
    tracked = (discover_raw_files(raw_dir, data_cfg["raw_csv_glob"])
               + sorted(raw_dir.glob(data_cfg["raw_csv_glob"].replace(".csv", ".txt")))
               + [root / p for p in data_cfg["parquet_files"].values()]
               + sorted((raw_dir / "dukascopy").glob("*.csv")) + sorted((raw_dir / "fxcm").glob("*"))
               + list(fxcm_paths))
    tracked = sorted(set(tracked))
    before = {str(p): sha256_file(p) for p in tracked}
    rows, scans, infos, weekly = [], [], [], []
    for p in fxcm_paths:
        r, s, info, w = compare_file(p, raw_dir, data_cfg["raw_csv_glob"])
        rows += r
        scans += s
        weekly += w
        infos.append(info)
    daily = pd.DataFrame(rows)
    cells = cell_summary(daily) if len(daily) else pd.DataFrame()
    after = {str(p): sha256_file(p) for p in tracked}
    return {"daily": daily, "weekly": pd.DataFrame(weekly), "scans": pd.concat(scans, ignore_index=True) if scans else pd.DataFrame(),
            "cells": cells, "verdicts": candidate_verdicts(cells) if len(cells) else pd.DataFrame(),
            "files": infos, "hashes_before": before, "hashes_unchanged": before == after,
            "rules": {"max_offset_minutes": MAX_OFFSET, "min_correlation": MIN_CORRELATION,
                      "min_peak_ratio": MIN_PEAK_RATIO, "min_shared_minutes": MIN_SHARED_MINUTES,
                      "min_cell_decisive_days": MIN_CELL_DAYS, "min_match_share": MIN_MATCH_SHARE,
                      "clearly_worse_share": CLEARLY_WORSE_SHARE, "long_gap_minutes": LONG_GAP_MINUTES,
                      "session_open_skip_minutes": SESSION_OPEN_SKIP,
                      "era_boundary": str(ERA_BOUNDARY.date()), "hypotheses": TZ_HYPOTHESES}}


def sunday_first_bars(raw: pd.DataFrame) -> pd.DataFrame:
    """First Sunday bar of each week, as written (duplicated labels kept as rows; nothing is changed)."""
    ts = raw["timestamp"]
    sunday = raw[ts.dt.dayofweek == 6]
    first = sunday.loc[sunday.groupby(sunday["timestamp"].dt.normalize())["timestamp"].idxmin()]
    df = pd.DataFrame({"sunday": first["timestamp"].dt.normalize().dt.date.astype(str).to_numpy(),
                       "first_bar_label": first["timestamp"].astype(str).to_numpy(),
                       "first_bar_hm": first["timestamp"].dt.strftime("%H:%M").to_numpy(),
                       "source_file": first["source_file"].astype(str).to_numpy(),
                       "line_number": (first["source_row"] + 1).to_numpy()})
    days = pd.to_datetime(df["sunday"])
    df["regime"] = dst_regime(days).to_numpy()
    df["era"] = [era_of(d) for d in days]
    for h in TZ_HYPOTHESES:
        # Predicted label of the 17:00 New York open on that Sunday
        opens = [pd.Timestamp(dt.datetime.combine(d.date(), NY_MARKET_OPEN), tz="America/New_York") for d in days]
        df[f"{h}_predicted_hm"] = [source_label(h, o).strftime("%H:%M") for o in opens]
        df[f"{h}_consistent"] = df[f"{h}_predicted_hm"] == df["first_bar_hm"]
    return df


def sunday_open_table(opens: pd.DataFrame) -> pd.DataFrame:
    """Weeks per era x regime x observed first-bar time, with each hypothesis's prediction."""
    agg = {"weeks": ("sunday", "size"),
           "first_bar_times_seen": ("first_bar_hm", lambda s: ", ".join(f"{t}x{n}" for t, n in s.value_counts().sort_index().items()))}
    for h in TZ_HYPOTHESES:
        agg[f"{h}_predicts"] = (f"{h}_predicted_hm", lambda s: ",".join(sorted(set(s))))
        agg[f"{h}_consistent_weeks"] = (f"{h}_consistent", "sum")
    out = opens.groupby(["era", "regime"], sort=False).agg(**agg).reset_index()
    order = {(e, r): i for i, (e, r) in enumerate((e, r) for e in ERAS for r in REGIME_ORDER)}
    out["_order"] = [order[(e, r)] for e, r in zip(out["era"], out["regime"])]
    return out.sort_values("_order").drop(columns="_order").reset_index(drop=True)


def run_sunday_opens(root: Path, config: dict) -> dict:
    data_cfg = config["data"]
    paths = discover_raw_files(root / data_cfg["raw_dir"], data_cfg["raw_csv_glob"])
    before = {str(p): sha256_file(p) for p in paths}
    opens = sunday_first_bars(load_raw(paths))
    after = {str(p): sha256_file(p) for p in paths}
    return {"opens": opens, "table": sunday_open_table(opens), "hashes_unchanged": before == after, "files": len(paths)}


def write_outputs(r: dict, reports_dir: Path, stamp: str | None = None) -> Path:
    stamp = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(reports_dir) / f"fxcm_tz_comparison_{stamp}"
    out.mkdir(parents=False, exist_ok=False)
    for name in ("daily", "weekly", "cells", "verdicts", "scans"):
        with open(out / f"{name}.csv", "x", encoding="utf-8", newline="") as handle:
            r[name].to_csv(handle, index=False)
    write_new(out / "run.json", json.dumps({"files": r["files"], "rules": r["rules"],
                                            "tracked_files_unchanged": r["hashes_unchanged"],
                                            "hashes_before": r["hashes_before"]}, indent=2))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fxcm", type=Path, nargs="+")
    parser.add_argument("--sunday-opens", action="store_true", help="tabulate HistData Sunday first bars only")
    parser.add_argument("--config", type=Path, default=Path("config/research.yaml"))
    args = parser.parse_args()
    root = Path.cwd()
    config = load_config(args.config)
    if args.sunday_opens:
        s = run_sunday_opens(root, config)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = root / config["reports"]["dir"] / f"sunday_opens_{stamp}"
        out.mkdir(parents=False, exist_ok=False)
        for name, df in (("sunday_first_bars", s["opens"]), ("sunday_open_table", s["table"])):
            with open(out / f"{name}.csv", "x", encoding="utf-8", newline="") as handle:
                df.to_csv(handle, index=False)
        write_new(out / "summary.md", "# HistData Sunday first bars by era and DST regime\n\n"
                  f"Raw files read: {s['files']}; unchanged during run: **{s['hashes_unchanged']}**. Labels as written; "
                  f"predictions are the 17:00 New York open under each hypothesis.\n\n{md_table(s['table'])}\n")
        print(s["table"].to_string(index=False))
        print(f"raw files unchanged: {s['hashes_unchanged']}\nreport: {out}")
        return
    if not args.fxcm:
        parser.error("--fxcm is required unless --sunday-opens is given")
    r = run(root, config, args.fxcm)
    out = write_outputs(r, root / config["reports"]["dir"])
    cols = ["utc_day", "regime", "best_offset_minutes", "best_correlation", "peak_ratio", "best_shared_minutes",
            "decisive_day", "exclusion_reason", "hypotheses_matching_best"]
    print(r["daily"][[c for c in cols if c in r["daily"]]].to_string(index=False))
    print(r["cells"].to_string(index=False))
    print(r["verdicts"].to_string(index=False))
    print(f"tracked files unchanged: {r['hashes_unchanged']}\nreport: {out}")


if __name__ == "__main__":
    main()
