"""Tests for CRT v1. Synthetic data only (prices in the 2.x range); stub cost model."""

import numpy as np
import pandas as pd
import pytest

from src.strategies.crt import (
    NS_MIN, candidates, control, find_setups, h4_blocks, levels, path_outcome, simulate,
)
from tests.test_backtest_engine import StubCost

P = 2.1


def m15_from_blocks(day="2019-01-08", blocks=None):
    """M15 bars for consecutive H4 blocks of `day`; blocks = list of (open, high, low, close) per block."""
    rows = []
    for b, (o, h, l, c) in enumerate(blocks):
        start = pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=4 * b)
        for k in range(16):
            t = start + pd.Timedelta(minutes=15 * k)
            bo = o if k == 0 else c
            hi = h if k == 5 else max(bo, c)
            lo = l if k == 9 else min(bo, c)
            rows.append({"bar_start_utc": t, "open": bo, "high": hi, "low": lo, "close": c, "any_gap": False, "any_flag": False})
    return pd.DataFrame(rows)


def m1_flat(start, minutes, price):
    t = pd.date_range(start, periods=minutes, freq="min", tz="UTC")
    return pd.DataFrame({"t": t.astype("int64"), "h": price + 0.00001, "l": price - 0.00001, "c": price})


def as_m1(df):
    return {k: df[k].to_numpy() for k in ("t", "h", "l", "c")}


def test_h4_blocks_and_setups():
    m15 = m15_from_blocks(blocks=[(P, P + 0.0020, P - 0.0020, P),            # C1: range 2.0980-2.1020
                                  (P, P + 0.0030, P - 0.0010, P + 0.0005),   # C2: sweeps high, closes inside -> short
                                  (P + 0.0005, P + 0.0006, P + 0.0004, P + 0.0005),
                                  (P, P + 0.0040, P - 0.0040, P + 0.0005),   # C4 vs C3: both sides swept, close inside -> skip
                                  (P, P + 0.0001, P - 0.0050, P - 0.0001)])  # C5 vs C4: low swept, close inside -> long
    h4 = h4_blocks(m15)
    assert len(h4) == 5 and h4["high"].iloc[0] == pytest.approx(P + 0.0020) and (h4["bars"] == 16).all()
    s = find_setups(h4)
    assert s["direction"].tolist() == [-1, 0, 0, 1]
    assert s["both_swept"].tolist() == [False, False, True, False]
    assert s["c3_start"].iloc[0] == pd.Timestamp("2019-01-08 08:00", tz="UTC")


def test_non_consecutive_blocks_are_not_paired():
    m15 = m15_from_blocks(blocks=[(P, P + 0.002, P - 0.002, P), (P, P + 0.003, P - 0.001, P + 0.0005)])
    m15 = m15[m15["bar_start_utc"] < pd.Timestamp("2019-01-08 04:00", tz="UTC")]
    later = m15_from_blocks(day="2019-01-08 12:00", blocks=[(P, P + 0.003, P - 0.001, P + 0.0005)])
    assert find_setups(h4_blocks(pd.concat([m15, later])))["direction"].abs().sum() == 0


def test_levels():
    c = pd.DataFrame({"direction": [-1, 1], "high1": [2.12, 2.12], "low1": [2.10, 2.10], "high2": [2.13, 2.115],
                      "low2": [2.105, 2.09]})
    tp_a, sl = levels(c, "v1a")
    tp_b, _ = levels(c, "v1b")
    assert tp_a.tolist() == pytest.approx([2.11, 2.11]) and tp_b.tolist() == pytest.approx([2.10, 2.12])
    assert sl.tolist() == pytest.approx([2.13, 2.09])


def test_path_outcomes():
    t0 = pd.Timestamp("2019-01-08 08:00", tz="UTC")
    end = int(pd.Timestamp("2022-01-01", tz="UTC").value)
    df = m1_flat(t0, 13 * 60, P)
    df.loc[100, "l"] = P - 0.0021                                     # short TP at P-0.0020
    o, r, x = path_outcome(as_m1(df), t0.value, P, -1, P - 0.0020, P + 0.0030, end)
    assert o == "tp" and r == pytest.approx(20.0) and x == int(df["t"][100]) + NS_MIN
    df.loc[50, "h"] = P + 0.0031                                      # SL earlier
    assert path_outcome(as_m1(df), t0.value, P, -1, P - 0.0020, P + 0.0030, end)[:2] == ("sl", pytest.approx(-30.0))
    df2 = m1_flat(t0, 13 * 60, P)
    df2.loc[10, ["h", "l"]] = [P + 0.005, P - 0.005]                  # both in one minute -> SL
    assert path_outcome(as_m1(df2), t0.value, P, 1, P + 0.002, P - 0.002, end)[0] == "sl"
    df3 = m1_flat(t0, 13 * 60, P)
    df3.loc[12 * 60 - 1, "c"] = P + 0.0004
    o, r, x = path_outcome(as_m1(df3), t0.value, P, 1, P + 0.002, P - 0.002, end)
    assert o == "time" and r == pytest.approx(4.0) and x == (t0 + pd.Timedelta(hours=12)).value


def test_gap_exit_and_weekend():
    t0 = pd.Timestamp("2019-01-11 16:00", tz="UTC")                   # Friday; data stops at 22:00
    df = m1_flat(t0, 6 * 60, P)
    df.loc[len(df) - 1, "c"] = P - 0.0003
    o, r, x = path_outcome(as_m1(df), t0.value, P, 1, P + 0.002, P - 0.002, int(pd.Timestamp("2022-01-01", tz="UTC").value))
    assert o == "gap_exit" and r == pytest.approx(-3.0) and x == int(df["t"].iloc[-1]) + NS_MIN
    gap = m1_flat(t0, 12 * 60, P).drop(index=range(100, 200)).reset_index(drop=True)
    assert path_outcome(as_m1(gap), t0.value, P, 1, P + 0.002, P - 0.002, int(pd.Timestamp("2022-01-01", tz="UTC").value))[0] == "gap_exit"


def setup_frame(entry_price=P + 0.0005):
    return pd.DataFrame({"c3_start": [pd.Timestamp("2019-01-08 08:00", tz="UTC")], "direction": [-1],
                         "high1": [P + 0.002], "low1": [P - 0.002], "high2": [P + 0.003], "low2": [P - 0.001],
                         "entry_price": [entry_price], "entry_clean": [True], "blocked": [False], "cost_pips": [1.0]})


def test_simulate_geometry_and_flip():
    t0 = pd.Timestamp("2019-01-08 08:00", tz="UTC")
    end = int(pd.Timestamp("2022-01-01", tz="UTC").value)
    df = m1_flat(t0, 13 * 60, P + 0.0005)
    df.loc[30, "l"] = P - 0.0001                                      # short v1a TP (mid = P) hit
    sim = simulate(setup_frame(), as_m1(df), "v1a", end)
    t = sim["trades"].iloc[0]
    assert t["outcome"] == "tp" and t["gross_pips"] == pytest.approx(5.0) and t["net_pips"] == pytest.approx(4.0)
    assert t["tp_dist_pips"] == pytest.approx(5.0) and t["sl_dist_pips"] == pytest.approx(25.0)
    # flipped = long with TP +5 pips, SL -25 pips: the low at minute 30 is -6 pips, so it runs to the time exit at 0
    assert t["flipped_net_pips"] == pytest.approx(-1.0)
    below_mid = simulate(setup_frame(entry_price=P - 0.0005), as_m1(df), "v1a", end)
    assert below_mid["trades"].empty and below_mid["counts"]["bad_geometry"] == 1


def test_candidates_entry_checks():
    m15 = m15_from_blocks(blocks=[(P, P + 0.002, P - 0.002, P), (P, P + 0.003, P - 0.001, P + 0.0005),
                                  (P + 0.0005, P + 0.0006, P + 0.0004, P + 0.0005)])
    s = find_setups(h4_blocks(m15))
    c = candidates(s, m15, StubCost(), "p75")
    assert len(c) == 1 and c["entry_clean"].iloc[0] and c["entry_price"].iloc[0] == pytest.approx(P + 0.0005)
    m15.loc[m15["bar_start_utc"] == pd.Timestamp("2019-01-08 08:00", tz="UTC"), "any_flag"] = True
    assert not candidates(s, m15, StubCost(), "p75")["entry_clean"].iloc[0]


def test_one_position_at_a_time_and_control():
    t0 = pd.Timestamp("2019-01-08 08:00", tz="UTC")
    end = int(pd.Timestamp("2022-01-01", tz="UTC").value)
    two = pd.concat([setup_frame(), setup_frame().assign(c3_start=t0 + pd.Timedelta(hours=4))], ignore_index=True)
    sim = simulate(two, as_m1(m1_flat(t0, 20 * 60, P + 0.0005)), "v1a", end)
    assert len(sim["trades"]) == 1                                     # the first trade runs 12 h, so the second is skipped
    tr = pd.DataFrame({"net_pips": [2.0] * 50, "flipped_net_pips": [-4.0] * 50})
    c = control(tr, runs=200, seed=1)
    assert len(c) == 200 and c.min() >= -4 and c.max() <= 2 and abs(c.mean() + 1) < 0.2
    assert (control(tr, runs=200, seed=1) == c).all()
