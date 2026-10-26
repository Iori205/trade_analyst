"""Audit tests on small synthetic fixtures. No historical data is read."""

from pathlib import Path

import pandas as pd
import pytest

from src.data.audit import (
    compare_frames,
    conflicting_duplicate_choice,
    detect_gaps,
    find_duplicates,
    find_out_of_order,
    load_raw,
    parse_timestamps,
    raw_reference,
    read_raw_csv,
    resample_reference,
    validate_ohlc,
    write_new,
    write_report,
)
from src.data.inventory import sha256_file


def write_csv(directory: Path, name: str, lines: list[str]) -> Path:
    path = directory / name
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


def bar(ts: str, o=1.1, h=1.2, l=1.0, c=1.15, v=0) -> str:
    return f"{ts};{o:.6f};{h:.6f};{l:.6f};{c:.6f};{v}"


# --- timestamp parsing -------------------------------------------------------
def test_parse_timestamps_is_strict_and_naive():
    parsed = parse_timestamps(["20240102 170000", "20241027 190159"])
    assert parsed.tolist() == [pd.Timestamp("2024-01-02 17:00:00"), pd.Timestamp("2024-10-27 19:01:59")]
    assert parsed.dt.tz is None


@pytest.mark.parametrize("bad", ["2024-01-02 17:00:00", "20240102 1700", "20240132 170000", "", "20240102170000"])
def test_parse_timestamps_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        parse_timestamps([bad])


def test_read_raw_csv_preserves_values_order_and_file(tmp_path):
    path = write_csv(tmp_path, "DAT_ASCII_EURUSD_M1_2024.csv", [
        bar("20240102 170100", 2.104290, h=2.2, l=2.0, c=2.15),
        bar("20240102 170000", 2.104270, h=2.2, l=2.0, c=2.15),   # out of order on purpose
    ])
    before = sha256_file(path)
    df = read_raw_csv(path)
    assert df["source_row"].tolist() == [0, 1]
    assert df["timestamp"].tolist() == [pd.Timestamp("2024-01-02 17:01"), pd.Timestamp("2024-01-02 17:00")]
    assert df["open"].tolist() == [2.104290, 2.104270]
    assert sha256_file(path) == before


def test_read_raw_csv_rejects_empty_field(tmp_path):
    path = write_csv(tmp_path, "DAT_ASCII_EURUSD_M1_2024.csv", ["20240102 170000;1.1;;1.0;1.1;0"])
    with pytest.raises(ValueError):
        read_raw_csv(path)


# --- duplicates and ordering -------------------------------------------------
@pytest.fixture
def raw_with_duplicates(tmp_path):
    path = write_csv(tmp_path, "DAT_ASCII_EURUSD_M1_2024.csv", [
        bar("20241027 185900"),
        bar("20241027 190000", c=1.11),
        bar("20241027 190000", c=1.11),          # identical duplicate
        bar("20240705 173200", c=1.12),
        bar("20240705 173100", c=1.13),          # out of order
        bar("20240705 173100", c=1.14),          # conflicting duplicate
    ])
    return load_raw([path])


def test_find_duplicates_distinguishes_identical_and_conflicting(raw_with_duplicates):
    dup = find_duplicates(raw_with_duplicates)
    status = dup.groupby("timestamp")["status"].first()
    assert status[pd.Timestamp("2024-10-27 19:00")] == "identical"
    assert status[pd.Timestamp("2024-07-05 17:31")] == "conflicting"
    assert len(dup) == 4
    assert len(raw_with_duplicates) == 6  # nothing dropped from the input


def test_find_duplicates_across_files(tmp_path):
    a = write_csv(tmp_path, "DAT_ASCII_EURUSD_M1_2024.csv", [bar("20241231 235900")])
    b = write_csv(tmp_path, "DAT_ASCII_EURUSD_M1_2025.csv", [bar("20241231 235900", c=1.19)])
    dup = find_duplicates(load_raw([a, b]))
    assert set(dup["files"]) == {2}
    assert set(dup["status"]) == {"conflicting"}


def test_find_duplicates_none(tmp_path):
    path = write_csv(tmp_path, "DAT_ASCII_EURUSD_M1_2024.csv", [bar("20240102 170000"), bar("20240102 170100")])
    assert find_duplicates(load_raw([path])).empty


def test_find_out_of_order(raw_with_duplicates):
    out = find_out_of_order(raw_with_duplicates)
    # row 2 repeats 19:00 (not later), rows 3 and 4 jump backwards, row 5 repeats 17:31
    assert out["source_row"].tolist() == [2, 3, 4, 5]


# --- OHLC validation ---------------------------------------------------------
def test_validate_ohlc_flags_each_rule(tmp_path):
    path = write_csv(tmp_path, "DAT_ASCII_EURUSD_M1_2024.csv", [
        bar("20240102 170000"),                                # valid
        bar("20240102 170100", o=1.1, h=1.05, l=1.0, c=1.02),  # high below open
        bar("20240102 170200", o=1.1, h=1.2, l=1.12, c=1.15),  # low above open
        bar("20240102 170300", o=1.1, h=1.0, l=1.2, c=1.1),    # high below low
        bar("20240102 170400", o=0.0, h=1.2, l=0.0, c=1.1),    # non-positive
        bar("20240102 170500", o=1.1, h=1.1, l=1.1, c=1.1),    # flat bar is valid
    ])
    bad = validate_ohlc(load_raw([path])).set_index("source_row")
    assert list(bad.index) == [1, 2, 3, 4]
    assert bad.loc[1, "high_below_open_or_close"]
    assert bad.loc[2, "low_above_open_or_close"]
    assert bad.loc[3, "high_below_low"]
    assert bad.loc[4, "non_positive_price"]


# --- gaps ----------------------------------------------------------------------
def minutes(start: str, count: int) -> list[pd.Timestamp]:
    return list(pd.date_range(start, periods=count, freq="1min"))


def test_detect_gaps_classifies_weekend_short_and_long():
    ts = (
        minutes("2024-03-08 10:00", 3)            # Fri
        + minutes("2024-03-08 10:05", 2)          # 2-bar gap -> short
        + minutes("2024-03-08 12:00", 2)          # 113-bar gap -> long
        + minutes("2024-03-08 16:58", 2)          # Fri close, 296-bar gap -> long
        + minutes("2024-03-10 17:00", 2)          # Sun open -> weekend
    )
    gaps = detect_gaps(ts, short_gap_max_minutes=30, weekend_max_hours=56)
    assert gaps["category"].tolist() == ["intraweek_short", "intraweek_long", "intraweek_long", "weekend"]
    assert gaps["missing_bars"].tolist()[:2] == [2, 113]


def test_detect_gaps_holiday_candidate():
    ts = minutes("2024-12-24 12:58", 2) + minutes("2024-12-26 17:00", 1)  # Tue -> Thu over Christmas
    holidays = ("12-24", "12-25", "12-26")
    assert detect_gaps(ts, holiday_month_days=holidays)["category"].tolist() == ["holiday_candidate"]
    assert detect_gaps(ts)["category"].tolist() == ["intraweek_long"]  # no holiday list -> not hidden


def test_detect_gaps_short_gap_on_holiday_stays_short():
    ts = minutes("2024-12-24 10:00", 1) + minutes("2024-12-24 10:03", 1)
    assert detect_gaps(ts, holiday_month_days=("12-24",))["category"].tolist() == ["intraweek_short"]


def test_detect_gaps_ignores_duplicates_and_order():
    ts = [pd.Timestamp("2024-03-06 10:02"), pd.Timestamp("2024-03-06 10:00"),
          pd.Timestamp("2024-03-06 10:00"), pd.Timestamp("2024-03-06 10:01")]
    assert detect_gaps(ts).empty


def test_detect_gaps_long_weekend_is_not_weekend():
    ts = minutes("2024-03-08 16:58", 2) + minutes("2024-03-11 17:00", 1)  # Fri -> Mon 17:00 (72h)
    assert detect_gaps(ts, weekend_max_hours=56)["category"].tolist() == ["intraweek_long"]


# --- Parquet comparison --------------------------------------------------------
def test_reference_and_resample_and_compare(tmp_path):
    path = write_csv(tmp_path, "DAT_ASCII_EURUSD_M1_2024.csv", [
        bar("20240102 170000", o=1.0, h=1.3, l=0.9, c=1.1),
        bar("20240102 170100", o=1.1, h=1.4, l=1.0, c=1.2),
        bar("20240102 170100", o=1.1, h=1.5, l=1.0, c=1.3),   # conflicting duplicate
        bar("20240102 171500", o=1.2, h=1.2, l=1.2, c=1.2),
    ])
    raw = load_raw([path])
    reference = raw_reference(raw)
    assert len(reference) == 3
    assert reference.loc[pd.Timestamp("2024-01-02 17:01"), "high"] == 1.4  # first occurrence

    m15 = resample_reference(reference, "15min")
    assert m15.index.tolist() == [pd.Timestamp("2024-01-02 17:00"), pd.Timestamp("2024-01-02 17:15")]
    assert m15.iloc[0].tolist() == [1.0, 1.4, 0.9, 1.2]

    assert compare_frames(reference, reference)["value_mismatch_rows"] == 0
    altered = reference.copy()
    altered.loc[pd.Timestamp("2024-01-02 17:01"), ["high", "close"]] = [1.5, 1.3]  # = second variant
    result = compare_frames(reference, altered.iloc[:2])
    assert result["value_mismatch_rows"] == 1
    assert result["only_in_expected"] == 1

    dup = find_duplicates(raw)
    assert conflicting_duplicate_choice(dup, altered)["parquet_matches"].iloc[0].startswith("occurrence_2_of_2")
    assert conflicting_duplicate_choice(dup, reference)["parquet_matches"].iloc[0].startswith("occurrence_1_of_2")


# --- report writing never overwrites -----------------------------------------
def test_write_new_refuses_to_overwrite(tmp_path):
    target = tmp_path / "x.md"
    write_new(target, "first")
    with pytest.raises(FileExistsError):
        write_new(target, "second")
    assert target.read_text() == "first"


def test_write_report_refuses_existing_run_dir(tmp_path):
    (tmp_path / "data_audit_20260101T000000Z").mkdir()
    with pytest.raises(FileExistsError):
        write_report({}, tmp_path, stamp="20260101T000000Z")
