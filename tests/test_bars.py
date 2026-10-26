"""Tests for splits, the test-set guard and M15/H1 bar construction. Synthetic fixtures only."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.data.bars import BAR_FLAGS, aggregate, bar_file, read_bars, run
from src.data.inventory import sha256_file
from src.data.splits import TestSetLockedError, guard_range, load_splits, read_m1_split

SPLITS_YAML = """
version: test
splits:
  train: {start: "2019-01-01", end: "2019-12-31"}
  validation: {start: "2020-01-01", end: "2020-12-31", exclude_flags: [low_quality_period]}
  test: {start: "2021-01-01", end: "2021-12-31", locked: true}
"""


def m1_frame(rows):
    """rows: (utc minute, close, flags dict). Other prices equal close; bar fixtures stay OHLC-valid."""
    out = []
    for i, (ts, close, flags) in enumerate(rows):
        r = {"timestamp_utc": pd.Timestamp(ts, tz="UTC"), "source_file": "f.csv", "source_line": i + 1,
             "open": close, "high": close + 0.0005, "low": close - 0.0005, "close": close, "volume": 0,
             "utc_unresolved": False, **{f: False for f in BAR_FLAGS}}
        r.update(flags)
        out.append(r)
    return pd.DataFrame(out)


@pytest.fixture
def splits(tmp_path):
    p = tmp_path / "splits.yaml"
    p.write_text(SPLITS_YAML, encoding="utf-8")
    return load_splits(p)


def test_split_ranges_are_inclusive_days(splits):
    assert str(splits["train"].end) == "2020-01-01 00:00:00+00:00"
    assert splits["test"].locked and not splits["validation"].locked


def test_project_splits_config():
    s = load_splits(Path(__file__).resolve().parents[1] / "config" / "splits.yaml")
    assert [str(s[n].start.date()) for n in ("train", "validation", "test")] == ["2015-01-01", "2022-01-01", "2024-01-01"]
    assert str(s["test"].end) == "2026-09-01 00:00:00+00:00" and s["test"].locked
    assert s["validation"].exclude_flags == ("low_quality_period",)


def test_guard_blocks_locked_ranges(splits):
    guard_range(pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2021-01-01", tz="UTC"), splits)  # ends at test start
    for start, end in [("2020-06-01", "2021-01-02"), ("2021-05-01", "2021-05-02"), ("2021-12-31", "2023-01-01")]:
        with pytest.raises(TestSetLockedError):
            guard_range(pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC"), splits)
    with pytest.raises(TestSetLockedError):
        guard_range(None, None, splits)  # unbounded read
    with pytest.raises(TestSetLockedError):
        guard_range(None, None, splits, unlock_test="yes")  # only the literal True unlocks
    guard_range(None, None, splits, unlock_test=True)


def test_read_m1_split_guard_and_exclusion(tmp_path, splits):
    m1 = m1_frame([("2019-05-01 10:00", 1.1, {}), ("2020-05-01 10:00", 1.1, {"low_quality_period": True}),
                   ("2020-05-02 10:00", 1.1, {}), ("2021-05-01 10:00", 1.1, {})])
    path = tmp_path / "m1.parquet"
    m1.to_parquet(path, index=False)
    val, excluded = read_m1_split(path, "validation", splits)
    assert len(val) == 1 and excluded == 1
    with pytest.raises(TestSetLockedError):
        read_m1_split(path, "test", splits)
    test, _ = read_m1_split(path, "test", splits, unlock_test=True)
    assert len(test) == 1


def test_aggregate_ohlc_counts_and_no_filling():
    m1 = m1_frame([
        ("2019-05-01 10:00", 1.10, {}),
        ("2019-05-01 10:01", 1.12, {}),
        ("2019-05-01 10:14", 1.11, {"gap_before": True}),
        ("2019-05-01 10:15", 1.13, {}),
        # 10:16 .. 10:59 missing entirely; 11:00 .. 11:59 has no minute at all
        ("2019-05-01 12:30", 1.14, {}),
    ])
    m15 = aggregate(m1, 15)
    assert [str(t) for t in m15["bar_start_utc"]] == ["2019-05-01 10:00:00+00:00", "2019-05-01 10:15:00+00:00",
                                                      "2019-05-01 12:30:00+00:00"]
    first = m15.iloc[0]
    assert (first["open"], first["close"], first["m1_count"], first["expected_minutes"]) == (1.10, 1.11, 3, 15)
    assert first["high"] == pytest.approx(1.1205) and first["low"] == pytest.approx(1.0995)
    assert first["any_gap"] and first["gap_before"] and first["any_flag"]
    h1 = aggregate(m1, 60)
    assert h1["m1_count"].tolist() == [4, 1] and h1["expected_minutes"].tolist() == [60, 60]
    assert h1["m1_count"].sum() == len(m1)  # each real minute counted once, nothing invented


def test_aggregate_duplicates():
    m1 = m1_frame([
        ("2019-05-01 10:00", 1.10, {}),
        ("2019-05-01 10:01", 1.11, {"duplicate_identical": True}),
        ("2019-05-01 10:01", 1.11, {"duplicate_identical": True}),
        ("2019-05-01 10:15", 1.12, {"duplicate_conflict": True}),
        ("2019-05-01 10:15", 1.20, {"duplicate_conflict": True}),
    ])
    m15 = aggregate(m1.iloc[::-1], 15)  # input order must not matter
    assert m15["m1_count"].tolist() == [2, 1]
    assert m15["duplicate_identical"].tolist() == [True, False]
    conflict = m15.iloc[1]
    assert conflict["duplicate_conflict"] and conflict["any_flag"]
    assert conflict["close"] == 1.12  # first copy by source line, the other kept out but flagged


def write_input(root: Path, m1: pd.DataFrame) -> None:
    d = root / "data/processed/eurusd_m1/v1"
    d.mkdir(parents=True)
    m1.to_parquet(d / "eurusd_m1_utc.parquet", index=False)
    (d / "manifest.json").write_text(json.dumps({"policy": {"id": "C4", "version": "C4-v1"}}), encoding="utf-8")
    (d / "SHA256SUMS.txt").write_text(f"{sha256_file(d / 'eurusd_m1_utc.parquet')}  eurusd_m1_utc.parquet\n")
    (root / "config").mkdir()
    (root / "config/splits.yaml").write_text(SPLITS_YAML, encoding="utf-8")


def test_run_guard_determinism_and_no_overwrite(tmp_path):
    m1 = m1_frame([("2019-05-01 10:00", 1.1, {}), ("2019-05-01 10:01", 1.1, {}),
                   ("2020-05-01 10:00", 1.1, {"low_quality_period": True}), ("2020-06-01 10:00", 1.1, {}),
                   ("2021-05-01 10:00", 1.1, {}), ("2022-01-03 10:00", 1.1, {})])
    write_input(tmp_path, m1)
    src = tmp_path / "data/processed/eurusd_m1/v1/eurusd_m1_utc.parquet"
    before = sha256_file(src)
    with pytest.raises(TestSetLockedError):
        run(tmp_path, out_dir=Path("out/a"))
    assert not (tmp_path / "out/a").exists()
    a = run(tmp_path, out_dir=Path("out/a"), unlock_test=True)
    b = run(tmp_path, out_dir=Path("out/b"), unlock_test=True)
    ma, mb = a["manifest"], b["manifest"]
    assert {k: v["sha256"] for k, v in ma["outputs"].items()} == {k: v["sha256"] for k, v in mb["outputs"].items()}
    assert ma["input"]["sha256"] == before == sha256_file(src)
    assert ma["policy"]["id"] == "C4" and ma["test_unlocked"]["value"] is True
    assert ma["splits"]["validation"]["m1_rows_excluded_by_flags"] == 1
    assert ma["splits"]["m1_rows_outside_all_splits"] == 1
    assert ma["summary"]["H1/train"]["bars"] == 1 and ma["summary"]["M15/test"]["bars"] == 1
    splits = load_splits(tmp_path / "config/splits.yaml")
    with pytest.raises(TestSetLockedError):
        read_bars(a["out_dir"], "H1", "test", splits)
    assert len(read_bars(a["out_dir"], "H1", "train", splits)) == 1
    assert (a["out_dir"] / bar_file("M15", "validation")).exists()
    with pytest.raises(FileExistsError):
        run(tmp_path, out_dir=Path("out/a"), unlock_test=True)
