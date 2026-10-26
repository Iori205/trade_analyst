"""Tests for the reference comparison helpers. Synthetic fixtures only."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data.audit import load_raw
from src.data.inventory import sha256_file
from src.data.reference_compare import (
    assess_peak,
    hypothesis_offsets,
    join_at_offset,
    label_minutes,
    minute_returns,
    missing_minutes,
    offset_scan,
    price_summary,
    read_dukascopy_csv,
    rollover_minutes_utc,
)

HEADER = "Etc/UTC,Open,High,Low,Close,Volume"


def write_dukascopy(directory: Path, rows: list[str]) -> Path:
    path = directory / "EUR-USD_1Minute_BID_test_Etc_UTC.csv"
    path.write_text("\n".join([HEADER, *rows]), encoding="ascii")  # no trailing newline, like the sample
    return path


def test_read_dukascopy_strict_and_utc(tmp_path):
    path = write_dukascopy(tmp_path, ["2025-03-19T00:00:00+00:00,2.09386,2.09388,2.09368,2.09374,67440000",
                                      "2025-03-19T00:01:00+00:00,2.09376,2.09378,2.09367,2.09371,46050000"])
    before = sha256_file(path)
    df = read_dukascopy_csv(path)
    assert str(df["timestamp_utc"].dt.tz) == "UTC"
    assert df["timestamp_text"].tolist()[0] == "2025-03-19T00:00:00+00:00"
    assert df["close"].tolist() == [2.09374, 2.09371]
    assert sha256_file(path) == before


@pytest.mark.parametrize("bad", ["2025-03-19T00:00:00+01:00", "2025-03-19 00:00:00", "2025-03-19T00:00:00Z"])
def test_read_dukascopy_rejects_non_utc_or_malformed(tmp_path, bad):
    path = write_dukascopy(tmp_path, [f"{bad},1.1,1.2,1.0,1.1,1"])
    with pytest.raises(ValueError):
        read_dukascopy_csv(path)


def test_read_dukascopy_rejects_unexpected_columns(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("Time,Open,High,Low,Close\n2025-03-19T00:00:00+00:00,1,1,1,1", encoding="ascii")
    with pytest.raises(ValueError):
        read_dukascopy_csv(path)


def test_label_minutes_naive_and_aware_agree_on_same_wall_clock():
    naive = pd.Series(pd.to_datetime(["2025-03-19 13:00"]))
    aware = pd.Series(pd.to_datetime(["2025-03-19 13:00"]).tz_localize("UTC"))
    assert label_minutes(naive)[0] == label_minutes(aware)[0]


def test_minute_returns_skip_gaps_and_duplicates():
    df = pd.DataFrame({"t": pd.to_datetime(["2025-01-01 00:00", "2025-01-01 00:01", "2025-01-01 00:03",
                                            "2025-01-01 00:04", "2025-01-01 00:05", "2025-01-01 00:05"]),
                       "close": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5]})
    r = minute_returns(df, "t")
    # 00:01 (consecutive), 00:04 (consecutive after the gap); 00:05 duplicated -> excluded
    assert len(r) == 2
    assert r.iloc[0] == pytest.approx(np.log(1.1))


def make_series(seed: int, n: int = 2000):
    rng = np.random.default_rng(seed)
    return np.exp(np.cumsum(rng.normal(0, 1e-4, n))) * 1.1


def test_offset_scan_finds_known_shift():
    n = 1500
    closes = make_series(1, n)
    ref_t = pd.date_range("2025-03-19 00:00", periods=n, freq="1min", tz="UTC")
    hist_t = pd.date_range("2025-03-18 19:00", periods=n, freq="1min")  # label = UTC - 300 min
    ref = pd.DataFrame({"t": ref_t, "close": closes})
    hist = pd.DataFrame({"t": hist_t, "close": closes + np.random.default_rng(2).normal(0, 2e-6, n)})
    scan = offset_scan(minute_returns(hist, "t"), minute_returns(ref, "t"), range(-400, 401))
    peak = assess_peak(scan)
    assert peak["best_offset_minutes"] == 300
    assert peak["decisive_day"]


def test_assess_peak_not_decisive_for_noise():
    rng = np.random.default_rng(5)
    scan = pd.DataFrame({"offset_minutes": range(-50, 51), "shared_minutes": 1000,
                         "pearson": rng.normal(0, 0.03, 101), "spearman": rng.normal(0, 0.03, 101)})
    assert not assess_peak(scan)["decisive_day"]


def test_hypothesis_offsets_for_us_only_dst_window():
    pred = hypothesis_offsets(pd.Timestamp("2025-03-19", tz="UTC")).set_index("hypothesis")
    assert pred.loc["H1_fixed_utc-5", "predicted_offset_minutes"] == 300
    assert pred.loc["H2_america_new_york", "predicted_offset_minutes"] == 240
    assert pred.loc["H3_ny_offset_eu_dates", "predicted_offset_minutes"] == 300


def test_rollover_minutes_in_edt():
    minutes = rollover_minutes_utc(pd.Timestamp("2025-03-19", tz="UTC"))
    first = label_minutes(pd.Series(pd.to_datetime(["2025-03-19 20:55"])))[0]
    assert min(minutes) == first and len(minutes) == 21


def test_join_at_offset_and_price_summary(tmp_path):
    hist_path = tmp_path / "DAT_ASCII_EURUSD_M1_2025.csv"
    hist_path.write_text("20250319 080000;2.100000;2.100100;2.099900;2.100050;0\n"
                         "20250319 080100;2.100050;2.100200;2.100000;2.100100;0\n", encoding="ascii")
    ref_path = write_dukascopy(tmp_path, ["2025-03-19T13:00:00+00:00,2.10000,2.10010,2.09990,2.10006,5",
                                          "2025-03-19T13:02:00+00:00,2.10010,2.10020,2.10000,2.10010,5"])
    joined = join_at_offset(load_raw([hist_path]), read_dukascopy_csv(ref_path), 300)
    # sorted by reference time; HistData-only rows (no reference time) last
    assert joined["present_in"].tolist() == ["both", "reference_only", "histdata_only"]
    assert joined.loc[0, "close_diff_pips"] == pytest.approx(-0.1)
    assert joined.loc[0, "histdata_line_number"] == 1 and joined.loc[0, "reference_line_number"] == 2
    summary = price_summary(joined).set_index("field")
    assert summary.loc["open", "share_exact"] == 1.0


def test_missing_minutes():
    df = pd.DataFrame({"t": pd.to_datetime(["2025-03-19 00:00", "2025-03-19 00:02"])})
    gone = missing_minutes(df, "t", pd.Timestamp("2025-03-19 00:00"), pd.Timestamp("2025-03-19 00:03"))
    assert gone["missing_minute_label"].tolist() == ["2025-03-19 00:01:00"]


def test_interpretation_flags_shared_upstream_and_event_match():
    from src.data.reference_compare import interpretation
    r = {
        "utc_day": "2025-03-19",
        "peak": {"best_offset_minutes": 300, "best_correlation": 1.0, "peak_ratio": 11.1, "decisive_day": True},
        "predictions": pd.DataFrame({"hypothesis": ["H1", "H2"], "matches_best_offset": [True, False]}),
        "top_ref": pd.DataFrame({"minute_label": ["2025-03-19 18:00:00"]}),
        "top_hist": pd.DataFrame({"minute_label": ["2025-03-19 13:00:00"]}),
        "best_summary": pd.DataFrame({"share_exact": [1.0, 1.0, 1.0, 1.0]}),
    }
    text = interpretation(r)
    assert "Consistent with H1; inconsistent with H2" in text
    assert "(match)" in text
    assert "not independent-vendor evidence" in text

    r["best_summary"] = pd.DataFrame({"share_exact": [0.4, 0.5, 0.4, 0.4]})
    r["top_ref"] = pd.DataFrame({"minute_label": ["2025-03-19 17:00:00"]})
    text = interpretation(r)
    assert "NO match" in text and "not independent-vendor evidence" not in text
