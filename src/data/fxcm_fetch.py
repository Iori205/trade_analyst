"""Gated fetch of FXCM m1 EURUSD weekly candle files into data/reference/fxcm/.

Nothing is downloaded unless a written approval note exists that names the
terms basis and every requested week. Files are stored exactly as received,
never overwritten, and each one's actual date coverage is checked from its
contents (the URL week number is not trusted to mean any calendar week).

Run (only after approval is documented):
    .venv/bin/python -m src.data.fxcm_fetch --approval docs/approvals/fxcm_batch1.md \
        --weeks 2018/12 2018/43 2018/44 2019/11
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import subprocess
import time
from pathlib import Path

import pandas as pd

from src.data.fxcm_audit import FXCM_COLUMNS, FXCM_TS_FORMAT, FXCM_TS_PATTERN
from src.data.inventory import sha256_file

# Documented in the FXCM MarketData README (re-read 2026-10-26):
# https://candledata.fxcorporate.com/{periodicity}/{instrument}/{year}/{int of week of year}.csv.gz
URL_PATTERN = "https://candledata.fxcorporate.com/m1/EURUSD/{year}/{week}.csv.gz"
DEFAULT_ROOT = Path("data/reference/fxcm/v1")
REQUIRED_APPROVAL_KEYS = ("approved_by", "approved_on", "terms_basis", "approved_weeks")
MAX_FILE_BYTES = 2_000_000
MANIFEST_COLUMNS = [
    "fxcm_year", "fxcm_week", "url", "local_path", "retrieved_utc", "http_status", "content_length",
    "last_modified", "etag", "content_type", "sha256_gz", "gz_bytes", "header_ok", "data_rows",
    "first_label", "last_label", "first_label_weekday", "last_label_weekday", "distinct_dates",
    "iso_week_monday", "coverage_status", "notes",
]


def parse_week(text: str) -> tuple[int, int]:
    year, week = text.strip().split("/")
    year, week = int(year), int(week)
    if not (2000 <= year <= 2100 and 1 <= week <= 53):
        raise ValueError(f"bad week {text!r}")
    return year, week


def candidate_url(year: int, week: int) -> str:
    return URL_PATTERN.format(year=year, week=week)


def read_approval(path: Path) -> dict:
    """Parse a 'key: value' approval note. Refuses incomplete or placeholder notes."""
    if not path.is_file():
        raise PermissionError(f"approval note {path} does not exist; nothing will be downloaded")
    fields = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1)
            fields[key.strip().lower()] = value.strip()
    missing = [k for k in REQUIRED_APPROVAL_KEYS if not fields.get(k)]
    placeholders = [k for k in REQUIRED_APPROVAL_KEYS if "TODO" in fields.get(k, "") or "<" in fields.get(k, "")]
    if missing or placeholders:
        raise PermissionError(f"approval note incomplete: missing {missing}, placeholders {placeholders}")
    fields["weeks"] = {parse_week(w) for w in fields["approved_weeks"].replace(";", ",").split(",") if w.strip()}
    return fields


def check_requested(requested: list[tuple[int, int]], approval: dict) -> None:
    unapproved = [f"{y}/{w}" for y, w in requested if (y, w) not in approval["weeks"]]
    if unapproved:
        raise PermissionError(f"weeks not in the approval note: {unapproved}")


def iso_monday(year: int, week: int) -> dt.date | None:
    try:
        return dt.date.fromisocalendar(year, week, 1)
    except ValueError:
        return None


def inspect_content(gz_bytes: bytes, year: int, week: int) -> dict:
    """Decompress in memory and record what dates the file actually covers."""
    out = {"header_ok": False, "data_rows": 0, "first_label": "", "last_label": "", "first_label_weekday": "",
           "last_label_weekday": "", "distinct_dates": 0, "iso_week_monday": "", "coverage_status": "", "notes": ""}
    monday = iso_monday(year, week)
    out["iso_week_monday"] = monday.isoformat() if monday else "no such ISO week"
    try:
        text = gzip.decompress(gz_bytes).decode("ascii")
    except (OSError, EOFError, UnicodeDecodeError) as exc:
        out.update(coverage_status="unreadable", notes=f"{type(exc).__name__}: {exc}")
        return out
    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    out["header_ok"] = list(df.columns) == FXCM_COLUMNS
    out["data_rows"] = len(df)
    if not out["header_ok"] or df.empty:
        out.update(coverage_status="bad_schema", notes=f"columns {list(df.columns)}")
        return out
    valid = df["DateTime"].str.fullmatch(FXCM_TS_PATTERN)
    if not valid.all():
        out.update(coverage_status="bad_timestamps", notes=f"{int((~valid).sum())} malformed timestamps")
        return out
    labels = pd.to_datetime(df["DateTime"], format=FXCM_TS_FORMAT)
    first, last = labels.min(), labels.max()
    out.update(first_label=str(first), last_label=str(last), first_label_weekday=first.day_name(),
               last_label_weekday=last.day_name(), distinct_dates=int(labels.dt.date.nunique()))
    if monday is None:
        out.update(coverage_status="no_iso_week", notes="week number has no ISO meaning; contents recorded only")
        return out
    sunday, saturday = pd.Timestamp(monday) - pd.Timedelta(days=1), pd.Timestamp(monday) + pd.Timedelta(days=5)
    weekdays = set(labels[labels.dt.dayofweek < 5].dt.date)
    expected_weekdays = {(pd.Timestamp(monday) + pd.Timedelta(days=i)).date() for i in range(5)}
    inside = bool((labels >= sunday).all() and (labels < saturday).all())
    if inside and weekdays == expected_weekdays:
        out["coverage_status"] = "ok"
    else:
        out.update(coverage_status="mismatch",
                   notes=f"expected labels in [{sunday.date()} 00:00, {saturday.date()} 00:00) with 5 weekdays; "
                         f"weekdays present {len(weekdays & expected_weekdays)}/5")
    return out


def curl_download(url: str, part_path: Path, header_path: Path) -> dict:
    """One GET with curl (Python urllib was refused by the CDN in the earlier probe)."""
    cmd = ["curl", "--silent", "--show-error", "--fail", "--proto", "=https", "--max-filesize", str(MAX_FILE_BYTES),
           "--max-time", "60", "--dump-header", str(header_path), "--output", str(part_path), url]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    headers = parse_headers(header_path.read_text(errors="replace")) if header_path.exists() else {}
    return {"returncode": proc.returncode, "stderr": proc.stderr.strip(), **headers}


def parse_headers(raw: str) -> dict:
    """Status and selected headers of the final response block."""
    blocks = [b for b in raw.replace("\r\n", "\n").split("\n\n") if b.strip()]
    if not blocks:
        return {}
    lines = blocks[-1].splitlines()
    status = lines[0].split()[1] if len(lines[0].split()) > 1 else ""
    fields = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip().lower()] = v.strip()
    return {"http_status": status, "content_length": fields.get("content-length", ""),
            "last_modified": fields.get("last-modified", ""), "etag": fields.get("etag", ""),
            "content_type": fields.get("content-type", "")}


def fetch_batch(requested: list[tuple[int, int]], approval_path: Path, root: Path = DEFAULT_ROOT,
                downloader=curl_download, pause_seconds: float = 2.0) -> pd.DataFrame:
    approval = read_approval(approval_path)
    check_requested(requested, approval)
    root.mkdir(parents=True, exist_ok=False)  # a new version directory every batch; never reused
    (root / "APPROVAL.md").write_bytes(approval_path.read_bytes())
    meta_dir = root / "http_headers"
    meta_dir.mkdir()
    rows = []
    for i, (year, week) in enumerate(requested):
        if i:
            time.sleep(pause_seconds)
        url = candidate_url(year, week)
        final = root / "m1" / "EURUSD" / str(year) / f"{week}.csv.gz"
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            raise FileExistsError(final)
        part = final.with_name(final.name + ".part")
        header_path = meta_dir / f"{year}_{week}.txt"
        retrieved = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = downloader(url, part, header_path)
        row = {"fxcm_year": year, "fxcm_week": week, "url": url, "local_path": "", "retrieved_utc": retrieved,
               **{k: result.get(k, "") for k in ("http_status", "content_length", "last_modified", "etag", "content_type")}}
        if result.get("returncode") != 0 or not part.exists():
            row.update(coverage_status="download_failed", notes=result.get("stderr", ""))
            part.unlink(missing_ok=True)
            rows.append(row)
            continue
        data = part.read_bytes()
        part.rename(final)  # final did not exist (checked above)
        row.update(local_path=str(final.relative_to(root)), sha256_gz=sha256_file(final), gz_bytes=len(data),
                   **inspect_content(data, year, week))
        rows.append(row)
    manifest = pd.DataFrame(rows).reindex(columns=MANIFEST_COLUMNS)
    with open(root / "MANIFEST.csv", "x", encoding="utf-8", newline="") as handle:
        manifest.to_csv(handle, index=False)
    with open(root / "SHA256SUMS.txt", "x", encoding="utf-8") as handle:
        for r in manifest.itertuples():
            if isinstance(r.sha256_gz, str) and r.sha256_gz:
                handle.write(f"{r.sha256_gz}  {r.local_path}\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--weeks", nargs="+", required=True, help="e.g. 2018/12 2018/43")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    manifest = fetch_batch([parse_week(w) for w in args.weeks], args.approval, args.root)
    print(manifest[["fxcm_year", "fxcm_week", "http_status", "gz_bytes", "first_label", "last_label",
                    "coverage_status"]].to_string(index=False))


if __name__ == "__main__":
    main()
