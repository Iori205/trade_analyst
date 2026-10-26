"""Build the versioned processed EURUSD M1 dataset under the approved timestamp policy C4.

Policy C4 (approved by the project owner 2026-10-26; evidence in reports/timezone_decision.md):
  HistData label before 2018-12-16  ->  America/New_York local time
  HistData label from 2018-12-16    ->  Europe/Zurich local time minus 6 hours

Every raw row is kept: nothing is filled, deduplicated or dropped. Quality issues
are flags only. Raw CSV/TXT files and the legacy Parquet files are only read.

Run:
    .venv/bin/python -m src.data.processed_m1
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.audit import PRICE_COLUMNS, load_config, load_raw
from src.data.fxcm_tz_compare import CANDIDATES, ERA_BOUNDARY, ERAS, TZ_HYPOTHESES, sunday_first_bars
from src.data.inventory import discover_raw_files, sha256_file
from src.data.investigate import dst_switch_dates

POLICY_ID = "C4"
POLICY_VERSION = "C4-v1"
POLICY_CANDIDATE = "C4_h2_then_h3_at_2018-12-16"
LOW_QUALITY_PERIOD = (pd.Timestamp("2023-02-01", tz="UTC"), pd.Timestamp("2023-08-01", tz="UTC"))  # Feb-Jul 2023
DEFAULT_OUT = Path("data/processed/eurusd_m1/v1")
OUTPUT_NAME = "eurusd_m1_utc.parquet"
SCRIPTS = ["src/data/processed_m1.py", "src/data/fxcm_tz_compare.py", "src/data/audit.py",
           "src/data/investigate.py", "src/data/inventory.py"]
FLAG_COLUMNS = ["gap_before", "duplicate_identical", "duplicate_conflict", "low_quality_period",
                "suspect_late_open", "dst_transition_hour", "utc_unresolved"]


def labels_to_utc(labels: pd.Series) -> tuple[pd.Series, pd.Series]:
    """UTC instants under C4, plus the source-clock rule used per row.

    Nonexistent or ambiguous local times (only possible on weekend nights, when the
    market is closed) become NaT and are flagged rather than guessed.
    """
    labels = pd.Series(labels).reset_index(drop=True)
    before = labels < ERA_BOUNDARY
    utc = pd.Series(pd.NaT, index=labels.index, dtype="datetime64[ns, UTC]")
    rule = pd.Series("", index=labels.index, dtype=object)
    for era, mask in ((ERAS[0], before), (ERAS[1], ~before)):
        hypothesis = CANDIDATES[POLICY_CANDIDATE][era]
        zone, shift = TZ_HYPOTHESES[hypothesis]
        local = labels[mask] - pd.Timedelta(minutes=shift)  # label = local + shift
        utc[mask] = local.dt.tz_localize(zone, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
        rule[mask] = f"{zone}{'' if shift == 0 else f'{shift // 60:+d}h'}"
    return utc, rule


def late_open_sundays(raw: pd.DataFrame) -> pd.DataFrame:
    """Sundays whose first bar's hour differs from the C4 prediction for the 17:00 New York open."""
    opens = sunday_first_bars(raw)
    if opens.empty:
        return opens.assign(c4_predicted_hm=pd.Series(dtype=object))
    predicted = np.where(opens["era"] == ERAS[0], opens["H2_america_new_york_predicted_hm"],
                         opens["H3_zurich_minus_6h_predicted_hm"])
    opens["c4_predicted_hm"] = predicted
    return opens[opens["first_bar_hm"].str[:2] != opens["c4_predicted_hm"].str[:2]].reset_index(drop=True)


def switch_sundays(years) -> set:
    return {d.date() for y in years for d in dst_switch_dates(int(y)).values()}


def build(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Processed frame (same rows as `raw`, sorted stably by UTC) and the late-open table."""
    raw = raw.reset_index(drop=True)
    utc, rule = labels_to_utc(raw["timestamp"])
    out = pd.DataFrame({
        "timestamp_utc": utc,
        # The raw field passed a strict \d{8} \d{6} check, so this reproduces the stored text exactly
        "source_timestamp_text": raw["timestamp"].dt.strftime("%Y%m%d %H%M%S"),
        "source_label": raw["timestamp"],
        "source_file": raw["source_file"].astype(str),
        "source_line": raw["source_row"].to_numpy() + 1,
        **{c: raw[c].to_numpy() for c in [*PRICE_COLUMNS, "volume"]},
        "source_era": np.where(raw["timestamp"] < ERA_BOUNDARY, ERAS[0], ERAS[1]),
        "source_clock_rule": rule.to_numpy(),
    })
    out["utc_offset_minutes"] = ((out["source_label"] - out["timestamp_utc"].dt.tz_localize(None))
                                 / pd.Timedelta(minutes=1)).astype("Int64")
    out["utc_unresolved"] = out["timestamp_utc"].isna()

    # Duplicates share a UTC minute; identical vs conflicting is judged on OHLC and volume
    key = out["timestamp_utc"]
    group_size = out.groupby(key, dropna=True)["source_line"].transform("size").fillna(1).astype(int)
    distinct = out.groupby(key, dropna=True)[[*PRICE_COLUMNS, "volume"]].transform("nunique").max(axis=1)
    dup = group_size > 1
    out["duplicate_group_size"] = group_size
    out["duplicate_identical"] = dup & (distinct == 1)
    out["duplicate_conflict"] = dup & (distinct > 1)

    # Missing minutes before each bar (on the UTC clock), computed over distinct minutes
    minutes = pd.Series(np.sort(key.dropna().unique()))
    gaps = (minutes.diff() / pd.Timedelta(minutes=1) - 1).fillna(0).astype(int)
    out["gap_before_minutes"] = key.map(pd.Series(gaps.to_numpy(), index=minutes)).astype("Int64")
    out["gap_before"] = out["gap_before_minutes"].fillna(0) > 0

    out["low_quality_period"] = (key >= LOW_QUALITY_PERIOD[0]) & (key < LOW_QUALITY_PERIOD[1])
    late = late_open_sundays(raw)
    label_dates = raw["timestamp"].dt.date
    out["suspect_late_open"] = label_dates.isin(set(pd.to_datetime(late["sunday"]).dt.date)).to_numpy()
    out["dst_transition_hour"] = (label_dates.isin(switch_sundays(raw["timestamp"].dt.year.unique()))
                                  & (raw["timestamp"].dt.dayofweek == 6)).to_numpy()
    for c in FLAG_COLUMNS:
        out[c] = out[c].fillna(False).astype(bool)

    order = np.lexsort((out["source_line"].to_numpy(), out["source_file"].to_numpy(),
                        out["timestamp_utc"].isna().to_numpy(),
                        out["timestamp_utc"].fillna(pd.Timestamp(0, tz="UTC")).dt.tz_localize(None)
                        .to_numpy().astype("int64")))
    return out.iloc[order].reset_index(drop=True), late


def git_commit(root: Path) -> dict:
    proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    if proc.returncode == 0:
        return {"git_commit": proc.stdout.strip(), "git_note": ""}
    return {"git_commit": None, "git_note": "project is not a git repository; script SHA-256 values recorded instead"}


def run(root: Path, config: dict, out_dir: Path = DEFAULT_OUT) -> dict:
    data_cfg = config["data"]
    out_dir = root / out_dir
    if out_dir.exists():
        raise FileExistsError(f"{out_dir} exists; versions are never overwritten")
    paths = discover_raw_files(root / data_cfg["raw_dir"], data_cfg["raw_csv_glob"])
    protected = paths + [root / p for p in data_cfg["parquet_files"].values()]
    before = {str(p.relative_to(root)): sha256_file(p) for p in protected}
    raw = load_raw(paths)
    rows_per_file = raw["source_file"].value_counts(sort=False).to_dict()
    processed, late = build(raw)
    if len(processed) != len(raw):
        raise AssertionError("row count changed")

    out_dir.mkdir(parents=True, exist_ok=False)
    data_path = out_dir / OUTPUT_NAME
    with open(data_path, "xb") as handle:  # "x": never overwrite
        processed.to_parquet(handle, index=False)
    with open(out_dir / "late_open_sundays.csv", "x", encoding="utf-8", newline="") as handle:
        late.to_csv(handle, index=False)
    after = {str(p.relative_to(root)): sha256_file(p) for p in protected}
    if before != after:
        raise AssertionError("a protected input changed during the build")

    flags = {c: int(processed[c].sum()) for c in FLAG_COLUMNS}
    manifest = {
        "dataset": "eurusd_m1", "version": out_dir.name,
        "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy": {"id": POLICY_ID, "version": POLICY_VERSION, "candidate": POLICY_CANDIDATE,
                   "era_boundary_label_date": str(ERA_BOUNDARY.date()),
                   "before_boundary": "America/New_York local time",
                   "from_boundary": "Europe/Zurich local time minus 6 hours",
                   "approved_by": "project owner, 2026-10-26 (in session)",
                   "evidence": "reports/timezone_decision.md",
                   "evidence_sha256": sha256_file(root / "reports/timezone_decision.md")},
        "handling": {"missing_minutes": "not filled; see gap_before_minutes",
                     "duplicates": "all copies kept; duplicate_identical / duplicate_conflict flags",
                     "low_quality_period": "UTC 2023-02-01 to 2023-07-31 flagged, not removed",
                     "suspect_late_open": f"whole Sunday session (label date) of {len(late)} weeks whose first bar "
                                          "is later than the C4-predicted 17:00 New York open",
                     "dst_transition_hour": "Sunday-session rows on US and EU DST switch Sundays (label date)",
                     "utc_unresolved": "nonexistent/ambiguous local labels left as NaT",
                     "sort": "stable by timestamp_utc, then source_file, source_line"},
        **git_commit(root),
        "scripts_sha256": {s: sha256_file(root / s) for s in SCRIPTS},
        "inputs": [{"path": str(p.relative_to(root)), "sha256": before[str(p.relative_to(root))],
                    "rows": int(rows_per_file.get(p.name, 0))} for p in paths],
        "legacy_parquet_untouched_sha256": {k: v for k, v in before.items() if k.endswith(".parquet")},
        "output": {"path": str(data_path.relative_to(root)), "sha256": sha256_file(data_path),
                   "rows": len(processed), "input_rows": len(raw),
                   "first_utc": str(processed["timestamp_utc"].min()), "last_utc": str(processed["timestamp_utc"].max()),
                   "columns": list(processed.columns)},
        "flag_counts": flags,
        "environment": {"python": platform.python_version(), "pandas": pd.__version__,
                        "pyarrow": __import__("pyarrow").__version__},
    }
    with open(out_dir / "manifest.json", "x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    with open(out_dir / "SHA256SUMS.txt", "x", encoding="utf-8") as handle:
        for name in (OUTPUT_NAME, "late_open_sundays.csv", "manifest.json"):
            handle.write(f"{sha256_file(out_dir / name)}  {name}\n")
    return {"manifest": manifest, "late": late, "out_dir": out_dir}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path("config/research.yaml"))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    r = run(Path.cwd(), load_config(args.config), args.out)
    m = r["manifest"]
    print(json.dumps({k: m[k] for k in ("output", "flag_counts", "git_commit", "git_note")}, indent=2))
    print(f"written: {r['out_dir']}")


if __name__ == "__main__":
    main()
