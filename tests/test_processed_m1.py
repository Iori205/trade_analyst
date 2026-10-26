"""Tests for the C4 processed dataset builder. Synthetic fixtures only."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.data.audit import load_raw
from src.data.inventory import sha256_file
from src.data.processed_m1 import build, labels_to_utc, run


def test_labels_to_utc_c4_examples():
    labels = pd.Series(pd.to_datetime([
        "2018-03-20 08:30",   # before boundary, US-only window: New York EDT -> 12:30 UTC
        "2018-07-10 08:30",   # before boundary, summer -> 12:30 UTC
        "2018-12-17 08:30",   # after boundary, winter -> 13:30 UTC (same under both rules)
        "2019-03-12 07:30",   # after boundary, US-only window: Zurich-6h (UTC-5) -> 12:30 UTC
        "2019-07-16 08:30",   # after boundary, summer: UTC-4 -> 12:30 UTC
    ]))
    utc, rule = labels_to_utc(labels)
    assert [str(u) for u in utc] == ["2018-03-20 12:30:00+00:00", "2018-07-10 12:30:00+00:00",
                                     "2018-12-17 13:30:00+00:00", "2019-03-12 12:30:00+00:00",
                                     "2019-07-16 12:30:00+00:00"]
    assert rule.tolist() == ["America/New_York"] * 2 + ["Europe/Zurich-6h"] * 3


def test_nonexistent_local_label_is_flagged_not_guessed():
    utc, _ = labels_to_utc(pd.Series(pd.to_datetime(["2018-03-11 02:30"])))  # New York spring-forward hole
    assert utc.isna().all()


def raw_frame(rows):
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.insert(0, "source_file", "DAT_ASCII_EURUSD_M1_2019.csv")
    df.insert(1, "source_row", range(len(df)))
    return df


def test_build_keeps_every_row_and_flags():
    raw = raw_frame([
        ("2019-03-10 16:00", 1.1, 1.1, 1.1, 1.1, 0),   # US-start Sunday open at the C4-predicted hour
        ("2019-03-10 16:01", 1.1, 1.1, 1.1, 1.1, 0),
        ("2019-03-10 16:04", 1.1, 1.1, 1.1, 1.1, 0),   # 2 missing minutes before
        ("2019-03-10 16:04", 1.1, 1.1, 1.1, 1.1, 0),   # identical duplicate
        ("2019-03-11 10:00", 1.2, 1.2, 1.2, 1.2, 0),
        ("2019-03-11 10:00", 1.3, 1.3, 1.3, 1.3, 0),   # conflicting duplicate
        ("2019-03-17 18:00", 1.1, 1.1, 1.1, 1.1, 0),   # late open (C4 predicts 16:00)
        ("2023-03-01 10:00", 1.1, 1.1, 1.1, 1.1, 0),   # low-quality period
    ])
    out, late = build(raw)
    assert len(out) == len(raw)
    assert out["source_line"].tolist() == [1, 2, 3, 4, 5, 6, 7, 8]
    assert out["source_timestamp_text"].iloc[0] == "20190310 160000"
    assert str(out["timestamp_utc"].iloc[0]) == "2019-03-10 21:00:00+00:00"
    assert out["gap_before_minutes"].tolist()[2] == 2 and out["gap_before"].tolist()[2]
    assert out["duplicate_identical"].tolist()[2:4] == [True, True]
    assert out["duplicate_conflict"].tolist()[4:6] == [True, True]
    assert late["sunday"].tolist() == ["2019-03-17"]
    assert out["suspect_late_open"].tolist() == [False] * 6 + [True, False]
    assert out["dst_transition_hour"].tolist()[:4] == [True] * 4 and not out["dst_transition_hour"].iloc[6]
    assert out["low_quality_period"].tolist() == [False] * 7 + [True]


def test_run_writes_new_version_and_never_overwrites(tmp_path):
    raw_dir = tmp_path / "data" / "HISTDATA_COM_ASCII_EURUSD_M12019"
    raw_dir.mkdir(parents=True)
    csv = raw_dir / "DAT_ASCII_EURUSD_M1_2019.csv"
    csv.write_text("20190311 100000;1.1;1.1;1.1;1.1;0\n20190311 100100;1.1;1.1;1.1;1.1;0\n", encoding="ascii")
    parquet = tmp_path / "legacy.parquet"
    parquet.write_bytes(b"legacy")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "timezone_decision.md").write_text("evidence", encoding="utf-8")
    for s in ["processed_m1.py", "fxcm_tz_compare.py", "audit.py", "investigate.py", "inventory.py"]:
        p = tmp_path / "src" / "data" / s
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# stub", encoding="utf-8")
    config = {"data": {"raw_dir": "data", "raw_csv_glob": "**/DAT_ASCII_EURUSD_M1_*.csv",
                       "parquet_files": {"1m": "legacy.parquet"}}}
    before = sha256_file(csv)
    r = run(tmp_path, config, Path("data/processed/eurusd_m1/v1"))
    m = json.loads((r["out_dir"] / "manifest.json").read_text())
    assert m["policy"]["id"] == "C4" and m["policy"]["era_boundary_label_date"] == "2018-12-16"
    assert m["output"]["rows"] == 2 and m["inputs"][0]["sha256"] == before and m["inputs"][0]["rows"] == 2
    assert m["git_commit"] is None and "not a git repository" in m["git_note"]
    assert sha256_file(csv) == before and parquet.read_bytes() == b"legacy"
    assert len(pd.read_parquet(r["out_dir"] / "eurusd_m1_utc.parquet")) == 2
    with pytest.raises(FileExistsError):
        run(tmp_path, config, Path("data/processed/eurusd_m1/v1"))
