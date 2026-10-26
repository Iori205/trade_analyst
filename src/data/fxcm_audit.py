"""Read-only quality audit of an FXCM M1 bid/ask CSV, plus overlap comparison with HistData.

FXCM's documentation says the timestamps are UTC. That claim is recorded but
not assumed: timestamps are parsed as naive labels. Any offset against
HistData is reported as a label-arithmetic hypothesis; nothing is shifted,
filled or written back.

Run:
    .venv/bin/python -m src.data.fxcm_audit --fxcm data/fxcm/53.csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.audit import detect_gaps, load_config, md_table, validate_ohlc, write_new
from src.data.inventory import discover_raw_files, sha256_file
from src.data.investigate import classify_gap_hypothesis
from src.data.reference_compare import (
    PIP, PRICE_COLUMNS, assess_peak, histdata_files_for_window, hypothesis_offsets, join_at_offset,
    label_minutes, load_histdata_window, minute_returns, null_check, offset_scan, price_summary,
)

FXCM_COLUMNS = ["DateTime", "BidOpen", "BidHigh", "BidLow", "BidClose", "AskOpen", "AskHigh", "AskLow", "AskClose"]
FXCM_TS_PATTERN = r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}\.\d{3}"
FXCM_TS_FORMAT = "%m/%d/%Y %H:%M:%S.%f"
SIDES = ("bid", "ask")
SPREAD_ALERT_PIPS = 5.0
JUMP_ALERT_PIPS = 20.0

# Documented release times used as independent anchors (UTC)
EVENTS = [
    {"event": "FOMC minutes (Dec 10-11 meeting)", "utc": "2020-01-03 19:00",
     "basis": "Federal Reserve press release: 2:00 p.m. EST"},
    {"event": "ISM manufacturing (Dec)", "utc": "2020-01-03 15:00",
     "basis": "10:00 a.m. ET per a market preview (secondary source)"},
]


# ---------------------------------------------------------------------------
# Loading and schema
# ---------------------------------------------------------------------------
def read_fxcm_text(path: Path) -> pd.DataFrame:
    """Every field as text, exactly as stored."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(df.columns) != FXCM_COLUMNS:
        raise ValueError(f"unexpected columns {list(df.columns)}; expected {FXCM_COLUMNS}")
    return df


def read_fxcm_csv(path: Path) -> pd.DataFrame:
    """Strict parse. Timestamps stay naive labels; the documented UTC basis is not applied."""
    text = read_fxcm_text(path)
    ts_text = text["DateTime"].astype("string")
    valid = ts_text.str.fullmatch(FXCM_TS_PATTERN).fillna(False).astype(bool)
    if not valid.all():
        raise ValueError(f"{int((~valid).sum())} timestamp(s) not in 'MM/DD/YYYY HH:MM:SS.fff' form, "
                         f"first: {ts_text[~valid].iloc[0]!r}")
    out = pd.DataFrame({
        "source_row": np.arange(len(text)),
        "timestamp_text": ts_text.to_numpy(),
        "timestamp_label": pd.to_datetime(ts_text, format=FXCM_TS_FORMAT).to_numpy(),
    })
    for side in SIDES:
        for field in PRICE_COLUMNS:
            column = f"{side.capitalize()}{field.capitalize()}"
            out[f"{side}_{field}"] = pd.to_numeric(text[column], errors="raise").astype("float64")
    return out


def schema_report(text: pd.DataFrame) -> pd.DataFrame:
    """Per-column empties, numeric parse failures, and decimal places as written."""
    rows = []
    for column in text.columns:
        values = text[column]
        row = {"column": column, "stored_as": "text", "empty_values": int((values.str.strip() == "").sum())}
        if column != "DateTime":
            numeric = pd.to_numeric(values, errors="coerce")
            decimals = values.str.split(".").str[1].str.len().fillna(0).astype(int)
            row.update({"parsed_dtype": "float64", "non_numeric": int(numeric.isna().sum()),
                        "min": numeric.min(), "max": numeric.max(),
                        "max_decimals_written": int(decimals.max()),
                        "decimals_distribution": ",".join(f"{d}:{n}" for d, n in decimals.value_counts().sort_index().items())})
        else:
            row.update({"parsed_dtype": "datetime64 (naive label)",
                        "fraction_nonzero_ms": int((~values.str.endswith(".000")).sum())})
        rows.append(row)
    return pd.DataFrame(rows)


def date_order_evidence(ts_text: pd.Series) -> dict:
    """Is the date MM/DD/YYYY or DD/MM/YYYY? Only values above 12 can settle it."""
    first = ts_text.str[0:2].astype(int)
    second = ts_text.str[3:5].astype(int)
    if second.max() > 12 >= first.max():
        verdict = "MM/DD/YYYY (established: second field exceeds 12)"
    elif first.max() > 12 >= second.max():
        verdict = "DD/MM/YYYY (established: first field exceeds 12)"
    else:
        verdict = "ambiguous"
    return {"first_field_max": int(first.max()), "second_field_max": int(second.max()), "verdict": verdict}


def side_frame(df: pd.DataFrame, side: str, name: str) -> pd.DataFrame:
    """One price side in the column layout the HistData audit helpers expect."""
    return pd.DataFrame({"source_file": name, "source_row": df["source_row"], "timestamp": df["timestamp_label"],
                         **{f: df[f"{side}_{f}"] for f in PRICE_COLUMNS}, "volume": 0})


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def ordering_and_duplicates(df: pd.DataFrame) -> dict:
    ts = df["timestamp_label"]
    prev = ts.shift()
    return {"rows": len(df), "first_label": str(ts.iloc[0]), "last_label": str(ts.iloc[-1]),
            "min_label": str(ts.min()), "max_label": str(ts.max()),
            "monotonic_increasing": bool(ts.is_monotonic_increasing),
            "rows_not_after_previous": int((ts <= prev).sum()),
            "duplicate_timestamp_rows": int(ts.duplicated(keep=False).sum()),
            "duplicate_timestamps": int(ts[ts.duplicated(keep=False)].nunique()),
            "nonzero_seconds": int((ts.dt.second != 0).sum())}


def gap_table(df: pd.DataFrame, audit_cfg: dict) -> pd.DataFrame:
    """All gaps on the FXCM label clock, with hypothesis categories (none verified)."""
    gaps = detect_gaps(df["timestamp_label"], expected_minutes=audit_cfg["expected_bar_minutes"],
                       short_gap_max_minutes=audit_cfg["short_gap_max_minutes"],
                       weekend_max_hours=audit_cfg["weekend_max_hours"])
    long = gaps["category"] != "intraweek_short"
    gaps["hypothesis_category"] = "short_gap_unexplained"
    gaps["hypothesis_basis"] = ""
    for i in gaps.index[long]:
        cat, basis = classify_gap_hypothesis(gaps.at[i, "last_bar_before"], gaps.at[i, "first_bar_after"],
                                             gaps.at[i, "category"])
        gaps.at[i, "hypothesis_category"], gaps.at[i, "hypothesis_basis"] = cat, basis
    gaps["duration"] = gaps["duration"].astype(str)
    return gaps


def bid_ask_checks(df: pd.DataFrame) -> pd.DataFrame:
    """Ask should be >= bid for each field if the spread is never negative at any tick."""
    rows = []
    for field in PRICE_COLUMNS:
        spread = (df[f"ask_{field}"] - df[f"bid_{field}"]) / PIP
        rows.append({"field": field, "ask_below_bid": int((spread < 0).sum()), "ask_equals_bid": int((spread == 0).sum()),
                     "spread_min_pips": round(spread.min(), 2), "spread_median_pips": round(spread.median(), 2),
                     "spread_p99_pips": round(spread.quantile(0.99), 2), "spread_max_pips": round(spread.max(), 2)})
    return pd.DataFrame(rows)


def spread_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    spread = (df["ask_close"] - df["bid_close"]) / PIP
    hour = df["timestamp_label"].dt.hour.rename("label_hour")
    return spread.groupby(hour).agg(["count", "median", "max"]).round(2).reset_index()


def spread_anomalies(df: pd.DataFrame, alert_pips: float = SPREAD_ALERT_PIPS) -> pd.DataFrame:
    """Bars with any negative spread, or a close/open spread above alert_pips."""
    spreads = pd.DataFrame({f: (df[f"ask_{f}"] - df[f"bid_{f}"]) / PIP for f in PRICE_COLUMNS})
    flag = (spreads < 0).any(axis=1) | (spreads[["open", "close"]] > alert_pips).any(axis=1)
    out = df.loc[flag, ["source_row", "timestamp_text"]].copy()
    out["line_number"] = out.pop("source_row") + 2
    return out.join(spreads[flag].round(2).add_prefix("spread_pips_"))


def price_jumps(df: pd.DataFrame, alert_pips: float = JUMP_ALERT_PIPS) -> pd.DataFrame:
    """Consecutive bars whose bid close-to-open or close-to-close move exceeds alert_pips."""
    rows = []
    for i in range(1, len(df)):
        gap_open = abs(df["bid_open"].iat[i] - df["bid_close"].iat[i - 1]) / PIP
        move = abs(df["bid_close"].iat[i] - df["bid_close"].iat[i - 1]) / PIP
        if max(gap_open, move) > alert_pips:
            rows.append({"line_number": i + 2, "timestamp_text": df["timestamp_text"].iat[i],
                         "previous_timestamp_text": df["timestamp_text"].iat[i - 1],
                         "bid_open_vs_prev_close_pips": round(gap_open, 2), "bid_close_move_pips": round(move, 2)})
    return pd.DataFrame(rows, columns=["line_number", "timestamp_text", "previous_timestamp_text",
                                       "bid_open_vs_prev_close_pips", "bid_close_move_pips"])


def event_activity(df: pd.DataFrame, events: list[dict], window: int = 5,
                   alternatives=(-60, 0, 60)) -> pd.DataFrame:
    """Bid-return activity at each documented event label, and at +/- 1 h for comparison.

    If the labels are UTC, the strongest activity should be at offset 0.
    """
    returns = minute_returns(side_frame(df, "bid", "fxcm").rename(columns={"timestamp": "t"}), "t").abs()
    rows = []
    for e in events:
        at = int(label_minutes(pd.Series(pd.to_datetime([e["utc"]])))[0])
        day = returns[(returns.index >= at - at % 1440) & (returns.index < at - at % 1440 + 1440)]
        median = day.median()
        row = {**e, "day_median_abs_return_bp": round(median * 1e4, 3)}
        for shift in alternatives:
            near = returns[(returns.index >= at + shift) & (returns.index < at + shift + window)]
            peak = near.max() if len(near) else np.nan
            row[f"max_bp_at_{shift:+d}min"] = round(peak * 1e4, 2)
            row[f"ratio_to_median_at_{shift:+d}min"] = round(peak / median, 1) if median > 0 else np.nan
        strengths = {s: row[f"max_bp_at_{s:+d}min"] for s in alternatives}
        row["strongest_shift_min"] = max(strengths, key=lambda s: -np.inf if np.isnan(strengths[s]) else strengths[s])
        rows.append(row)
    return pd.DataFrame(rows)


def largest_differences(joined: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    both = joined[joined["present_in"] == "both"].copy()
    diff_cols = [f"{f}_diff_pips" for f in PRICE_COLUMNS]
    both["max_abs_diff_pips"] = both[diff_cols].abs().max(axis=1)
    cols = ["fxcm_timestamp_text", "histdata_label", "fxcm_line_number", "histdata_line_number", *diff_cols, "max_abs_diff_pips"]
    return both.nlargest(n, "max_abs_diff_pips")[cols]


# ---------------------------------------------------------------------------
# Overlap comparison with HistData
# ---------------------------------------------------------------------------
def compare_with_histdata(fxcm: pd.DataFrame, raw_dir: Path, pattern: str, max_offset: int = 720) -> dict:
    start, end = fxcm["timestamp_label"].min(), fxcm["timestamp_label"].max() + pd.Timedelta(minutes=1)
    window_start, window_end = start - pd.Timedelta(minutes=max_offset), end + pd.Timedelta(minutes=max_offset)
    paths = histdata_files_for_window(raw_dir, pattern, window_start, window_end)
    if not paths:
        return {"available": False, "reason": f"no HistData file covers {window_start} - {window_end}"}
    hist = load_histdata_window(paths, window_start, window_end)
    bid = side_frame(fxcm, "bid", "fxcm")
    scan = offset_scan(minute_returns(hist, "timestamp"), minute_returns(bid, "timestamp"), range(-max_offset, max_offset + 1))
    peak = assess_peak(scan)
    ref = pd.DataFrame({"source_row": fxcm["source_row"], "timestamp_text": fxcm["timestamp_text"],
                        "timestamp_label": fxcm["timestamp_label"], **{f: fxcm[f"bid_{f}"] for f in PRICE_COLUMNS}})

    def joined(offset: int) -> pd.DataFrame:
        j = join_at_offset(hist, ref, offset, ref_ts_column="timestamp_label").rename(
            columns={"reference_utc": "fxcm_timestamp_text", "reference_line_number": "fxcm_line_number"})
        j = j.rename(columns={f"{f}_ref": f"{f}_fxcm_bid" for f in PRICE_COLUMNS})
        j = j.rename(columns={f"{f}_hist": f"{f}_histdata_bid" for f in PRICE_COLUMNS})
        j["fxcm_label"] = pd.to_datetime(j["fxcm_timestamp_text"], format=FXCM_TS_FORMAT)
        in_span = j["fxcm_label"].notna() | j["histdata_label"].ne("")
        return j[in_span].sort_values(["fxcm_label", "histdata_label"], na_position="last").reset_index(drop=True)

    def summary(j: pd.DataFrame) -> pd.DataFrame:
        renamed = j.rename(columns={f"{f}_fxcm_bid": f"{f}_ref" for f in PRICE_COLUMNS})
        return price_summary(renamed)

    best = joined(peak["best_offset_minutes"])
    # Only HistData minutes that would fall inside the FXCM span at this offset are relevant
    lo, hi = label_minutes(pd.Series([start]))[0], label_minutes(pd.Series([end]))[0]
    hist_keys = label_minutes(pd.to_datetime(best["histdata_label"].replace("", None))) + peak["best_offset_minutes"]
    best = best[best["fxcm_label"].notna() | ((hist_keys >= lo) & (hist_keys < hi))]
    exact = joined(0)
    exact = exact[exact["fxcm_label"].notna()]
    return {
        "available": True, "histdata_files": [str(p) for p in paths], "scan": scan, "peak": peak,
        "peak_spearman": assess_peak(scan, "spearman"), "null": null_check(scan, peak["best_offset_minutes"]),
        "predictions": hypothesis_offsets(start.normalize()).assign(
            matches_best_offset=lambda p: p["predicted_offset_minutes"] == peak["best_offset_minutes"]),
        "best": best, "best_summary": summary(best), "best_presence": best["present_in"].value_counts().to_dict(),
        "largest_differences": largest_differences(best),
        "presence_by_day": best.assign(day=best["fxcm_label"].fillna(
            pd.to_datetime(best["histdata_label"].replace("", None)) + pd.Timedelta(minutes=peak["best_offset_minutes"])
        ).dt.date).groupby(["day", "present_in"], observed=True).size().unstack(fill_value=0).reset_index(),
        "exact": exact, "exact_summary": summary(exact), "exact_presence": exact["present_in"].value_counts().to_dict(),
    }


# ---------------------------------------------------------------------------
# Orchestration and report
# ---------------------------------------------------------------------------
def run_fxcm_audit(root: Path, config: dict, fxcm_path: Path) -> dict:
    data_cfg = config["data"]
    raw_dir = root / data_cfg["raw_dir"]
    originals = (discover_raw_files(raw_dir, data_cfg["raw_csv_glob"])
                 + sorted(raw_dir.glob(data_cfg["raw_csv_glob"].replace(".csv", ".txt")))
                 + [root / p for p in data_cfg["parquet_files"].values()])
    tracked = originals + [fxcm_path] + sorted((raw_dir / "dukascopy").glob("*.csv"))
    hashes_before = {str(p): sha256_file(p) for p in tracked}

    text = read_fxcm_text(fxcm_path)
    fxcm = read_fxcm_csv(fxcm_path)
    name = fxcm_path.name
    ohlc = pd.concat([validate_ohlc(side_frame(fxcm, s, name)).assign(side=s) for s in SIDES], ignore_index=True)
    dukascopy = sorted((raw_dir / "dukascopy").glob("*.csv"))
    fx_days = set(fxcm["timestamp_label"].dt.date.astype(str))
    duka_overlap = [p.name for p in dukascopy if any(day in p.name for day in fx_days)]

    results = {
        "fxcm_path": str(fxcm_path),
        "file": {"bytes": fxcm_path.stat().st_size, "gzip_magic": fxcm_path.read_bytes()[:2] == b"\x1f\x8b",
                 "data_rows": len(text), "trailing_newline": fxcm_path.read_bytes().endswith(b"\n")},
        "schema": schema_report(text),
        "date_order": date_order_evidence(text["DateTime"]),
        "ordering": ordering_and_duplicates(fxcm),
        "gaps": gap_table(fxcm, config["audit"]),
        "ohlc_violations": ohlc,
        "bid_ask": bid_ask_checks(fxcm),
        "spread_by_hour": spread_by_hour(fxcm),
        "spread_anomalies": spread_anomalies(fxcm),
        "price_jumps": price_jumps(fxcm),
        "events": event_activity(fxcm, EVENTS),
        "dukascopy_files": [p.name for p in dukascopy], "dukascopy_overlap": duka_overlap,
        "histdata": compare_with_histdata(fxcm, raw_dir, data_cfg["raw_csv_glob"]),
    }
    results["hashes_before"] = hashes_before
    results["hashes_after"] = {p: sha256_file(Path(p)) for p in hashes_before}
    return results


def render_summary(r: dict) -> str:
    unchanged = r["hashes_before"] == r["hashes_after"]
    o, h = r["ordering"], r["histdata"]
    gaps = r["gaps"]
    gap_counts = gaps.groupby("hypothesis_category")["missing_bars"].agg(["size", "sum"]).rename(
        columns={"size": "gaps", "sum": "missing_bars"}).reset_index()
    long_gaps = gaps[gaps["hypothesis_category"] != "short_gap_unexplained"]
    sections = [
        f"# FXCM M1 audit: `{r['fxcm_path']}` (read-only)",
        f"Generated (UTC): {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S}. No file was modified, shifted, "
        f"filled or converted. Tracked files unchanged during run: **{'YES' if unchanged else 'NO'}** "
        f"({len(r['hashes_before'])} files).",
        "## 1. File",
        f"`{json.dumps(r['file'])}`. Gzip-compressed: **{'yes' if r['file']['gzip_magic'] else 'no (plain CSV text)'}**. "
        "The file contains no instrument column; EURUSD is inferred from price levels and the HistData match below.",
        "## 2. Schema (all fields read as text first)",
        md_table(r["schema"]),
        f"Date order: `{json.dumps(r['date_order'])}`. Timestamps carry **no timezone designator**; FXCM's statement "
        "that they are UTC is documentation, not something the file establishes.",
        "## 3. Coverage, ordering, duplicates (label clock)",
        f"`{json.dumps(o)}`",
        "## 4. Gaps (hypothesis categories; none verified as market closures)",
        md_table(gap_counts),
        "Gaps longer than the short-gap threshold:",
        md_table(long_gaps) if len(long_gaps) else "none",
        "## 5. OHLC validity",
        f"Violations (bid and ask checked separately): {len(r['ohlc_violations'])}.",
        md_table(r["ohlc_violations"]) if len(r["ohlc_violations"]) else "",
        "## 6. Bid/ask and spreads",
        md_table(r["bid_ask"]),
        f"Bars with a negative spread or an open/close spread above {SPREAD_ALERT_PIPS} pips: {len(r['spread_anomalies'])} "
        "(spread_anomalies.csv).",
        md_table(r["spread_anomalies"].head(20)) if len(r["spread_anomalies"]) else "",
        "Median close spread by label hour:",
        md_table(r["spread_by_hour"]),
        f"Bid jumps above {JUMP_ALERT_PIPS} pips between consecutive bars: {len(r['price_jumps'])}.",
        md_table(r["price_jumps"]) if len(r["price_jumps"]) else "",
        "## 7. Event check on FXCM labels (independent of HistData)",
        md_table(r["events"]),
        "## 8. Dukascopy",
        f"Files: {r['dukascopy_files']}. Overlapping FXCM dates: {r['dukascopy_overlap'] or 'none'}; no comparison possible.",
        "## 9. HistData overlap comparison (no timestamps shifted)",
    ]
    if not h["available"]:
        sections.append(f"Not possible: {h['reason']}")
    else:
        p = h["peak"]
        sections += [
            "HistData files: " + ", ".join(f"`{f}`" for f in h["histdata_files"]),
            f"Exact labels (offset 0): presence {h['exact_presence']}.",
            md_table(h["exact_summary"]),
            "Offset scan on bid 1-minute log returns (FXCM label = HistData label + k):",
            md_table(pd.DataFrame([p, h["peak_spearman"]]).assign(variant=["pearson", "spearman"])),
            f"Null check: `{json.dumps(h['null'])}`",
            md_table(h["predictions"]),
            f"Price levels at the best offset (bid vs bid; supporting evidence only): presence {h['best_presence']}.",
            md_table(h["best_summary"]),
            "Presence by day (FXCM day after applying the best offset to HistData labels, for pairing only):",
            md_table(h["presence_by_day"]),
            "Largest bid differences at the best offset:",
            md_table(h["largest_differences"]),
        ]
    return "\n\n".join(s for s in sections if s != "") + "\n"


def write_report(r: dict, reports_dir: Path, stamp: str | None = None) -> Path:
    stamp = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(reports_dir) / f"fxcm_audit_{Path(r['fxcm_path']).stem}_{stamp}"
    run_dir.mkdir(parents=False, exist_ok=False)
    write_new(run_dir / "summary.md", render_summary(r))
    for name in ["schema", "gaps", "ohlc_violations", "bid_ask", "spread_by_hour", "spread_anomalies",
                 "price_jumps", "events"]:
        write_new(run_dir / f"{name}.csv", r[name].to_csv(index=False))
    h = r["histdata"]
    if h["available"]:
        for name in ["scan", "predictions", "best", "best_summary", "exact", "exact_summary",
                     "largest_differences", "presence_by_day"]:
            write_new(run_dir / f"histdata_{name}.csv", h[name].to_csv(index=False))
        write_new(run_dir / "histdata_alignment.json", json.dumps(
            {"pearson": h["peak"], "spearman": h["peak_spearman"], "null_check": h["null"]}, indent=2, default=str))
    write_new(run_dir / "file_and_ordering.json", json.dumps(
        {"file": r["file"], "date_order": r["date_order"], "ordering": r["ordering"],
         "dukascopy_files": r["dukascopy_files"], "dukascopy_overlap": r["dukascopy_overlap"]}, indent=2))
    write_new(run_dir / "source_hashes.json",
              json.dumps({"before": r["hashes_before"], "after": r["hashes_after"]}, indent=2))
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only FXCM M1 audit and HistData overlap comparison.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="config/research.yaml")
    parser.add_argument("--fxcm", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config = load_config(root / args.config)
    results = run_fxcm_audit(root, config, (root / args.fxcm).resolve())
    run_dir = write_report(results, root / config["reports"]["dir"])
    unchanged = results["hashes_before"] == results["hashes_after"]
    print(f"Report written to {run_dir}")
    print(f"Tracked files unchanged: {'YES' if unchanged else 'NO'}")
    if not unchanged:
        raise SystemExit("Source file hashes changed during the audit.")


if __name__ == "__main__":
    main()
