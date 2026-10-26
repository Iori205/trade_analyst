"""Inventory of raw HistData EURUSD M1 files.

Everything here is read-only: files are opened for reading and never
written, moved or renamed.

Run:
    .venv/bin/python -m src.data.inventory
"""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

CSV_NAME = re.compile(r"^DAT_ASCII_EURUSD_M1_(?P<period>\d{4}|\d{6})\.csv$")

# One bar: "YYYYMMDD HHMMSS;open;high;low;close;volume"
BAR_LINE = re.compile(
    r"^\d{8} \d{6};\d+\.(\d+);\d+\.(\d+);\d+\.(\d+);\d+\.(\d+);-?\d+$"
)

# HistData status-report lines (the accompanying .txt file)
GAP_LINE = re.compile(
    r"^Gap of (?P<seconds>\d+)s found between (?P<start>\d{14}) and (?P<end>\d{14})\.$"
)
MAX_TICK_LINE = re.compile(r"^Maximum tick interval found: (?P<ms>\d+) miliseconds\.$")
FILE_LINE = re.compile(r"^File: (?P<name>\S+) Status Report$")
HEADER_LINE = "HistData.com (c) 2012"


@dataclass(frozen=True)
class RawFile:
    period: str             # "2015" (yearly file) or "202601" (monthly file)
    granularity: str        # "year" | "month"
    csv_path: str
    txt_path: str | None
    csv_bytes: int
    txt_bytes: int | None
    rows: int
    malformed_rows: int     # lines not matching BAR_LINE
    price_decimals: str     # distinct decimal-place counts seen in prices
    first_timestamp: str    # raw text from the file, not converted
    last_timestamp: str
    sha256: str


def parse_period(file_name: str) -> tuple[str, str] | None:
    """Return (period, granularity) for a raw CSV name, or None if it doesn't match."""
    match = CSV_NAME.match(file_name)
    if not match:
        return None
    period = match["period"]
    return period, "year" if len(period) == 4 else "month"


def nominal_period_bounds(period: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """[start, end) of the calendar period a file name claims to cover (naive)."""
    if len(period) == 4:
        start = pd.Timestamp(year=int(period), month=1, day=1)
        return start, start + pd.DateOffset(years=1)
    start = pd.Timestamp(year=int(period[:4]), month=int(period[4:]), day=1)
    return start, start + pd.DateOffset(months=1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_raw_files(data_dir: Path, pattern: str = "**/DAT_ASCII_EURUSD_M1_*.csv") -> list[Path]:
    """Raw CSVs under data_dir, sorted by the period in their name."""
    paths = [p for p in Path(data_dir).glob(pattern) if parse_period(p.name)]
    return sorted(paths, key=lambda p: parse_period(p.name)[0].ljust(6, "0"))


def describe_raw_file(csv_path: Path) -> RawFile:
    csv_path = Path(csv_path)
    period, granularity = parse_period(csv_path.name)
    lines = csv_path.read_text(encoding="ascii").splitlines()
    lines = [line for line in lines if line.strip()]

    malformed = 0
    decimals: set[int] = set()
    for line in lines:
        match = BAR_LINE.match(line)
        if match is None:
            malformed += 1
        else:
            decimals.update(len(group) for group in match.groups())

    txt_path = csv_path.with_suffix(".txt")
    has_txt = txt_path.exists()
    return RawFile(
        period=period,
        granularity=granularity,
        csv_path=str(csv_path),
        txt_path=str(txt_path) if has_txt else None,
        csv_bytes=csv_path.stat().st_size,
        txt_bytes=txt_path.stat().st_size if has_txt else None,
        rows=len(lines),
        malformed_rows=malformed,
        price_decimals=",".join(str(d) for d in sorted(decimals)),
        first_timestamp=lines[0].split(";")[0] if lines else "",
        last_timestamp=lines[-1].split(";")[0] if lines else "",
        sha256=sha256_file(csv_path),
    )


def parse_gap_report(txt_path: Path) -> dict:
    """Parse a HistData .txt status report into structured data.

    These reports describe gaps between *ticks* (in seconds) in HistData's
    source feed, so they are related to, but not the same as, missing M1 bars.
    """
    gaps, unparsed = [], []
    file_ref = max_tick_ms = None
    header_ok = False
    for line in Path(txt_path).read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        if line == HEADER_LINE:
            header_ok = True
        elif match := FILE_LINE.match(line):
            file_ref = match["name"]
        elif match := GAP_LINE.match(line):
            gaps.append((int(match["seconds"]), match["start"], match["end"]))
        elif match := MAX_TICK_LINE.match(line):
            max_tick_ms = int(match["ms"])
        else:
            unparsed.append(line)

    gap_df = pd.DataFrame(gaps, columns=["seconds", "start", "end"])
    for column in ("start", "end"):
        gap_df[column] = pd.to_datetime(gap_df[column], format="%Y%m%d%H%M%S")
    return {
        "header_ok": header_ok,
        "file_ref": file_ref,
        "gaps": gap_df,
        "max_tick_interval_ms": max_tick_ms,
        "unparsed_lines": unparsed,
    }


def build_inventory(data_dir: Path, pattern: str = "**/DAT_ASCII_EURUSD_M1_*.csv") -> pd.DataFrame:
    return pd.DataFrame([asdict(describe_raw_file(p)) for p in discover_raw_files(data_dir, pattern)])


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory raw EURUSD HistData M1 files (read-only).")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()

    inventory = build_inventory(Path(args.data_dir))
    columns = ["period", "rows", "malformed_rows", "price_decimals", "csv_bytes",
               "txt_bytes", "first_timestamp", "last_timestamp"]
    print(inventory[columns].to_string(index=False))
    print(f"\n{len(inventory)} CSV files, {inventory['rows'].sum():,} rows, "
          f"{inventory['csv_bytes'].sum() + inventory['txt_bytes'].fillna(0).sum():,.0f} bytes (CSV+TXT)")


if __name__ == "__main__":
    main()
