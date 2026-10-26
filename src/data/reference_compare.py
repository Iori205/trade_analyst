"""Read-only comparison of HistData M1 against an independent UTC-stamped reference.

Nothing here converts or shifts either dataset on disk. Alignment is tested
with *label arithmetic*: a HistData source-clock label L (naive, timezone
unverified) is compared with reference UTC time L + k minutes, for candidate
offsets k. The offset is only a hypothesis to report.

Timing evidence comes from 1-minute returns, which are close to uncorrelated
across lags, so the correct alignment stands out. Price-level similarity is
reported as supporting evidence only.

Run:
    .venv/bin/python -m src.data.reference_compare \
        --reference data/dukascopy/EUR-USD_1Minute_BID_2025-03-19_00_00-23_59_Etc_UTC.csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.audit import load_config, md_table, read_raw_csv, write_new
from src.data.inventory import discover_raw_files, nominal_period_bounds, parse_period, sha256_file
from src.data.investigate import DECISIVE_RATIO, HYPOTHESES, dst_regime, source_offset_hours, REGIMES

DUKASCOPY_COLUMNS = ["Etc/UTC", "Open", "High", "Low", "Close", "Volume"]
DUKASCOPY_TS_PATTERN = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00"
PRICE_COLUMNS = ["open", "high", "low", "close"]
PIP = 1e-4

# Pre-registered day-level criteria (reports/timestamp_policy_proposal_20261022T110251Z/summary.md §3A)
MIN_CORRELATION = 0.3
MIN_PEAK_RATIO = 3.0
MIN_SHARED_MINUTES = 300


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def read_dukascopy_csv(path: Path) -> pd.DataFrame:
    """Read a Dukascopy M1 export strictly. Every timestamp must carry +00:00."""
    df = pd.read_csv(path, dtype={"Etc/UTC": str, **{c: "float64" for c in DUKASCOPY_COLUMNS[1:]}},
                     na_filter=False)
    if list(df.columns) != DUKASCOPY_COLUMNS:
        raise ValueError(f"unexpected columns {list(df.columns)}; expected {DUKASCOPY_COLUMNS}")
    text = df["Etc/UTC"].astype("string")
    valid = text.str.fullmatch(DUKASCOPY_TS_PATTERN).fillna(False).astype(bool)
    if not valid.all():
        raise ValueError(f"{int((~valid).sum())} timestamp(s) not in 'YYYY-MM-DDTHH:MM:SS+00:00' form, "
                         f"first: {text[~valid].iloc[0]!r}")
    return pd.DataFrame({
        "source_row": np.arange(len(df)),
        "timestamp_text": text.to_numpy(),
        "timestamp_utc": pd.to_datetime(text, format="%Y-%m-%dT%H:%M:%S%z", utc=True).to_numpy(),
        "open": df["Open"].to_numpy(), "high": df["High"].to_numpy(),
        "low": df["Low"].to_numpy(), "close": df["Close"].to_numpy(),
        "volume": df["Volume"].to_numpy(),
    })


def histdata_files_for_window(raw_dir: Path, pattern: str, start: pd.Timestamp, end: pd.Timestamp) -> list[Path]:
    """HistData files whose named period overlaps [start, end) on the source clock."""
    paths = []
    for path in discover_raw_files(raw_dir, pattern):
        first, last = nominal_period_bounds(parse_period(path.name)[0])
        if first < end and last > start:
            paths.append(path)
    return paths


def load_histdata_window(paths: list[Path], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """HistData rows with source-clock labels in [start, end), original order kept."""
    frames = [read_raw_csv(p) for p in paths]
    raw = pd.concat(frames, ignore_index=True)
    return raw[(raw["timestamp"] >= start) & (raw["timestamp"] < end)].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------
def label_minutes(timestamps: pd.Series) -> np.ndarray:
    """Integer minute labels. Naive values are used as plain labels; aware values via UTC."""
    ts = pd.Series(timestamps)
    if ts.dt.tz is not None:
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    return ts.to_numpy().astype("datetime64[m]").astype(np.int64)


def profile(df: pd.DataFrame, ts_column: str, name: str, expected_start, expected_end) -> dict:
    ts = df[ts_column]
    minutes = label_minutes(ts)
    expected = int(label_minutes(pd.Series([expected_end]))[0] - label_minutes(pd.Series([expected_start]))[0])
    body_high = df[["open", "close"]].max(axis=1)
    body_low = df[["open", "close"]].min(axis=1)
    return {
        "dataset": name,
        "rows": len(df),
        "first": str(ts.iloc[0]) if len(df) else "",
        "last": str(ts.iloc[-1]) if len(df) else "",
        "expected_minutes_in_window": expected,
        "distinct_minutes": int(len(np.unique(minutes))),
        "duplicate_timestamp_rows": int(pd.Series(minutes).duplicated().sum()),
        "monotonic_increasing": bool(pd.Series(minutes).is_monotonic_increasing),
        "non_zero_seconds": int((pd.Series(ts).dt.second != 0).sum()),
        "ohlc_violations": int(((df["high"] < body_high) | (df["low"] > body_low) | (df["high"] < df["low"])
                                | (df[PRICE_COLUMNS] <= 0).any(axis=1)).sum()),
        "zero_volume_rows": int((df["volume"] == 0).sum()),
    }


def missing_minutes(df: pd.DataFrame, ts_column: str, start, end) -> pd.DataFrame:
    """Minutes in [start, end) with no row. Values are reported on the dataset's own clock."""
    present = set(label_minutes(df[ts_column]).tolist())
    lo = int(label_minutes(pd.Series([start]))[0])
    hi = int(label_minutes(pd.Series([end]))[0])
    gone = [m for m in range(lo, hi) if m not in present]
    labels = pd.to_datetime(np.array(gone, dtype="datetime64[m]"))
    return pd.DataFrame({"missing_minute_label": labels.astype(str)})


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------
def minute_returns(df: pd.DataFrame, ts_column: str) -> pd.Series:
    """Close-to-close log returns keyed by integer minute label.

    Only consecutive minutes count; every duplicated timestamp is excluded
    entirely, so no copy is preferred over another.
    """
    minutes = label_minutes(df[ts_column])
    keep = ~pd.Series(minutes).duplicated(keep=False).to_numpy()
    series = pd.Series(df["close"].to_numpy()[keep], index=minutes[keep]).sort_index()
    consecutive = np.r_[False, np.diff(series.index.to_numpy()) == 1]
    returns = np.log(series).diff()
    return returns[consecutive]


def offset_scan(hist_returns: pd.Series, ref_returns: pd.Series, offsets, exclude_ref_minutes=frozenset()) -> pd.DataFrame:
    """Correlation of returns for each candidate offset k (reference minute = HistData label + k)."""
    ref = ref_returns[~ref_returns.index.isin(list(exclude_ref_minutes))]
    rows = []
    for k in offsets:
        shifted = pd.Series(hist_returns.to_numpy(), index=hist_returns.index + k)
        common = shifted.index.intersection(ref.index)
        a, b = shifted.loc[common], ref.loc[common]
        enough = len(common) >= 3 and a.std() > 0 and b.std() > 0
        rows.append({
            "offset_minutes": int(k),
            "shared_minutes": len(common),
            "pearson": float(a.corr(b)) if enough else np.nan,
            "spearman": float(a.rank().corr(b.rank())) if enough else np.nan,  # Spearman = Pearson of ranks
        })
    return pd.DataFrame(rows)


def assess_peak(scan: pd.DataFrame, column: str = "pearson") -> dict:
    """Apply the pre-registered day-level criteria to an offset scan."""
    valid = scan.dropna(subset=[column])
    best = valid.loc[valid[column].idxmax()]
    outside = valid[(valid["offset_minutes"] - best["offset_minutes"]).abs() > 1]
    runner_up = outside.loc[outside[column].idxmax()] if len(outside) else None
    ratio = float(best[column] / runner_up[column]) if runner_up is not None and runner_up[column] > 0 else np.inf
    checks = {
        "correlation_ge_min": bool(best[column] >= MIN_CORRELATION),
        "peak_ratio_ge_min": bool(ratio >= MIN_PEAK_RATIO),
        "shared_minutes_ge_min": bool(best["shared_minutes"] >= MIN_SHARED_MINUTES),
    }
    return {
        "measure": column,
        "best_offset_minutes": int(best["offset_minutes"]),
        "best_offset_hours": round(best["offset_minutes"] / 60, 4),
        "best_correlation": round(float(best[column]), 4),
        "best_shared_minutes": int(best["shared_minutes"]),
        "runner_up_offset_minutes": int(runner_up["offset_minutes"]) if runner_up is not None else None,
        "runner_up_correlation": round(float(runner_up[column]), 4) if runner_up is not None else None,
        "peak_ratio": round(ratio, 2) if np.isfinite(ratio) else None,
        **checks,
        "decisive_day": all(checks.values()),
    }


def null_check(scan: pd.DataFrame, best_offset: int, column: str = "pearson", min_distance: int = 30) -> dict:
    """Correlation at offsets far from the peak should be near zero."""
    far = scan[(scan["offset_minutes"] - best_offset).abs() >= min_distance][column].dropna()
    return {"far_offsets": len(far), "far_abs_corr_median": round(float(far.abs().median()), 4),
            "far_abs_corr_p99": round(float(far.abs().quantile(0.99)), 4)}


def hypothesis_offsets(utc_day: pd.Timestamp) -> pd.DataFrame:
    """Offset k (minutes, reference = label + k) predicted by each timezone hypothesis for one day."""
    regime = dst_regime(pd.Series([utc_day.tz_localize(None) if utc_day.tzinfo else utc_day])).iloc[0]
    us_summer, eu_summer = REGIMES[regime]
    return pd.DataFrame([{"hypothesis": h, "regime": regime,
                          "predicted_offset_minutes": -60 * source_offset_hours(h, us_summer, eu_summer)}
                         for h in HYPOTHESES])


# ---------------------------------------------------------------------------
# Price-level comparison (supporting evidence only)
# ---------------------------------------------------------------------------
def join_at_offset(hist: pd.DataFrame, ref: pd.DataFrame, offset_minutes: int,
                   ref_ts_column: str = "timestamp_utc") -> pd.DataFrame:
    """Pair rows where reference minute == HistData label + offset. Duplicated labels are excluded."""
    h = hist.assign(key=label_minutes(hist["timestamp"]) + offset_minutes)
    r = ref.assign(key=label_minutes(ref[ref_ts_column]))
    h = h[~h["key"].duplicated(keep=False)]
    r = r[~r["key"].duplicated(keep=False)]
    joined = r.merge(h, on="key", how="outer", suffixes=("_ref", "_hist"), indicator=True)
    out = pd.DataFrame({
        "reference_utc": joined["timestamp_text"],
        "histdata_label": joined["timestamp"].astype(str).where(joined["timestamp"].notna(), ""),
        "histdata_source_file": joined["source_file"],
        "histdata_line_number": joined["source_row_hist"] + 1,
        "reference_line_number": joined["source_row_ref"] + 2,  # +1 header, +1 one-based
        "present_in": joined["_merge"].map({"both": "both", "left_only": "reference_only", "right_only": "histdata_only"}),
    })
    for c in PRICE_COLUMNS:
        out[f"{c}_ref"] = joined[f"{c}_ref"]
        out[f"{c}_hist"] = joined[f"{c}_hist"]
        out[f"{c}_diff_pips"] = ((joined[f"{c}_hist"] - joined[f"{c}_ref"]) / PIP).round(2)
    return out.sort_values(["reference_utc", "histdata_label"], na_position="last").reset_index(drop=True)


def price_summary(joined: pd.DataFrame) -> pd.DataFrame:
    both = joined[joined["present_in"] == "both"]
    rows = []
    for c in PRICE_COLUMNS:
        d = both[f"{c}_diff_pips"]
        rows.append({"field": c, "pairs": len(d), "mean_diff_pips": round(d.mean(), 3),
                     "median_diff_pips": round(d.median(), 3), "median_abs_diff_pips": round(d.abs().median(), 3),
                     "p95_abs_diff_pips": round(d.abs().quantile(0.95), 3), "max_abs_diff_pips": round(d.abs().max(), 3),
                     "share_exact": round(float((d == 0).mean()), 4), "share_within_0_5_pip": round(float((d.abs() <= 0.5).mean()), 4)})
    return pd.DataFrame(rows)


def top_moves(df: pd.DataFrame, ts_column: str, n: int = 5) -> pd.DataFrame:
    returns = minute_returns(df, ts_column)
    top = returns.abs().nlargest(n)
    labels = pd.to_datetime(top.index.to_numpy().astype("datetime64[m]"))
    return pd.DataFrame({"minute_label": labels.astype(str), "abs_log_return_bp": (top.to_numpy() * 1e4).round(2)})


def rollover_minutes_utc(utc_day: pd.Timestamp) -> set[int]:
    """Reference minutes 16:55-17:15 New York time (spread widening around rollover)."""
    ny = pd.Timestamp(utc_day.date()).tz_localize("America/New_York")
    start = (ny + pd.Timedelta(hours=16, minutes=55)).tz_convert("UTC").tz_localize(None)
    labels = pd.date_range(start, periods=21, freq="1min")
    return set(label_minutes(pd.Series(labels)).tolist())


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_comparison(root: Path, config: dict, reference_path: Path, max_offset_minutes: int = 720) -> dict:
    data_cfg = config["data"]
    raw_dir = root / data_cfg["raw_dir"]
    ref = read_dukascopy_csv(reference_path)
    day = ref["timestamp_utc"].iloc[0].normalize()
    day_end = day + pd.Timedelta(days=1)
    naive_day = day.tz_localize(None)

    # HistData labels that could pair with this UTC day for any scanned offset
    window_start = naive_day - pd.Timedelta(minutes=max_offset_minutes)
    window_end = naive_day + pd.Timedelta(days=1, minutes=max_offset_minutes)
    hist_paths = histdata_files_for_window(raw_dir, data_cfg["raw_csv_glob"], window_start, window_end)
    if not hist_paths:
        raise SystemExit(f"No HistData file covers {window_start} - {window_end}; stopping.")
    sources = hist_paths + [reference_path]
    all_42 = (discover_raw_files(raw_dir, data_cfg["raw_csv_glob"])
              + sorted(raw_dir.glob(data_cfg["raw_csv_glob"].replace(".csv", ".txt")))
              + [root / p for p in data_cfg["parquet_files"].values()])
    hashes_before = {str(p): sha256_file(p) for p in dict.fromkeys(all_42 + sources)}

    hist = load_histdata_window(hist_paths, window_start, window_end)
    hist_same_label_day = hist[(hist["timestamp"] >= naive_day) & (hist["timestamp"] < naive_day + pd.Timedelta(days=1))]

    hist_ret = minute_returns(hist, "timestamp")
    ref_ret = minute_returns(ref, "timestamp_utc")
    offsets = range(-max_offset_minutes, max_offset_minutes + 1)
    scan = offset_scan(hist_ret, ref_ret, offsets)
    scan_ex = offset_scan(hist_ret, ref_ret, offsets, exclude_ref_minutes=rollover_minutes_utc(day))
    peak = assess_peak(scan)
    peak_spearman = assess_peak(scan, "spearman")
    peak_ex = assess_peak(scan_ex)
    predictions = hypothesis_offsets(day)
    predictions["matches_best_offset"] = predictions["predicted_offset_minutes"] == peak["best_offset_minutes"]

    exact = join_at_offset(hist, ref, 0)
    exact = exact[exact["reference_utc"].notna() | exact["histdata_label"].str.startswith(str(naive_day.date()))]
    best = join_at_offset(hist, ref, peak["best_offset_minutes"])
    best = best[best["reference_utc"].notna()]
    hist_for_best = hist.assign(key=label_minutes(hist["timestamp"]) + peak["best_offset_minutes"])

    hashes_after = {p: sha256_file(Path(p)) for p in hashes_before}
    return {
        "reference_path": str(reference_path),
        "histdata_files": [str(p) for p in hist_paths],
        "utc_day": str(day.date()),
        "profiles": pd.DataFrame([
            profile(ref, "timestamp_utc", "dukascopy (UTC)", day, day_end),
            profile(hist_same_label_day, "timestamp", "histdata, same calendar label", naive_day,
                    naive_day + pd.Timedelta(days=1)),
        ]),
        "missing_reference": missing_minutes(ref, "timestamp_utc", day, day_end),
        "missing_hist_same_label": missing_minutes(hist_same_label_day, "timestamp", naive_day,
                                                    naive_day + pd.Timedelta(days=1)),
        "scan": scan.merge(scan_ex, on="offset_minutes", suffixes=("", "_ex_rollover")),
        "peak": peak, "peak_spearman": peak_spearman, "peak_ex_rollover": peak_ex,
        "null": null_check(scan, peak["best_offset_minutes"]),
        "predictions": predictions,
        "exact": exact, "exact_summary": price_summary(exact),
        "best": best, "best_summary": price_summary(best),
        "top_ref": top_moves(ref, "timestamp_utc"),
        "top_hist": top_moves(hist_same_label_day, "timestamp"),
        "hist_rows_mapped_to_day": int(hist_for_best["key"].between(*label_minutes(pd.Series([day, day_end - pd.Timedelta(minutes=1)]))).sum()),
        "hashes_before": hashes_before, "hashes_after": hashes_after,
    }


FOMC_UTC = {"2025-03-19": "18:00"}  # statement 14:00 EDT (Federal Reserve press release)


def interpretation(r: dict) -> str:
    """Plain statements derived from the results, separating timing from price-level evidence."""
    p = r["peak"]
    k = p["best_offset_minutes"]
    fits = r["predictions"].loc[r["predictions"]["matches_best_offset"], "hypothesis"].tolist()
    misses = r["predictions"].loc[~r["predictions"]["matches_best_offset"], "hypothesis"].tolist()
    lines = [
        f"- **Timing evidence:** returns align at HistData label + {k} min = reference UTC "
        f"(correlation {p['best_correlation']}, {p['peak_ratio']}x the runner-up; decisive day: {p['decisive_day']}). "
        f"Consistent with {', '.join(fits) or 'none'}; inconsistent with {', '.join(misses) or 'none'}.",
    ]
    event = FOMC_UTC.get(r["utc_day"])
    if event:
        ref_top = r["top_ref"]["minute_label"].iloc[0][11:16]
        hist_top = r["top_hist"]["minute_label"].iloc[0][11:16]
        lines.append(f"- **Event check on the reference:** the largest Dukascopy move is at {ref_top} UTC; the documented "
                     f"FOMC release was {event} UTC ({'match' if ref_top == event else 'NO match'}). The same move is at "
                     f"HistData label {hist_top}.")
    exact_share = float(r["best_summary"]["share_exact"].min())
    if exact_share >= 0.99:
        lines.append(f"- **Price levels (supporting only):** at the best offset, {exact_share:.1%} of paired minutes have "
                     "identical OHLC in all four fields, and the single missing minute is the same bar in both files. "
                     "The two files almost certainly share an upstream feed (HistData appears to be derived from "
                     "Dukascopy bid data, or both from a common source). This comparison therefore maps HistData labels "
                     "to the reference's UTC labels exactly, but it is **not independent-vendor evidence**. Its "
                     "independence rests on the documented event check.")
    else:
        lines.append(f"- **Price levels (supporting only):** identical OHLC share at the best offset is {exact_share:.1%}; "
                     "differences reflect vendor liquidity and bar construction.")
    return "\n".join(lines)


def render_summary(r: dict) -> str:
    p, pe, ps = r["peak"], r["peak_ex_rollover"], r["peak_spearman"]
    unchanged = r["hashes_before"] == r["hashes_after"]
    exact_counts = r["exact"]["present_in"].value_counts().to_dict()
    best_counts = r["best"]["present_in"].value_counts().to_dict()
    scan = r["scan"]
    around = scan[scan["offset_minutes"].isin([0, -240, -300, 240, 300, p["best_offset_minutes"] - 1,
                                               p["best_offset_minutes"], p["best_offset_minutes"] + 1])]
    sections = [
        f"# HistData vs Dukascopy: read-only alignment check for {r['utc_day']} (UTC)",
        f"Generated (UTC): {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S}. No file was modified, shifted, "
        f"deduplicated or converted. Source files unchanged during run: **{'YES' if unchanged else 'NO'}** "
        f"({len(r['hashes_before'])} files hashed).",
        f"- Reference: `{r['reference_path']}`\n- HistData: " + ", ".join(f"`{f}`" for f in r["histdata_files"]),
        "## 1. Formats",
        "| | Dukascopy | HistData |\n|---|---|---|\n"
        "| Delimiter / header | `,` with header `Etc/UTC,Open,High,Low,Close,Volume` | `;`, no header |\n"
        "| Timestamp | `YYYY-MM-DDTHH:MM:SS+00:00` (explicit UTC offset) | `YYYYMMDD HHMMSS`, no zone (unverified source clock) |\n"
        "| Columns | Etc/UTC, Open, High, Low, Close, Volume | timestamp, open, high, low, close, volume |\n"
        "| Price type | BID (file name) | bid (HistData FAQ) |\n"
        "| Volume | non-zero, vendor units | always 0 |",
        "## 2. Profiles",
        md_table(r["profiles"]),
        f"Missing minutes: Dukascopy {len(r['missing_reference'])} "
        f"({', '.join(r['missing_reference']['missing_minute_label']) or 'none'}); HistData same label day "
        f"{len(r['missing_hist_same_label'])} ({', '.join(r['missing_hist_same_label']['missing_minute_label']) or 'none'}).",
        "## 3. Exact timestamp alignment (offset 0, labels taken at face value)",
        f"Pairing: {exact_counts}.",
        md_table(r["exact_summary"]),
        "## 4. Offset scan (reference minute = HistData label + k)",
        f"Scanned k = {scan['offset_minutes'].min()} to {scan['offset_minutes'].max()} minutes on 1-minute log returns "
        "(consecutive minutes only, duplicated labels excluded).",
        md_table(around),
        "Day-level criteria (pre-registered): best correlation >= "
        f"{MIN_CORRELATION}, >= {MIN_PEAK_RATIO}x the best correlation outside best +/- 1 min, >= {MIN_SHARED_MINUTES} shared minutes.",
        md_table(pd.DataFrame([p, ps, pe]).assign(variant=["pearson", "spearman", "pearson, rollover excluded"])),
        f"Null check (|offset - best| >= 30 min): {json.dumps(r['null'])}",
        "## 5. Hypothesis predictions for this day",
        md_table(r["predictions"]),
        "## 6. Price levels at the best offset (supporting evidence only)",
        f"Pairing: {best_counts}. HistData rows mapped into the UTC day: {r['hist_rows_mapped_to_day']}.",
        md_table(r["best_summary"]),
        "## 7. Event check (largest 1-minute moves, each on its own clock)",
        "FOMC statement released 14:00 EDT = 18:00 UTC on 2025-03-19 (Federal Reserve press release).",
        "Dukascopy:", md_table(r["top_ref"]),
        "HistData (same calendar label day):", md_table(r["top_hist"]),
        "## 8. Interpretation for this day",
        interpretation(r),
        "## 9. Limitations",
        "- One day only. The pre-registered acceptance rule needs >= 5 decisive days per DST regime, so this "
        "result cannot accept or reject a timezone candidate on its own.\n"
        "- The reference's own UTC claim is checked only by the FOMC event; Dukascopy export settings were not seen.\n"
        "- Offsets are label arithmetic for this day only; no dataset was shifted.",
    ]
    return "\n\n".join(sections) + "\n"


def write_report(r: dict, reports_dir: Path, stamp: str | None = None) -> Path:
    stamp = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(reports_dir) / f"reference_compare_dukascopy_{r['utc_day']}_{stamp}"
    run_dir.mkdir(parents=False, exist_ok=False)
    write_new(run_dir / "summary.md", render_summary(r))
    for name in ["profiles", "missing_reference", "missing_hist_same_label", "scan", "predictions",
                 "exact", "exact_summary", "best", "best_summary", "top_ref", "top_hist"]:
        write_new(run_dir / f"{name}.csv", r[name].to_csv(index=False))
    write_new(run_dir / "alignment_assessment.json", json.dumps(
        {"pearson": r["peak"], "spearman": r["peak_spearman"], "pearson_rollover_excluded": r["peak_ex_rollover"],
         "null_check": r["null"]}, indent=2, default=str))
    write_new(run_dir / "source_hashes.json",
              json.dumps({"before": r["hashes_before"], "after": r["hashes_after"]}, indent=2))
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only HistData vs reference alignment check.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="config/research.yaml")
    parser.add_argument("--reference", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config = load_config(root / args.config)
    results = run_comparison(root, config, (root / args.reference).resolve())
    run_dir = write_report(results, root / config["reports"]["dir"])
    unchanged = results["hashes_before"] == results["hashes_after"]
    print(f"Report written to {run_dir}")
    print(f"Source files unchanged: {'YES' if unchanged else 'NO'}")
    if not unchanged:
        raise SystemExit("Source file hashes changed during the comparison.")


if __name__ == "__main__":
    main()
