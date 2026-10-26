"""Tests for the day-level FXCM timezone comparison. Synthetic fixtures only."""

import numpy as np
import pandas as pd

from src.data.fxcm_audit import FXCM_COLUMNS, read_fxcm_csv
from src.data.fxcm_tz_compare import (
    candidate_verdicts, cell_summary, compare_file, day_exclusion, gap_mask_minutes, long_gaps,
)
from src.data.reference_compare import label_minutes


def write_pair(tmp_path, hist_start: str, offset_minutes: int, n: int, year: int, seed: int = 4):
    rng = np.random.default_rng(seed)
    closes = np.round(1.15 * np.exp(np.cumsum(rng.normal(0, 1e-4, n))), 5)
    hist_t = pd.date_range(hist_start, periods=n, freq="1min")
    raw_dir = tmp_path / "data" / f"HISTDATA_COM_ASCII_EURUSD_M1{year}"
    raw_dir.mkdir(parents=True)
    (raw_dir / f"DAT_ASCII_EURUSD_M1_{year}.csv").write_text(
        "\n".join(f"{t:%Y%m%d %H%M%S};{c:.6f};{c:.6f};{c:.6f};{c:.6f};0" for t, c in zip(hist_t, closes)) + "\n",
        encoding="ascii")
    fx_t = hist_t + pd.Timedelta(minutes=offset_minutes)
    noisy = np.round(closes + rng.normal(0, 3e-6, n), 5)
    lines = [",".join(FXCM_COLUMNS)] + [f"{t:%m/%d/%Y %H:%M:%S}.000," + ",".join([f"{c:.5f}"] * 4 + [f"{c + 2e-5:.5f}"] * 4)
                                        for t, c in zip(fx_t, noisy)]
    fx_path = tmp_path / "week.csv"
    fx_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return fx_path, tmp_path / "data"


def test_gap_helpers():
    m = np.array([0, 1, 2, 50, 51])
    assert long_gaps(m, 0, 100) == [(2, 50)]
    assert gap_mask_minutes(m, long_gap=30, skip=2) == {50, 51}


def test_summer_us_only_day_matches_h2_or_h3(tmp_path):
    # 2018-07-10 (both_summer): FXCM UTC = HistData label + 240 -> H2 and H3 match, H1 does not
    fx_path, raw = write_pair(tmp_path, "2018-07-09 20:00", 240, 1700, 2018)
    rows, scans, info, weekly = compare_file(fx_path, raw, "**/DAT_ASCII_EURUSD_M1_*.csv", max_offset=360)
    day = next(r for r in rows if r["utc_day"] == "2018-07-10")
    assert day["regime"] == "both_summer" and day["best_offset_minutes"] == 240 and day["counts_as_decisive"]
    assert day["hypotheses_matching_best"] == "H2_america_new_york,H3_zurich_minus_6h"
    assert day["exact_pairs"] == 0 or day["exact_identical_ohlc_share"] < 0.1
    w = {r["test"]: r for r in weekly}
    assert w["H2_america_new_york"]["is_best_offset"] and w["H2_america_new_york"]["timestamp_match_pct"] > 99
    assert not w["H1_fixed_utc-5"]["is_best_offset"] and w["H1_fixed_utc-5"]["predicted_offset_minutes"] == 300
    assert w["H2_america_new_york"]["close_median_abs_pips"] < 0.1
    assert w["H2_america_new_york"]["second_offset_minutes"] != 240


def test_day_exclusion_reasons():
    fx = label_minutes(pd.Series(pd.date_range("2018-03-19 00:00", "2018-03-19 23:59", freq="1min")))
    assert day_exclusion(pd.Timestamp("2018-03-18"), fx).startswith("weekend")
    assert day_exclusion(pd.Timestamp("2018-12-25"), fx).startswith("holiday")
    assert day_exclusion(pd.Timestamp("2018-03-19"), fx) == ""
    holed = fx[(fx < fx[600]) | (fx > fx[700])]
    assert day_exclusion(pd.Timestamp("2018-03-19"), holed).startswith("long FXCM gap")


def daily_frame(cells):
    rows = []
    for era, regime, year, best, n in cells:
        preds = {"both_standard": (300, 300, 300), "both_summer": (300, 240, 240),
                 "us_summer_eu_standard": (300, 240, 300)}[regime]
        for _ in range(n):
            rows.append({"era": era, "regime": regime, "year": year, "best_offset_minutes": best,
                         "counts_as_decisive": True, "exclusion_reason": "",
                         "pred_H1_fixed_utc-5": preds[0], "pred_H2_america_new_york": preds[1],
                         "pred_H3_zurich_minus_6h": preds[2]})
    return pd.DataFrame(rows)


def test_verdicts_recommend_only_when_all_cells_filled_and_rivals_contradicted():
    full = [("before_2018-12-16", "both_standard", 2018, 300, 5), ("before_2018-12-16", "both_summer", 2018, 240, 5),
            ("before_2018-12-16", "us_summer_eu_standard", 2018, 240, 5), ("from_2018-12-16", "both_standard", 2019, 300, 5),
            ("from_2018-12-16", "both_summer", 2019, 240, 5), ("from_2018-12-16", "us_summer_eu_standard", 2019, 300, 5)]
    v = candidate_verdicts(cell_summary(daily_frame(full))).set_index("candidate")
    assert v.loc["C4_h2_then_h3_at_2018-12-16", "recommendable"]
    assert not v.loc["C2_america_new_york", "accepted"] and not v.loc["C1_fixed_utc-5", "accepted"]
    partial = cell_summary(daily_frame(full[:3] + [("from_2018-12-16", "us_summer_eu_standard", 2019, 300, 5)]))
    v2 = candidate_verdicts(partial).set_index("candidate")
    assert not v2["recommendable"].any()
    assert "from_2018-12-16/both_summer (0 decisive)" in v2.loc["C4_h2_then_h3_at_2018-12-16", "cells_missing_evidence"]


# ---------------------------------------------------------------------------
# Timezone hypotheses as functions
# ---------------------------------------------------------------------------
import pytest

from src.data.fxcm_tz_compare import (
    candidate_offset_minutes, era_of, predicted_offset_minutes, source_label, sunday_first_bars, sunday_open_table,
)
from src.data.investigate import HYPOTHESES as REGIME_HYPOTHESES, REGIMES, dst_regime, source_offset_hours


@pytest.mark.parametrize("utc, h1, h2, h3", [
    ("2018-01-15 12:00", 300, 300, 300),   # both standard
    ("2018-07-10 12:00", 300, 240, 240),   # both summer
    ("2018-03-20 12:00", 300, 240, 300),   # US-only spring window
    ("2024-10-29 12:00", 300, 240, 300),   # US-only autumn window
])
def test_hypothesis_offsets_by_regime(utc, h1, h2, h3):
    assert predicted_offset_minutes("H1_fixed_utc-5", utc) == h1
    assert predicted_offset_minutes("H2_america_new_york", utc) == h2
    assert predicted_offset_minutes("H3_zurich_minus_6h", utc) == h3


def test_source_label_examples():
    # 2019-03-12 12:30 UTC (CPI, 08:30 EDT): H2 labels it 08:30, H1 and H3 label it 07:30
    assert source_label("H2_america_new_york", "2019-03-12 12:30") == pd.Timestamp("2019-03-12 08:30")
    assert source_label("H1_fixed_utc-5", "2019-03-12 12:30") == pd.Timestamp("2019-03-12 07:30")
    assert source_label("H3_zurich_minus_6h", "2019-03-12 12:30") == pd.Timestamp("2019-03-12 07:30")


def test_tz_hypotheses_agree_with_regime_tables_on_weekdays():
    days = pd.date_range("2015-01-05 12:00", "2026-08-31 12:00", freq="D")
    days = days[days.dayofweek < 5]
    regimes = dst_regime(pd.Series(days.normalize()))
    old = {"H1_fixed_utc-5": "H1_fixed_utc-5", "H2_america_new_york": "H2_america_new_york",
           "H3_zurich_minus_6h": "H3_ny_offset_eu_dates"}
    for new, prev in old.items():
        assert prev in REGIME_HYPOTHESES
        expected = [-60 * source_offset_hours(prev, *REGIMES[r]) for r in regimes]
        assert [predicted_offset_minutes(new, d) for d in days] == expected


def test_era_boundary_and_candidates():
    assert era_of("2018-12-15 23:59") == "before_2018-12-16" and era_of("2018-12-16") == "from_2018-12-16"
    c4 = "C4_h2_then_h3_at_2018-12-16"
    assert candidate_offset_minutes(c4, "2018-03-20 12:00") == 240   # H2 before the boundary
    assert candidate_offset_minutes(c4, "2019-03-12 12:00") == 300   # H3 after it
    assert candidate_offset_minutes("C4r_h3_then_h2_at_2018-12-16", "2019-03-12 12:00") == 240


def test_sunday_first_bars_and_table():
    ts = pd.to_datetime(["2018-03-11 17:00", "2018-03-11 17:01", "2018-03-12 00:00",   # US-only, 17:00 open
                         "2019-03-10 16:00", "2019-03-10 16:01",                         # US-only, 16:00 open
                         "2019-07-14 17:00"])                                            # summer
    raw = pd.DataFrame({"timestamp": ts, "source_file": "f.csv", "source_row": range(len(ts))})
    opens = sunday_first_bars(raw)
    assert opens["first_bar_hm"].tolist() == ["17:00", "16:00", "17:00"]
    assert opens["line_number"].tolist() == [1, 4, 6]
    assert opens.loc[0, "H2_america_new_york_consistent"] and not opens.loc[0, "H3_zurich_minus_6h_consistent"]
    assert opens.loc[1, "H3_zurich_minus_6h_consistent"] and opens.loc[1, "H1_fixed_utc-5_consistent"]
    table = sunday_open_table(opens)
    assert table["era"].tolist()[0] == "before_2018-12-16"
    assert table["weeks"].sum() == 3
