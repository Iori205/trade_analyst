"""Build versioned M15 and H1 bars from the processed C4 M1 dataset, one file per split.

Bars are on the UTC clock and labelled by their start time. Nothing is filled:
an interval with no M1 minute has no bar, and m1_count counts only real minutes.
Duplicates: of each identical group one copy is used; a minute with conflicting
copies uses its first copy (by source_file, source_line) and the bar keeps the
duplicate_conflict flag. The input M1 dataset is only read.

Reading the locked test split needs an explicit unlock, here --unlock-test.

Run:
    .venv/bin/python -m src.data.bars --unlock-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import subprocess
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from src.data.inventory import sha256_file
from src.data.splits import DEFAULT_SPLITS, Split, TestSetLockedError, guard_range, load_splits, read_m1_split

DEFAULT_INPUT = Path("data/processed/eurusd_m1/v1")
INPUT_NAME = "eurusd_m1_utc.parquet"
DEFAULT_OUT = Path("data/processed/eurusd_bars/v1")
TIMEFRAMES = {"M15": 15, "H1": 60}
BAR_FLAGS = ["gap_before", "duplicate_identical", "duplicate_conflict", "low_quality_period",
             "suspect_late_open", "dst_transition_hour"]
M1_COLUMNS = ["timestamp_utc", "source_file", "source_line", "open", "high", "low", "close",
              "utc_unresolved", *BAR_FLAGS]
SCRIPTS = ["src/data/bars.py", "src/data/splits.py"]


def bar_file(timeframe: str, split: str) -> str:
    return f"eurusd_{timeframe.lower()}_{split}.parquet"


def aggregate(m1: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Bars of `minutes` length from M1 rows (any order; duplicates allowed)."""
    m1 = m1[~m1["utc_unresolved"].astype(bool)]
    m1 = m1.sort_values(["timestamp_utc", "source_file", "source_line"], kind="mergesort")
    # Minute-level flags are OR-ed over all copies before one copy per minute is kept
    minute_flags = m1.groupby("timestamp_utc", sort=True)[BAR_FLAGS].any()
    one = m1.drop_duplicates("timestamp_utc", keep="first").set_index("timestamp_utc")
    one[BAR_FLAGS] = minute_flags
    start = one.index.floor(f"{minutes}min")
    g = one.groupby(start, sort=True)
    bars = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
        "m1_count": g.size().astype("int32"),
    })
    bars["expected_minutes"] = pd.Series(minutes, index=bars.index, dtype="int32")
    bars["any_gap"] = bars["m1_count"] < bars["expected_minutes"]
    for f in BAR_FLAGS:
        bars[f] = g[f].any()
    bars["any_flag"] = bars[BAR_FLAGS].any(axis=1)
    bars.index.name = "bar_start_utc"
    return bars.reset_index()


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    with open(path, "xb") as handle:  # "x": never overwrite
        df.to_parquet(handle, index=False, engine="pyarrow", compression="snappy")


def git_state(root: Path) -> dict:
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        return {"git_commit": None, "git_dirty": None}
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", *SCRIPTS, "config"],
                           capture_output=True, text=True)
    return {"git_commit": head.stdout.strip(), "git_dirty": bool(dirty.stdout.strip())}


def split_summary(bars: pd.DataFrame) -> dict:
    n = len(bars)
    pct = (lambda m: round(100 * float(m.sum()) / n, 3) if n else None)
    return {"bars": n, "m1_minutes": int(bars["m1_count"].sum()),
            "pct_m1_count_below_expected": pct(bars["any_gap"]), "pct_any_flag": pct(bars["any_flag"]),
            "bars_with_duplicate_conflict": int(bars["duplicate_conflict"].sum()),
            "first_bar_utc": str(bars["bar_start_utc"].min()) if n else None,
            "last_bar_utc": str(bars["bar_start_utc"].max()) if n else None}


def run(root: Path, input_dir: Path = DEFAULT_INPUT, out_dir: Path = DEFAULT_OUT,
        splits_path: Path = DEFAULT_SPLITS, unlock_test: bool = False) -> dict:
    root = Path(root)
    in_dir, out = root / input_dir, root / out_dir
    if out.exists():
        raise FileExistsError(f"{out} exists; versions are never overwritten")
    splits = load_splits(root / splits_path)
    guard_range(None, None, splits, unlock_test)  # building every split reads the locked one too
    source = in_dir / INPUT_NAME
    source_sha = sha256_file(source)
    recorded = dict(line.split()[::-1] for line in (in_dir / "SHA256SUMS.txt").read_text().splitlines() if line)
    if recorded.get(INPUT_NAME) != source_sha:
        raise AssertionError(f"{source} does not match its SHA256SUMS.txt")
    in_manifest = json.loads((in_dir / "manifest.json").read_text(encoding="utf-8"))

    frames, excluded = {}, {}
    for name in splits:
        frames[name], excluded[name] = read_m1_split(source, name, splits, M1_COLUMNS, unlock_test=unlock_test)
    used = sum(len(f) for f in frames.values())
    total = pq.ParquetFile(source).metadata.num_rows

    out.mkdir(parents=True, exist_ok=False)
    outputs, summary = {}, {}
    for tf, minutes in TIMEFRAMES.items():
        for name, m1 in frames.items():
            bars = aggregate(m1, minutes)
            path = out / bar_file(tf, name)
            write_parquet(bars, path)
            outputs[path.name] = {"timeframe": tf, "split": name, "rows": len(bars), "sha256": sha256_file(path)}
            summary[f"{tf}/{name}"] = split_summary(bars)
    if sha256_file(source) != source_sha:
        raise AssertionError("the input changed during the build")

    manifest = {
        "dataset": "eurusd_bars", "version": out.name,
        "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input": {"path": str(source.relative_to(root)), "sha256": source_sha,
                  "manifest_sha256": sha256_file(in_dir / "manifest.json"), "rows": total},
        "policy": {k: in_manifest["policy"].get(k) for k in ("id", "version", "candidate", "era_boundary_label_date")},
        "splits": {"config": str(Path(splits_path)), "config_sha256": sha256_file(root / splits_path),
                   **{s.name: {"start_utc": str(s.start), "end_utc_exclusive": str(s.end), "locked": s.locked,
                               "exclude_flags": list(s.exclude_flags), "m1_rows_used": len(frames[s.name]),
                               "m1_rows_excluded_by_flags": excluded[s.name]} for s in splits.values()},
                   "m1_rows_outside_all_splits": total - used - sum(excluded.values())},
        "test_unlocked": {"value": bool(unlock_test), "purpose": "bar construction only; no modelling"},
        "handling": {"label": "bar start time, UTC; bar = [start, start + timeframe)",
                     "missing_minutes": "not filled; no bar without an M1 minute; see m1_count, any_gap",
                     "duplicate_identical": "one copy used",
                     "duplicate_conflict": "first copy by source_file, source_line used; bar flagged",
                     "flags": "per-flag OR over the bar's M1 rows (all copies); any_flag = OR of " + ", ".join(BAR_FLAGS),
                     "utc_unresolved": "M1 rows with NaT UTC are not used"},
        **git_state(root),
        "scripts_sha256": {s: sha256_file(root / s) for s in SCRIPTS if (root / s).exists()},
        "outputs": outputs,
        "summary": summary,
        "environment": {"python": platform.python_version(), "pandas": pd.__version__,
                        "pyarrow": __import__("pyarrow").__version__},
    }
    with open(out / "manifest.json", "x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    with open(out / "SHA256SUMS.txt", "x", encoding="utf-8") as handle:
        for name in [*outputs, "manifest.json"]:
            handle.write(f"{sha256_file(out / name)}  {name}\n")
    return {"manifest": manifest, "out_dir": out}


def read_bars(bars_dir: Path, timeframe: str, split: str, splits: dict[str, Split],
              unlock_test: bool = False) -> pd.DataFrame:
    """One split's bars, behind the test guard."""
    s = splits[split]
    guard_range(s.start, s.end, splits, unlock_test)
    return pd.read_parquet(Path(bars_dir) / bar_file(timeframe, split))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    parser.add_argument("--unlock-test", action="store_true", help="explicitly allow reading the locked test split")
    args = parser.parse_args()
    try:
        r = run(Path.cwd(), args.input, args.out, args.splits, unlock_test=args.unlock_test)
    except TestSetLockedError as exc:
        parser.error(str(exc))
    m = r["manifest"]
    print(json.dumps({k: m[k] for k in ("outputs", "summary", "git_commit", "git_dirty")}, indent=2))
    print(f"written: {r['out_dir']}")


if __name__ == "__main__":
    main()
