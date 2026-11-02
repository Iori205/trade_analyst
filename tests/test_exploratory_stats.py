"""Tests for the exploratory statistics helpers. Synthetic fixtures only (prices in the 2.x range)."""

import numpy as np
import pandas as pd
import pytest

from src.research.exploratory_stats import (
    bh_qvalues, clean_bars, cluster_mean_test, fix_window_returns, forward_returns, lag_pairs, last_weekday_of_month,
    load_train, mean_test, perm_mean_diff, robust_corr, session_of, session_returns, sign_test, signflip_mean,
)
from src.data.splits import load_splits


def bars(starts, opens, closes, flags=None):
    n = len(starts)
    flags = flags or [False] * n
    return pd.DataFrame({"bar_start_utc": pd.DatetimeIndex(starts, tz="UTC"), "open": opens, "high": np.maximum(opens, closes),
                         "low": np.minimum(opens, closes), "close": closes, "any_gap": [False] * n, "any_flag": flags})


def test_bh_matches_hand_computation():
    q = bh_qvalues([0.01, 0.04, 0.03, 0.20, np.nan])
    assert np.allclose(q[:4], [0.04, 0.0533333, 0.0533333, 0.2])
    assert np.isnan(q[4])
    assert (bh_qvalues([0.001] * 3) == 0.001).all()


def test_basic_tests():
    assert mean_test([1.0, -1.0, 1.0, -1.0])["estimate"] == 0
    s = sign_test([1, 1, 1, -1, 0])
    assert (s["n"], s["estimate"]) == (4, 0.75)
    rng = np.random.default_rng(0)
    x = rng.normal(size=5000)
    assert robust_corr(x, x)["estimate"] == pytest.approx(1.0)
    assert robust_corr(x, rng.normal(size=5000))["p"] > 0.001
    c = cluster_mean_test([1.0, 1.0, 1.0, -1.0], ["a", "a", "a", "b"])
    assert c["clusters"] == 2 and c["estimate"] == 0.5


def test_permutation_tests_are_seeded():
    a, b = np.arange(10.0), np.arange(10.0) + 5
    r1 = perm_mean_diff(a, b, np.random.default_rng(1), 500)
    r2 = perm_mean_diff(a, b, np.random.default_rng(1), 500)
    assert r1 == r2 and r1["estimate"] == -5 and r1["p"] < 0.05
    assert signflip_mean(np.ones(12), np.random.default_rng(2), 2000)["p"] < 0.01


def test_clean_bars_drops_flags_and_computes_pips():
    b = clean_bars(bars(["2019-01-02 10:00", "2019-01-02 11:00"], [2.0, 2.0], [2.0012, 1.9990], [False, True]))
    assert len(b) == 1 and b["ret"].iloc[0] == pytest.approx(12.0)


def test_lag_pairs_need_exact_spacing():
    b = clean_bars(bars(["2019-01-02 10:00", "2019-01-02 11:00", "2019-01-02 13:00"], [2.0] * 3, [2.001, 2.002, 2.003]))
    p1 = lag_pairs(b, 1, 60)
    assert len(p1) == 1 and (p1["x"].iloc[0], p1["y"].iloc[0]) == pytest.approx((10.0, 20.0))  # 11:00 after 10:00 only
    assert len(lag_pairs(b, 2, 60)) == 1   # 13:00 after 11:00
    assert len(lag_pairs(b, 3, 60)) == 1   # 13:00 after 10:00


def test_forward_returns_use_exact_target_bar():
    b = clean_bars(bars(["2019-01-02 10:00", "2019-01-02 11:00", "2019-01-02 14:00"], [2.0] * 3, [2.0010, 2.0030, 2.0005]))
    f1, f4 = forward_returns(b, 1, 60), forward_returns(b, 4, 60)
    assert f1.iloc[0] == pytest.approx(20.0) and np.isnan(f1.iloc[1])
    assert f4.iloc[0] == pytest.approx(-5.0) and f4.iloc[1:].isna().all()   # 10:00 -> 14:00 exists, 11:00 -> 15:00 not
    assert forward_returns(b, 3, 60).iloc[1] == pytest.approx(-25.0)


def test_sessions():
    assert session_of([0, 6, 7, 11, 12, 20, 21, 23]).tolist() == ["asia", "asia", "london", "london", "ny", "ny", "other", "other"]
    starts = [f"2019-01-02 {h:02d}:00" for h in range(0, 12)]
    b = clean_bars(bars(starts, [2.0 + 0.0001 * h for h in range(12)], [2.0 + 0.0001 * (h + 1) for h in range(12)]))
    s = session_returns(b)
    assert s.loc[pd.Timestamp("2019-01-02", tz="UTC"), "asia"] == pytest.approx(7.0)
    assert s.loc[pd.Timestamp("2019-01-02", tz="UTC"), "london"] == pytest.approx(5.0)
    assert np.isnan(s.loc[pd.Timestamp("2019-01-02", tz="UTC"), "ny"])     # incomplete session is not used
    s2 = session_returns(b[b["bar_start_utc"].dt.hour != 3])
    assert np.isnan(s2.iloc[0]["asia"])


def test_last_weekday_of_month():
    d = pd.DatetimeIndex(["2021-07-30", "2021-07-29", "2021-10-29", "2021-10-31", "2021-12-31", "2019-08-30"])
    assert last_weekday_of_month(d).tolist() == [True, False, True, False, True, True]


def test_fix_window_follows_london_dst():
    # 2021-07-30 (BST): 15:00-17:00 London = 14:00-16:00 UTC; 2021-01-29 (GMT): 15:00-17:00 UTC
    starts, opens, closes = [], [], []
    for day, first in (("2021-07-30", 14), ("2021-01-29", 15)):
        for i in range(8):
            t = pd.Timestamp(f"{day} {first:02d}:00") + pd.Timedelta(minutes=15 * i)
            starts.append(str(t)); opens.append(2.0); closes.append(2.0 + (0.0008 if i == 7 else 0.0))
    m15 = clean_bars(bars(starts, opens, closes))
    fx = fix_window_returns(m15, pd.Timestamp("2021-01-01", tz="UTC"), pd.Timestamp("2022-01-01", tz="UTC"))
    assert fx["window_start_utc"].dt.hour.tolist() == [15, 14]
    assert fx["ret"].tolist() == pytest.approx([8.0, 8.0]) and fx["month_end"].all()


def test_load_train_only_reads_train(tmp_path):
    p = tmp_path / "splits.yaml"
    p.write_text('splits:\n  train: {start: "2019-01-01", end: "2019-12-31"}\n'
                 '  validation: {start: "2020-01-01", end: "2020-12-31"}\n'
                 '  test: {start: "2021-01-01", end: "2021-12-31", locked: true}\n', encoding="utf-8")
    splits = load_splits(p)
    good = bars(["2019-05-01 10:00"], [2.0], [2.001])
    good.to_parquet(tmp_path / "eurusd_h1_train.parquet", index=False)
    b, n = load_train(tmp_path, "H1", splits)
    assert n == 1 and len(b) == 1
    bars(["2020-05-01 10:00"], [2.0], [2.001]).to_parquet(tmp_path / "eurusd_m15_train.parquet", index=False)
    with pytest.raises(AssertionError):
        load_train(tmp_path, "M15", splits)   # a non-train bar in the train file is refused
