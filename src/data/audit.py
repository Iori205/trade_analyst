"""Read-only data-quality audit of raw EURUSD HistData M1 files.

Principles:
* Source files are only read. Their SHA-256 hashes are taken before and after
  the audit and must be identical.
* Timestamps are parsed strictly and kept naive, on the source clock. The
  source timezone is unverified, so nothing here converts or localises them.
* Nothing is repaired or dropped. Duplicates, ordering problems, invalid
  OHLC rows and gaps are reported, not fixed. Any cleaning is a future step.
* Each run writes to a new directory under reports/ and never overwrites.

Run:
    .venv/bin/python -m src.data.audit
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.data.inventory import (
    build_inventory,
    discover_raw_files,
    nominal_period_bounds,
    parse_gap_report,
    parse_period,
    sha256_file,
)

RAW_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
PRICE_COLUMNS = ["open", "high", "low", "close"]
TIMESTAMP_FORMAT = "%Y%m%d %H%M%S"
TIMESTAMP_PATTERN = r"\d{8} \d{6}"
RESAMPLE_RULES = {"15m": "15min", "1h": "1h", "4h": "4h"}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def parse_timestamps(values) -> pd.Series:
    """Parse 'YYYYMMDD HHMMSS' strings strictly into naive datetimes.

    Raises on any value that doesn't match the format exactly. No timezone
    is attached, because the source timezone is unverified.
    """
    text = pd.Series(values, dtype="string")
    # pandas' format parsing alone is lenient (e.g. accepts "20240102 1700",
    # turns "" into NaT), so the exact shape is checked first.
    valid = text.str.fullmatch(TIMESTAMP_PATTERN).fillna(False).astype(bool)
    if not valid.all():
        bad = text[~valid]
        raise ValueError(f"{len(bad)} timestamp(s) not in 'YYYYMMDD HHMMSS' form, first: {bad.iloc[0]!r}")
    return pd.to_datetime(text, format=TIMESTAMP_FORMAT, errors="raise")


def read_raw_csv(path: Path) -> pd.DataFrame:
    """Read one HistData M1 CSV exactly as stored: no sorting, no dedup."""
    df = pd.read_csv(
        path,
        sep=";",
        header=None,
        names=RAW_COLUMNS,
        dtype={"timestamp": str, **{c: "float64" for c in PRICE_COLUMNS}, "volume": "int64"},
        na_filter=False,  # an empty field is a format error, not a NaN
    )
    df["timestamp"] = parse_timestamps(df["timestamp"]).to_numpy()
    df.insert(0, "source_file", Path(path).name)
    df.insert(1, "source_row", np.arange(len(df)))
    return df


def load_raw(paths: list[Path]) -> pd.DataFrame:
    """All rows of all files, concatenated in file order."""
    raw = pd.concat([read_raw_csv(p) for p in paths], ignore_index=True)
    raw["source_file"] = raw["source_file"].astype("category")
    return raw


# ---------------------------------------------------------------------------
# Record-level checks
# ---------------------------------------------------------------------------
def per_file_checks(raw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, part in raw.groupby("source_file", observed=True, sort=False):
        start, end = nominal_period_bounds(parse_period(name)[0])
        ts = part["timestamp"]
        rows.append({
            "source_file": name,
            "rows": len(part),
            "first_timestamp": ts.iloc[0],
            "last_timestamp": ts.iloc[-1],
            "min_timestamp": ts.min(),
            "max_timestamp": ts.max(),
            "rows_outside_named_period": int(((ts < start) | (ts >= end)).sum()),
            "monotonic_increasing": bool(ts.is_monotonic_increasing),
            "duplicate_timestamp_rows": int(ts.duplicated().sum()),
            "nonzero_volume_rows": int((part["volume"] != 0).sum()),
            "nonzero_second_rows": int((ts.dt.second != 0).sum()),
        })
    return pd.DataFrame(rows)


def find_file_overlaps(file_checks: pd.DataFrame) -> pd.DataFrame:
    """Pairs of consecutive files (by first timestamp) whose time ranges overlap."""
    ordered = file_checks.sort_values("min_timestamp").reset_index(drop=True)
    nxt = ordered.shift(-1)
    overlap = nxt["min_timestamp"] <= ordered["max_timestamp"]
    return pd.DataFrame({
        "file": ordered.loc[overlap, "source_file"],
        "file_max": ordered.loc[overlap, "max_timestamp"],
        "next_file": nxt.loc[overlap, "source_file"],
        "next_file_min": nxt.loc[overlap, "min_timestamp"],
    })


def find_out_of_order(raw: pd.DataFrame) -> pd.DataFrame:
    """Rows whose timestamp is not later than the previous row of the same file."""
    previous = raw.groupby("source_file", observed=True)["timestamp"].shift()
    mask = raw["timestamp"] <= previous
    out = raw.loc[mask, ["source_file", "source_row", "timestamp"]].copy()
    out["previous_timestamp"] = previous[mask]
    return out


def find_duplicates(raw: pd.DataFrame) -> pd.DataFrame:
    """Every row whose timestamp occurs more than once (across all files).

    status is 'identical' when all rows sharing a timestamp have the same
    OHLC and volume, otherwise 'conflicting'.
    """
    value_columns = PRICE_COLUMNS + ["volume"]
    dup = raw[raw.duplicated("timestamp", keep=False)].copy()
    if dup.empty:
        return dup.assign(group_size=pd.Series(dtype=int), distinct_values=pd.Series(dtype=int),
                          files=pd.Series(dtype=int), status=pd.Series(dtype=str))
    by_ts = dup.groupby("timestamp")
    variants = dup.drop_duplicates(["timestamp"] + value_columns).groupby("timestamp").size()
    dup["group_size"] = by_ts["timestamp"].transform("size")
    dup["distinct_values"] = dup["timestamp"].map(variants)
    dup["files"] = by_ts["source_file"].transform("nunique")
    dup["status"] = np.where(dup["distinct_values"] == 1, "identical", "conflicting")
    return dup.sort_values(["timestamp", "source_file", "source_row"])


def summarize_duplicates(dup: pd.DataFrame) -> pd.DataFrame:
    """One line per (file, calendar day, status) cluster of duplicate timestamps."""
    if dup.empty:
        return pd.DataFrame(columns=["source_file", "date", "weekday", "status", "timestamps",
                                     "rows", "first", "last", "files"])
    d = dup.assign(date=dup["timestamp"].dt.date)
    summary = (
        d.groupby(["source_file", "date", "status"], observed=True)
        .agg(timestamps=("timestamp", "nunique"), rows=("timestamp", "size"),
             first=("timestamp", "min"), last=("timestamp", "max"), files=("files", "max"))
        .reset_index()
    )
    summary.insert(2, "weekday", pd.to_datetime(summary["date"]).dt.day_name())
    return summary


def validate_ohlc(raw: pd.DataFrame) -> pd.DataFrame:
    """Rows failing any price check, with one boolean column per check."""
    prices = raw[PRICE_COLUMNS]
    body_high = raw[["open", "close"]].max(axis=1)
    body_low = raw[["open", "close"]].min(axis=1)
    checks = pd.DataFrame({
        "missing_price": prices.isna().any(axis=1),
        "non_positive_price": (prices <= 0).any(axis=1),
        "high_below_low": raw["high"] < raw["low"],
        "high_below_open_or_close": raw["high"] < body_high,
        "low_above_open_or_close": raw["low"] > body_low,
    })
    bad = checks.any(axis=1)
    columns = ["source_file", "source_row", "timestamp"] + PRICE_COLUMNS
    return raw.loc[bad, columns].join(checks[bad])


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------
def detect_gaps(
    timestamps,
    expected_minutes: int = 1,
    short_gap_max_minutes: int = 30,
    weekend_max_hours: float = 56,
    holiday_month_days: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Intervals between consecutive distinct timestamps longer than one bar.

    Categories:
      weekend            starts Fri/Sat, ends Sun/Mon, lasts <= weekend_max_hours
      holiday_candidate  longer than a short gap and touches a holiday date
      intraweek_short    <= short_gap_max_minutes missing bars
      intraweek_long     everything else; worth a closer look
    Weekday rules use the source clock, whose timezone is unverified.
    """
    step = pd.Timedelta(minutes=expected_minutes)
    ts = pd.Series(np.sort(pd.unique(pd.Series(timestamps))))
    delta = ts.diff()
    is_gap = delta > step
    gaps = pd.DataFrame({
        "last_bar_before": ts.shift()[is_gap].to_numpy(),
        "first_bar_after": ts[is_gap].to_numpy(),
        "duration": delta[is_gap].to_numpy(),
    })
    gaps["missing_bars"] = (gaps["duration"] // step - 1).astype("int64")

    start, end = gaps["last_bar_before"], gaps["first_bar_after"]
    weekend = (
        start.dt.weekday.isin([4, 5]) & end.dt.weekday.isin([6, 0])
        & (gaps["duration"] <= pd.Timedelta(hours=weekend_max_hours))
    )
    short = gaps["missing_bars"] <= short_gap_max_minutes
    category = np.where(weekend, "weekend", np.where(short, "intraweek_short", "intraweek_long")).astype(object)

    holidays = set(holiday_month_days)
    if holidays:
        for i in np.flatnonzero(~weekend.to_numpy() & ~short.to_numpy()):
            days = pd.date_range(start.iloc[i].normalize(), end.iloc[i].normalize(), freq="D")
            if any(day.strftime("%m-%d") in holidays for day in days):
                category[i] = "holiday_candidate"
    gaps["category"] = category
    return gaps


def summarize_gaps(gaps: pd.DataFrame) -> pd.DataFrame:
    """Gap count and missing bars per year and category."""
    year = gaps["first_bar_after"].dt.year.rename("year")
    counts = gaps.groupby([year, "category"]).size().unstack(fill_value=0).add_prefix("n_")
    missing = gaps.groupby([year, "category"])["missing_bars"].sum().unstack(fill_value=0).add_prefix("missing_")
    return counts.join(missing).reset_index()


def monthly_intraweek_missing(gaps: pd.DataFrame) -> pd.DataFrame:
    """Missing bars inside the trading week (short + long gaps) by month."""
    intraweek = gaps[gaps["category"].isin(["intraweek_short", "intraweek_long"])]
    month = intraweek["first_bar_after"].dt.to_period("M").rename("month")
    return (intraweek.groupby([month, "category"])["missing_bars"].sum()
            .unstack(fill_value=0).reset_index())


def bars_per_month(raw: pd.DataFrame) -> pd.Series:
    unique_ts = pd.Series(raw["timestamp"].unique())
    return unique_ts.dt.to_period("M").value_counts().sort_index()


# ---------------------------------------------------------------------------
# Timezone evidence (observations only; no conversion)
# ---------------------------------------------------------------------------
def weekly_sessions(gaps: pd.DataFrame) -> pd.DataFrame:
    """Last bar before and first bar after every weekend gap, on the source clock."""
    weekend = gaps[gaps["category"] == "weekend"]
    return pd.DataFrame({
        "week_close": weekend["last_bar_before"].to_numpy(),
        "week_open": weekend["first_bar_after"].to_numpy(),
        "close_time": weekend["last_bar_before"].dt.strftime("%a %H:%M").to_numpy(),
        "open_time": weekend["first_bar_after"].dt.strftime("%a %H:%M").to_numpy(),
        "open_month": weekend["first_bar_after"].dt.month.to_numpy(),
    })


def session_time_table(sessions: pd.DataFrame, column: str) -> pd.DataFrame:
    """Counts of weekly open (or close) hour by calendar month."""
    hour = pd.to_datetime(sessions["week_open" if column == "open" else "week_close"]).dt.hour
    return pd.crosstab(sessions["open_month"].rename("month"), hour.rename(f"{column}_hour"))


# ---------------------------------------------------------------------------
# Parquet comparison
# ---------------------------------------------------------------------------
def describe_parquet(path: Path) -> dict:
    df = pd.read_parquet(path)
    index = df.index
    return {
        "path": str(path),
        "rows": len(df),
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "index_name": index.name,
        "index_dtype": str(index.dtype),
        "index_tz": str(getattr(index, "tz", None)),
        "first": str(index.min()),
        "last": str(index.max()),
        "duplicate_index": int(index.duplicated().sum()),
        "monotonic_increasing": bool(index.is_monotonic_increasing),
    }


def raw_reference(raw: pd.DataFrame) -> pd.DataFrame:
    """Comparison reference only, NOT a cleaning decision.

    Raw rows sorted stably by timestamp, keeping the first occurrence per
    timestamp in file order. Used to test whether the existing Parquet files
    could have been derived from the raw files this way.
    """
    ordered = raw.sort_values("timestamp", kind="mergesort")
    return ordered.drop_duplicates("timestamp", keep="first").set_index("timestamp")[PRICE_COLUMNS]


def resample_reference(reference: pd.DataFrame, rule: str) -> pd.DataFrame:
    """OHLC aggregation on the naive source clock, bins labelled by their left edge."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return reference.resample(rule, label="left", closed="left").agg(agg).dropna(how="all")


def compare_frames(expected: pd.DataFrame, actual: pd.DataFrame, sample: int = 10) -> dict:
    """Index and exact value comparison of two OHLC frames."""
    common = expected.index.intersection(actual.index)
    diff = (expected.loc[common, PRICE_COLUMNS] - actual.loc[common, PRICE_COLUMNS]).abs()
    mismatched = diff.index[(diff > 0).any(axis=1)]
    return {
        "rows_expected": len(expected),
        "rows_actual": len(actual),
        "common_index": len(common),
        "only_in_expected": len(expected.index.difference(actual.index)),
        "only_in_actual": len(actual.index.difference(expected.index)),
        "value_mismatch_rows": len(mismatched),
        "max_abs_diff": float(diff.to_numpy().max()) if len(common) else None,
        "sample_mismatch_timestamps": [str(t) for t in mismatched[:sample]],
    }


def conflicting_duplicate_choice(dup: pd.DataFrame, parquet_1m: pd.DataFrame) -> pd.DataFrame:
    """For each conflicting duplicate timestamp, which raw variant the Parquet holds."""
    conflicts = dup[dup["status"] == "conflicting"]
    rows = []
    for ts, group in conflicts.groupby("timestamp"):
        held = parquet_1m.loc[ts, PRICE_COLUMNS].to_numpy() if ts in parquet_1m.index else None
        match = "absent"
        if held is not None:
            match = "none"
            for order, (_, row) in enumerate(group.iterrows()):
                if np.array_equal(row[PRICE_COLUMNS].to_numpy(dtype=float), held):
                    match = f"occurrence_{order + 1}_of_{len(group)} (row {row['source_row']})"
                    break
        rows.append({"timestamp": ts, "variants": len(group), "parquet_matches": match})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Orchestration and reporting
# ---------------------------------------------------------------------------
def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def run_audit(root: Path, config: dict) -> dict:
    data_cfg, audit_cfg = config["data"], config["audit"]
    raw_dir = root / data_cfg["raw_dir"]
    csv_paths = discover_raw_files(raw_dir, data_cfg["raw_csv_glob"])
    txt_paths = sorted(raw_dir.glob(data_cfg["raw_csv_glob"].replace(".csv", ".txt")))
    parquet_paths = {k: root / v for k, v in data_cfg["parquet_files"].items()}
    source_paths = csv_paths + txt_paths + list(parquet_paths.values())
    hashes_before = {str(p): sha256_file(p) for p in source_paths}

    inventory = build_inventory(raw_dir, data_cfg["raw_csv_glob"])
    raw = load_raw(csv_paths)
    file_checks = per_file_checks(raw)
    dup = find_duplicates(raw)
    gaps = detect_gaps(
        raw["timestamp"],
        expected_minutes=audit_cfg["expected_bar_minutes"],
        short_gap_max_minutes=audit_cfg["short_gap_max_minutes"],
        weekend_max_hours=audit_cfg["weekend_max_hours"],
        holiday_month_days=tuple(audit_cfg["holiday_month_days"]),
    )
    sessions = weekly_sessions(gaps)

    gap_reports = []
    for txt in txt_paths:
        parsed = parse_gap_report(txt)
        g = parsed["gaps"]
        gap_reports.append({
            "file": txt.name,
            "header_ok": parsed["header_ok"],
            "file_ref_matches_csv": parsed["file_ref"] == txt.with_suffix(".csv").name,
            "reported_gaps": len(g),
            "reported_gap_seconds_total": int(g["seconds"].sum()),
            "largest_gap_seconds": int(g["seconds"].max()) if len(g) else 0,
            "largest_gap_start": str(g.loc[g["seconds"].idxmax(), "start"]) if len(g) else "",
            "max_tick_interval_ms": parsed["max_tick_interval_ms"],
            "unparsed_lines": len(parsed["unparsed_lines"]),
        })

    reference = raw_reference(raw)
    parquet_info, parquet_compare = {}, {}
    parquet_1m = None
    for key, path in parquet_paths.items():
        parquet_info[key] = describe_parquet(path)
        frame = pd.read_parquet(path)
        expected = reference if key == "1m" else resample_reference(reference, RESAMPLE_RULES[key])
        parquet_compare[key] = compare_frames(expected, frame)
        if key == "1m":
            parquet_1m = frame
    conflict_choice = conflicting_duplicate_choice(dup, parquet_1m)

    hashes_after = {str(p): sha256_file(p) for p in source_paths}
    return {
        "inventory": inventory,
        "file_checks": file_checks,
        "file_overlaps": find_file_overlaps(file_checks),
        "out_of_order": find_out_of_order(raw),
        "duplicates": dup,
        "duplicate_summary": summarize_duplicates(dup),
        "ohlc_violations": validate_ohlc(raw),
        "gaps": gaps,
        "gap_summary": summarize_gaps(gaps),
        "monthly_intraweek_missing": monthly_intraweek_missing(gaps),
        "bars_per_month": bars_per_month(raw),
        "weekly_sessions": sessions,
        "open_hour_by_month": session_time_table(sessions, "open"),
        "close_hour_by_month": session_time_table(sessions, "close"),
        "gap_reports": pd.DataFrame(gap_reports),
        "parquet_info": parquet_info,
        "parquet_compare": parquet_compare,
        "conflict_choice": conflict_choice,
        "raw_rows": len(raw),
        "unique_timestamps": int(raw["timestamp"].nunique()),
        "zero_volume_rows": int((raw["volume"] == 0).sum()),
        "hashes_before": hashes_before,
        "hashes_after": hashes_after,
        "config": config,
    }


def md_table(df: pd.DataFrame) -> str:
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    rule = "|" + "---|" * len(df.columns)
    body = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, rule, *body])


def render_summary(r: dict) -> str:
    top_n = r["config"]["audit"]["report_top_n"]
    tz = r["config"]["timezone"]
    unchanged = r["hashes_before"] == r["hashes_after"]
    gaps = r["gaps"]
    long_gaps = gaps[gaps["category"].isin(["intraweek_long", "holiday_candidate"])]
    long_gaps = long_gaps.sort_values("missing_bars", ascending=False).head(top_n)
    inv = r["inventory"][["period", "rows", "malformed_rows", "price_decimals", "csv_bytes",
                          "txt_bytes", "first_timestamp", "last_timestamp"]]
    ohlc = r["ohlc_violations"]
    check_columns = [c for c in ohlc.columns if c.startswith(("missing", "non_", "high_", "low_"))]

    sections = [
        "# EURUSD M1 raw data audit",
        f"Generated (UTC): {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S}",
        "All timestamps below are **naive source-clock values**. Source timezone: "
        f"**{tz['source_timezone']}** (vendor documentation: {tz['documented_by_vendor']}). "
        "No record was modified, dropped or converted.",
        f"Source files hashed before and after the audit: {len(r['hashes_before'])}; "
        f"unchanged: **{'YES' if unchanged else 'NO'}**",
        "## 1. Inventory", md_table(inv),
        f"Raw rows: {r['raw_rows']:,}. Distinct timestamps: {r['unique_timestamps']:,}. "
        f"Rows with volume == 0: {r['zero_volume_rows']:,} of {r['raw_rows']:,}.",
        "## 2. Per-file checks", md_table(r["file_checks"]),
        "File range overlaps:", md_table(r["file_overlaps"]) if len(r["file_overlaps"]) else "none",
        "## 3. Ordering", f"Rows not later than the previous row in the same file: {len(r['out_of_order'])}",
        md_table(r["out_of_order"].head(top_n)) if len(r["out_of_order"]) else "",
        "## 4. Duplicate timestamps",
        f"Rows involved: {len(r['duplicates'])}. Timestamps: {r['duplicates']['timestamp'].nunique()}. "
        f"Conflicting timestamps: {r['duplicates'].loc[r['duplicates']['status'] == 'conflicting', 'timestamp'].nunique()}.",
        md_table(r["duplicate_summary"]) if len(r["duplicate_summary"]) else "none",
        "## 5. OHLC validity",
        f"Rows failing at least one check: {len(ohlc)}",
        md_table(pd.DataFrame({"check": check_columns, "rows": [int(ohlc[c].sum()) for c in check_columns]})),
        "## 6. Gaps (source clock)",
        "Weekend = Fri/Sat to Sun/Mon within "
        f"{r['config']['audit']['weekend_max_hours']}h; short = up to "
        f"{r['config']['audit']['short_gap_max_minutes']} missing bars.",
        md_table(r["gap_summary"]),
        f"Largest non-weekend, non-short gaps (top {top_n}):",
        md_table(long_gaps.assign(duration=long_gaps["duration"].astype(str))),
        "Intraweek missing bars by month:", md_table(r["monthly_intraweek_missing"]),
        "Distinct bars per month:",
        md_table(r["bars_per_month"].rename("bars").rename_axis("month").reset_index()),
        "## 7. Timezone evidence (observations, no conclusion drawn by the code)",
        "If the source clock were a fixed UTC offset while the market opens and closes on New York "
        "local time, weekly open/close hours would shift by one hour between US standard and "
        "daylight time. If they don't shift, the clock follows a DST-observing zone, or the market "
        "convention differs.",
        "Weekly open hour by month:", md_table(r["open_hour_by_month"].reset_index()),
        "Weekly close hour by month:", md_table(r["close_hour_by_month"].reset_index()),
        "## 8. HistData TXT status reports (tick-level gaps, not bar gaps)",
        md_table(r["gap_reports"]),
        "## 9. Existing Parquet files (unverified derived data)",
        "Reference = raw rows, stable-sorted, first occurrence per timestamp kept; higher "
        "timeframes = left-labelled, left-closed bins on the naive source clock. This tests "
        "how the Parquet files may have been built and is not a cleaning decision.",
    ]
    for key, info in r["parquet_info"].items():
        sections.append(f"**{key}** schema: `{json.dumps(info)}`")
        sections.append(f"**{key}** vs raw reference: `{json.dumps(r['parquet_compare'][key])}`")
    sections += [
        "Conflicting duplicate timestamps: which raw occurrence the 1m Parquet holds:",
        md_table(r["conflict_choice"]) if len(r["conflict_choice"]) else "none",
        "## 10. Source file hashes",
        md_table(pd.DataFrame({"path": list(r["hashes_before"]), "sha256": list(r["hashes_before"].values()),
                               "unchanged": [r["hashes_before"][p] == r["hashes_after"].get(p)
                                             for p in r["hashes_before"]]})),
    ]
    return "\n\n".join(s for s in sections if s != "") + "\n"


def write_new(path: Path, text: str) -> None:
    with open(path, "x", encoding="utf-8") as handle:  # "x" refuses to overwrite
        handle.write(text)


def write_report(results: dict, reports_dir: Path, stamp: str | None = None) -> Path:
    stamp = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(reports_dir) / f"data_audit_{stamp}"
    run_dir.mkdir(parents=False, exist_ok=False)
    write_new(run_dir / "summary.md", render_summary(results))
    tables = ["inventory", "file_checks", "out_of_order", "duplicates", "duplicate_summary",
              "ohlc_violations", "gaps", "gap_summary", "monthly_intraweek_missing",
              "weekly_sessions", "gap_reports", "conflict_choice"]
    for name in tables:
        write_new(run_dir / f"{name}.csv", results[name].to_csv(index=False))
    write_new(run_dir / "parquet_comparison.json", json.dumps(
        {"schemas": results["parquet_info"], "comparison": results["parquet_compare"]}, indent=2))
    write_new(run_dir / "source_hashes.json", json.dumps(
        {"before": results["hashes_before"], "after": results["hashes_after"]}, indent=2))
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only audit of raw EURUSD HistData M1 files.")
    parser.add_argument("--root", default=".", help="project root")
    parser.add_argument("--config", default="config/research.yaml")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config = load_config(root / args.config)
    results = run_audit(root, config)
    run_dir = write_report(results, root / config["reports"]["dir"])
    unchanged = results["hashes_before"] == results["hashes_after"]
    print(f"Report written to {run_dir}")
    print(f"Source files unchanged: {'YES' if unchanged else 'NO'}")
    if not unchanged:
        raise SystemExit("Source file hashes changed during the audit.")


if __name__ == "__main__":
    main()
