"""Tests for the investigation helpers. Synthetic inputs only."""

from pathlib import Path

import pandas as pd
import pytest

from src.data.audit import load_raw
from src.data.investigate import (
    anchor_strength,
    classify_gap_hypothesis,
    dst_regime,
    dst_switch_dates,
    duplicate_reports,
    easter_sunday,
    holiday_calendar,
    predicted_source_time,
    repeated_block_continuity,
    spring_hole_price_change,
)
from src.data.inventory import sha256_file


def test_dst_switch_dates_2024():
    s = dst_switch_dates(2024)
    assert s == {"us_start": pd.Timestamp("2024-03-10"), "eu_start": pd.Timestamp("2024-03-31"),
                 "eu_end": pd.Timestamp("2024-10-27"), "us_end": pd.Timestamp("2024-11-03")}


def test_dst_regime_boundaries():
    days = pd.Series(pd.to_datetime(["2024-03-09", "2024-03-10", "2024-03-30", "2024-03-31",
                                     "2024-10-26", "2024-10-27", "2024-11-02", "2024-11-03"]))
    assert dst_regime(days).tolist() == [
        "both_standard", "us_summer_eu_standard", "us_summer_eu_standard", "both_summer",
        "both_summer", "us_summer_eu_standard", "us_summer_eu_standard", "both_standard",
    ]


@pytest.mark.parametrize("year,expected", [(2019, "2019-04-21"), (2023, "2023-04-09"), (2024, "2024-03-31")])
def test_easter(year, expected):
    assert easter_sunday(year) == pd.Timestamp(expected)


def test_holiday_calendar_contains_rules():
    cal = holiday_calendar(2023)
    assert "Good Friday" in cal[pd.Timestamp("2023-04-07")]
    assert "US Memorial Day / UK Spring Bank Holiday" in cal[pd.Timestamp("2023-05-29")]
    assert pd.Timestamp("2020-06-19") not in holiday_calendar(2020)


@pytest.mark.parametrize("anchor,regime,expected", [
    ("us_0830_release", "both_standard", ("08:30", "08:30", "08:30")),
    ("us_0830_release", "both_summer", ("07:30", "08:30", "08:30")),
    ("us_0830_release", "us_summer_eu_standard", ("07:30", "08:30", "07:30")),
    ("london_1600_fix", "both_summer", ("10:00", "11:00", "11:00")),
    ("london_1600_fix", "us_summer_eu_standard", ("11:00", "12:00", "11:00")),
    ("weekly_open_1700_ny", "both_summer", ("16:00", "17:00", "17:00")),
    ("weekly_open_1700_ny", "us_summer_eu_standard", ("16:00", "17:00", "16:00")),
])
def test_predicted_source_time(anchor, regime, expected):
    hypotheses = ("H1_fixed_utc-5", "H2_america_new_york", "H3_ny_offset_eu_dates")
    assert tuple(predicted_source_time(anchor, h, regime) for h in hypotheses) == expected


def test_anchor_strength_relative_to_baseline():
    minutes = pd.date_range("2000-01-03 06:00", "2000-01-03 13:00", freq="1min").strftime("%H:%M")
    profile = pd.Series(1.0, index=minutes)
    profile["08:30"] = 5.0
    profile[["10:55", "10:56", "10:57", "10:58", "10:59"]] = 3.0
    assert anchor_strength(profile, "us_0830_release", "08:30") == 5.0
    assert anchor_strength(profile, "london_1600_fix", "11:00") == 3.0
    assert anchor_strength(profile, "london_1600_fix", "12:00") == 1.0


@pytest.mark.parametrize("start,end,audit_category,expected", [
    ("2024-03-08 16:59", "2024-03-10 17:00", "weekend", "likely_weekend_or_market_closure"),
    ("2024-03-31 18:59", "2024-03-31 20:00", "intraweek_long", "possible_dst_effect"),
    ("2023-04-06 19:59", "2023-04-09 17:04", "intraweek_long", "possible_holiday"),
    ("2020-11-29 23:59", "2020-11-30 19:00", "intraweek_long", "unexplained"),
])
def test_classify_gap_hypothesis(start, end, audit_category, expected):
    category, _ = classify_gap_hypothesis(pd.Timestamp(start), pd.Timestamp(end), audit_category)
    assert category == expected


def test_duplicate_reports_keep_original_text_and_order(tmp_path):
    lines = [
        "20261025 185900;1.1;1.2;1.0;1.1;0",
        "20261025 190000;1.1;1.2;1.0;1.1;0",
        "20261025 190000;1.1;1.2;1.0;1.1;0",
        "20260705 173200;2.150000;2.2;2.0;2.1;0",
        "20260705 173100;2.140000;2.2;2.0;2.1;0",
        "20260705 173100;2.130000;2.2;2.0;2.1;0",
    ]
    path = tmp_path / "DAT_ASCII_EURUSD_M1_2026.csv"
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    before = sha256_file(path)
    reports = duplicate_reports(load_raw([path]), {path.name: path})

    conflicting = reports["conflicting"]
    assert conflicting["line_number"].tolist() == [5, 6]
    assert conflicting["occurrence"].tolist() == [1, 2]
    assert conflicting["raw_line"].tolist() == lines[4:6]
    assert conflicting["timestamp_string"].tolist() == ["20260705 173100"] * 2

    identical = reports["identical_groups"]
    assert identical["dst_switch_date"].tolist() == ["eu_end"]
    assert identical["block_line_ranges"].iloc[0] == "occurrence 1: lines 2-2; occurrence 2: lines 3-3"

    assert reports["out_of_order"]["line_number"].tolist() == [3, 4, 5, 6]
    assert sha256_file(path) == before


def test_repeated_block_continuity(tmp_path):
    lines = [
        "20261025 185900;1.10;1.20;1.00;1.11;0",
        "20261025 190000;1.11;1.20;1.00;1.12;0",
        "20261025 190100;1.12;1.20;1.00;1.13;0",
        "20261025 190000;1.11;1.20;1.00;1.12;0",
        "20261025 190100;1.12;1.20;1.00;1.13;0",
        "20261025 190200;1.13;1.20;1.00;1.14;0",
    ]
    path = tmp_path / "DAT_ASCII_EURUSD_M1_2026.csv"
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    raw = load_raw([path])
    groups = duplicate_reports(raw, {path.name: path})["identical_groups"]
    cont = repeated_block_continuity(raw, groups).iloc[0]
    assert cont["copies_equal"]
    assert cont["join_into_copy2_pips"] == pytest.approx(200.0)  # 1.13 close -> 1.11 open
    assert cont["outer_joins_pips"] == "0.0 / 0.0"


def test_spring_hole_price_change():
    idx = pd.date_range("2024-03-31 18:58", periods=2, freq="1min").append(
        pd.date_range("2024-03-31 20:00", periods=2, freq="1min"))
    closes = pd.Series([2.1000, 2.1001, 2.1004, 2.1005], index=idx)
    transitions = pd.DataFrame({"event": ["eu_start"], "date": [pd.Timestamp("2024-03-31").date()],
                                "long_gaps_on_day": ["18:59->20:00 (60 bars)"]})
    out = spring_hole_price_change(closes, transitions)
    assert out["change_pips"].tolist() == [3.0]
