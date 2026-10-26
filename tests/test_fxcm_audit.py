"""Tests for the FXCM audit helpers. Synthetic fixtures only."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data.fxcm_audit import (
    FXCM_COLUMNS,
    bid_ask_checks,
    compare_with_histdata,
    date_order_evidence,
    event_activity,
    ordering_and_duplicates,
    price_jumps,
    read_fxcm_csv,
    read_fxcm_text,
    schema_report,
    spread_anomalies,
)
from src.data.inventory import sha256_file

HEADER = ",".join(FXCM_COLUMNS)


def fxcm_line(ts: str, bid=(2.1, 2.1002, 2.0999, 2.1001), spread=0.0002) -> str:
    ask = tuple(round(b + spread, 5) for b in bid)
    return ",".join([ts, *(f"{v:.5f}".rstrip("0") for v in bid), *(f"{v:.5f}".rstrip("0") for v in ask)])


def write_fxcm(directory: Path, lines: list[str], name: str = "53.csv") -> Path:
    path = directory / name
    path.write_text("\n".join([HEADER, *lines]) + "\n", encoding="ascii")
    return path


def test_read_fxcm_strict_naive_and_untouched(tmp_path):
    path = write_fxcm(tmp_path, [fxcm_line("12/29/2019 22:03:00.000"), fxcm_line("12/29/2019 22:04:00.000")])
    before = sha256_file(path)
    df = read_fxcm_csv(path)
    assert df["timestamp_label"].dt.tz is None
    assert df["timestamp_label"].iloc[0] == pd.Timestamp("2019-12-29 22:03")
    assert df["timestamp_text"].iloc[0] == "12/29/2019 22:03:00.000"
    assert df["ask_close"].iloc[0] == pytest.approx(2.1003)
    assert sha256_file(path) == before


@pytest.mark.parametrize("bad", ["2019-12-29 22:03:00", "12/29/2019 22:03:00", "12/29/2019 22:03:00.000Z"])
def test_read_fxcm_rejects_bad_timestamps(tmp_path, bad):
    with pytest.raises(ValueError):
        read_fxcm_csv(write_fxcm(tmp_path, [fxcm_line(bad)]))


def test_read_fxcm_rejects_unexpected_header(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("DateTime,Open,High,Low,Close\n12/29/2019 22:03:00.000,1,1,1,1\n", encoding="ascii")
    with pytest.raises(ValueError):
        read_fxcm_text(path)


def test_date_order_evidence():
    assert date_order_evidence(pd.Series(["12/29/2019 22:03:00.000"]))["verdict"].startswith("MM/DD")
    assert date_order_evidence(pd.Series(["29/12/2019 22:03:00.000"]))["verdict"].startswith("DD/MM")
    assert date_order_evidence(pd.Series(["01/02/2020 00:00:00.000"]))["verdict"] == "ambiguous"


def test_schema_report_counts_decimals_and_empties(tmp_path):
    path = write_fxcm(tmp_path, [fxcm_line("12/29/2019 22:03:00.000"),
                                 "12/29/2019 22:04:00.000,1.1,,1.1,1.1,1.1,1.1,1.1,1.1"])
    schema = schema_report(read_fxcm_text(path)).set_index("column")
    assert schema.loc["BidHigh", "empty_values"] == 1
    assert schema.loc["BidOpen", "max_decimals_written"] == 1


def test_ordering_and_duplicates():
    df = pd.DataFrame({"timestamp_label": pd.to_datetime(["2020-01-01 00:00", "2020-01-01 00:02",
                                                          "2020-01-01 00:01", "2020-01-01 00:02"])})
    o = ordering_and_duplicates(df)
    assert not o["monotonic_increasing"]
    assert o["rows_not_after_previous"] == 1  # only 00:01 follows a later row
    assert o["duplicate_timestamps"] == 1 and o["duplicate_timestamp_rows"] == 2


def test_bid_ask_checks_and_spread_anomalies(tmp_path):
    path = write_fxcm(tmp_path, [
        fxcm_line("12/30/2019 10:00:00.000"),
        fxcm_line("12/30/2019 10:01:00.000", spread=-0.0001),   # negative spread
        fxcm_line("12/30/2019 10:02:00.000", spread=0.0008),    # 8-pip spread
    ])
    df = read_fxcm_csv(path)
    checks = bid_ask_checks(df).set_index("field")
    assert checks.loc["close", "ask_below_bid"] == 1
    anomalies = spread_anomalies(df, alert_pips=5)
    assert anomalies["line_number"].tolist() == [3, 4]


def test_price_jumps(tmp_path):
    path = write_fxcm(tmp_path, [fxcm_line("12/30/2019 10:00:00.000", bid=(2.1, 2.1, 2.1, 2.1)),
                                 fxcm_line("12/30/2019 10:01:00.000", bid=(2.103, 2.103, 2.103, 2.103))])
    jumps = price_jumps(read_fxcm_csv(path), alert_pips=20)
    assert jumps["line_number"].tolist() == [3]
    assert jumps["bid_close_move_pips"].iloc[0] == pytest.approx(30.0)


def test_event_activity_detects_spike(tmp_path):
    times = pd.date_range("2020-01-03 18:50", periods=20, freq="1min")
    closes = np.full(20, 1.11)
    closes[10:] += 0.002  # jump at 19:00
    lines = [fxcm_line(t.strftime("%m/%d/%Y %H:%M:%S.000"), bid=(c, c, c, c)) for t, c in zip(times, closes)]
    df = read_fxcm_csv(write_fxcm(tmp_path, lines))
    out = event_activity(df, [{"event": "x", "utc": "2020-01-03 19:00", "basis": "test"}], alternatives=(-5, 0, 5))
    assert out["max_bp_at_+0min"].iloc[0] > 10
    assert out["max_bp_at_-5min"].iloc[0] == 0
    assert out["strongest_shift_min"].iloc[0] == 0


def test_compare_with_histdata_finds_offset(tmp_path):
    n = 1200
    rng = np.random.default_rng(3)
    closes = np.round(1.11 * np.exp(np.cumsum(rng.normal(0, 1e-4, n))), 5)
    hist_t = pd.date_range("2019-12-30 00:00", periods=n, freq="1min")
    raw_dir = tmp_path / "data" / "HISTDATA_COM_ASCII_EURUSD_M12019"
    raw_dir.mkdir(parents=True)
    (raw_dir / "DAT_ASCII_EURUSD_M1_2019.csv").write_text(
        "\n".join(f"{t:%Y%m%d %H%M%S};{c:.6f};{c:.6f};{c:.6f};{c:.6f};0" for t, c in zip(hist_t, closes)) + "\n",
        encoding="ascii")
    fx_t = hist_t + pd.Timedelta(minutes=300)
    noisy = closes + rng.normal(0, 3e-6, n)
    fxcm = read_fxcm_csv(write_fxcm(tmp_path, [fxcm_line(t.strftime("%m/%d/%Y %H:%M:%S.000"), bid=(c, c, c, c))
                                               for t, c in zip(fx_t, noisy)]))
    result = compare_with_histdata(fxcm, tmp_path / "data", "**/DAT_ASCII_EURUSD_M1_*.csv", max_offset=400)
    assert result["available"]
    assert result["peak"]["best_offset_minutes"] == 300
    assert result["peak"]["decisive_day"]
    assert result["best_presence"].get("both", 0) > 1000
