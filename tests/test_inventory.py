"""Inventory tests on small synthetic files in a temporary directory."""

from pathlib import Path

import pandas as pd
import pytest

from src.data.inventory import (
    build_inventory,
    describe_raw_file,
    discover_raw_files,
    nominal_period_bounds,
    parse_gap_report,
    parse_period,
    sha256_file,
)

BARS = (
    "20240102 170000;2.104270;2.104290;2.104250;2.104290;0\n"
    "20240102 170100;2.104290;2.104290;2.104290;2.104290;0\n"
    "20240102 170300;2.104300;2.104400;2.104200;2.104350;0\n"
)

REPORT = (
    "HistData.com (c) 2012\n"
    "File: DAT_ASCII_EURUSD_M1_2024.csv Status Report\n"
    "\n"
    "Gap of 62s found between 20240102170143 and 20240102170245.\n"
    "Gap of 150s found between 20240102171000 and 20240102171230.\n"
    "Maximum tick interval found: 287000 miliseconds.\n"
)


def make_file(directory: Path, name: str, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text, encoding="ascii")
    return path


def test_parse_period():
    assert parse_period("DAT_ASCII_EURUSD_M1_2015.csv") == ("2015", "year")
    assert parse_period("DAT_ASCII_EURUSD_M1_202608.csv") == ("202608", "month")
    assert parse_period("DAT_ASCII_EURUSD_M1_2015.txt") is None
    assert parse_period("eurusd_1m.parquet") is None


def test_nominal_period_bounds():
    assert nominal_period_bounds("2015") == (pd.Timestamp("2015-01-01"), pd.Timestamp("2016-01-01"))
    assert nominal_period_bounds("202612") == (pd.Timestamp("2026-12-01"), pd.Timestamp("2027-01-01"))


def test_discover_sorts_years_before_months(tmp_path):
    make_file(tmp_path / "b", "DAT_ASCII_EURUSD_M1_202601.csv", BARS)
    make_file(tmp_path / "a", "DAT_ASCII_EURUSD_M1_2025.csv", BARS)
    make_file(tmp_path / "a", "notes.csv", "x")
    names = [p.name for p in discover_raw_files(tmp_path)]
    assert names == ["DAT_ASCII_EURUSD_M1_2025.csv", "DAT_ASCII_EURUSD_M1_202601.csv"]


def test_describe_raw_file_counts_rows_and_flags_malformed(tmp_path):
    path = make_file(tmp_path, "DAT_ASCII_EURUSD_M1_2024.csv", BARS + "20240102 1704;1.1;1.1;1.1;1.1;0\n")
    make_file(tmp_path, "DAT_ASCII_EURUSD_M1_2024.txt", REPORT)
    info = describe_raw_file(path)
    assert info.rows == 4
    assert info.malformed_rows == 1
    assert info.price_decimals == "6"
    assert info.first_timestamp == "20240102 170000"
    assert info.last_timestamp == "20240102 1704"
    assert info.txt_path is not None


def test_inventory_does_not_modify_files(tmp_path):
    path = make_file(tmp_path, "DAT_ASCII_EURUSD_M1_2024.csv", BARS)
    before = sha256_file(path)
    inventory = build_inventory(tmp_path)
    assert len(inventory) == 1
    assert sha256_file(path) == before


def test_parse_gap_report(tmp_path):
    parsed = parse_gap_report(make_file(tmp_path, "DAT_ASCII_EURUSD_M1_2024.txt", REPORT + "something odd\n"))
    assert parsed["header_ok"]
    assert parsed["file_ref"] == "DAT_ASCII_EURUSD_M1_2024.csv"
    assert parsed["gaps"]["seconds"].tolist() == [62, 150]
    assert parsed["gaps"]["start"].iloc[0] == pd.Timestamp("2024-01-02 17:01:43")
    assert parsed["max_tick_interval_ms"] == 287000
    assert parsed["unparsed_lines"] == ["something odd"]


@pytest.mark.parametrize("bad_line", ["", "20240102 170000;1.1;1.1"])
def test_describe_raw_file_ignores_blank_but_flags_short_lines(tmp_path, bad_line):
    path = make_file(tmp_path, "DAT_ASCII_EURUSD_M1_2024.csv", BARS + bad_line + "\n")
    info = describe_raw_file(path)
    assert info.malformed_rows == (0 if bad_line == "" else 1)
