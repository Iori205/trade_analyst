"""Tests for the gated FXCM fetch. No network: the downloader is replaced."""

import gzip
from pathlib import Path

import pandas as pd
import pytest

from src.data.fxcm_audit import FXCM_COLUMNS
from src.data.fxcm_fetch import (
    candidate_url, fetch_batch, inspect_content, parse_headers, read_approval,
)

APPROVAL = """# FXCM batch approval
approved_by: test owner
approved_on: 2026-10-26
terms_basis: test terms
approved_weeks: 2018/12, 2018/43
"""


def week_csv(start: str, periods: int, freq: str = "1h") -> bytes:
    times = pd.date_range(start, periods=periods, freq=freq)
    lines = [",".join(FXCM_COLUMNS)] + [f"{t:%m/%d/%Y %H:%M:%S}.000," + ",".join(["1.1"] * 8) for t in times]
    return gzip.compress(("\n".join(lines) + "\n").encode("ascii"))


def test_candidate_url_follows_documented_pattern():
    assert candidate_url(2018, 12) == "https://candledata.fxcorporate.com/m1/EURUSD/2018/12.csv.gz"


def test_read_approval_refuses_missing_or_placeholder(tmp_path):
    with pytest.raises(PermissionError):
        read_approval(tmp_path / "absent.md")
    note = tmp_path / "a.md"
    note.write_text(APPROVAL.replace("test terms", "TODO"), encoding="utf-8")
    with pytest.raises(PermissionError):
        read_approval(note)
    note.write_text(APPROVAL, encoding="utf-8")
    assert read_approval(note)["weeks"] == {(2018, 12), (2018, 43)}


def test_inspect_content_ok_and_mismatch():
    # ISO 2018-W12 is Mon 2018-03-19; the file runs Sunday 21:00 to Friday 20:00
    ok = inspect_content(week_csv("2018-03-18 21:00", 120), 2018, 12)
    assert ok["coverage_status"] == "ok" and ok["header_ok"] and ok["first_label_weekday"] == "Sunday"
    shifted = inspect_content(week_csv("2018-03-11 21:00", 120), 2018, 12)  # previous week's contents
    assert shifted["coverage_status"] == "mismatch"
    assert inspect_content(b"not gzip", 2018, 12)["coverage_status"] == "unreadable"


def test_parse_headers_uses_final_block():
    raw = "HTTP/1.1 301 Moved\r\nLocation: x\r\n\r\nHTTP/2 200\r\ncontent-length: 10\r\nlast-modified: Thu, 29 Mar 2018\r\n\r\n"
    h = parse_headers(raw)
    assert h["http_status"] == "200" and h["content_length"] == "10" and h["last_modified"] == "Thu, 29 Mar 2018"


def fake_downloader(payloads):
    def download(url, part_path: Path, header_path: Path):
        header_path.write_text("HTTP/2 200\r\ncontent-length: 1\r\n\r\n")
        part_path.write_bytes(payloads[url])
        return {"returncode": 0, "stderr": "", **parse_headers(header_path.read_text())}
    return download


def test_fetch_batch_gated_and_never_overwrites(tmp_path):
    note = tmp_path / "approval.md"
    note.write_text(APPROVAL, encoding="utf-8")
    root = tmp_path / "reference" / "v1"
    payloads = {candidate_url(2018, 12): week_csv("2018-03-18 21:00", 120)}
    with pytest.raises(PermissionError):  # 2019/44 not approved: nothing is created
        fetch_batch([(2019, 44)], note, root, downloader=fake_downloader(payloads), pause_seconds=0)
    assert not root.exists()
    manifest = fetch_batch([(2018, 12)], note, root, downloader=fake_downloader(payloads), pause_seconds=0)
    assert manifest["coverage_status"].tolist() == ["ok"]
    stored = root / "m1" / "EURUSD" / "2018" / "12.csv.gz"
    assert stored.read_bytes() == payloads[candidate_url(2018, 12)]  # bytes exactly as received
    assert (root / "SHA256SUMS.txt").read_text().split()[1] == "m1/EURUSD/2018/12.csv.gz"
    with pytest.raises(FileExistsError):  # a used version directory is never reused
        fetch_batch([(2018, 12)], note, root, downloader=fake_downloader(payloads), pause_seconds=0)
