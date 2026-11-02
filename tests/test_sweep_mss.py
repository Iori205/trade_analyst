"""Tests for the Sweep + MSS strategy. Synthetic M15 bars (prices in the 2.x range), stub cost model."""

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import backtest, prepare
from src.strategies.sweep_mss import last_fractal, random_matched_strategy, sweep_mss_strategy
from tests.test_backtest_engine import StubCost

P = 2.1000
DAY = "2019-01-15"          # a Tuesday, after ~14 days of warm-up


def bar(t, o, h, l, c):
    return {"bar_start_utc": pd.Timestamp(t), "open": o, "high": h, "low": l, "close": c}


def scenario(trend=+1, extra=None, mss_offset=2, sweep_time="13:00"):
    """Warm-up trend from 2019-01-01, then DAY with Asia range P +/- 10 pips, a fractal swing, a sweep and an MSS."""
    rows = []
    warm = pd.date_range("2019-01-01", f"{DAY} 00:00", freq="15min", tz="UTC", inclusive="left")
    start = P - trend * 0.0001 * len(warm) * 0.05
    for k, t in enumerate(warm):
        c = start + trend * 0.0001 * 0.05 * (k + 1)
        o = c - trend * 0.000005
        rows.append(bar(t, o, max(o, c) + 0.00002, min(o, c) - 0.00002, c))
    day = pd.date_range(f"{DAY} 00:00", periods=96, freq="15min", tz="UTC")
    for t in day:
        rows.append(bar(t, P, P + 0.00002, P - 0.00002, P))
    df = pd.DataFrame(rows).set_index("bar_start_utc")

    def put(hhmm, o, h, l, c):
        df.loc[pd.Timestamp(f"{DAY} {hhmm}", tz="UTC"), ["open", "high", "low", "close"]] = [o, h, l, c]
    put("03:00", P, P + 0.0010, P, P)                  # Asia high
    put("04:00", P, P, P - 0.0010, P)                  # Asia low
    s = 1 if trend > 0 else -1
    put("12:15", P, P + s * 0.0005 if s > 0 else P + 0.00002, P if s > 0 else P - 0.0005, P)   # swing high / low
    sw = pd.Timestamp(f"{DAY} {sweep_time}", tz="UTC")
    if s > 0:
        df.loc[sw, ["open", "high", "low", "close"]] = [P, P, P - 0.0015, P - 0.0005]
    else:
        df.loc[sw, ["open", "high", "low", "close"]] = [P, P + 0.0015, P, P + 0.0005]
    mss = sw + pd.Timedelta(minutes=15 * mss_offset)
    df.loc[mss, ["open", "high", "low", "close"]] = ([P, P + 0.0009, P, P + 0.0008] if s > 0
                                                     else [P, P, P - 0.0009, P - 0.0008])
    for hhmm, vals in (extra or {}).items():
        put(hhmm, *vals)
    df = df.reset_index()
    df["any_gap"], df["any_flag"] = False, False
    return df


def run(df):
    strat, sig = sweep_mss_strategy()
    return backtest(prepare(df, StubCost()), strat, "M15"), sig


def test_last_fractal():
    v = np.array([1, 2, 5, 3, 2, 4, 9, 8, 7, 1.0])
    assert last_fractal(v, 7, high=True) == 9 and last_fractal(v, 5, high=True) == 5
    assert last_fractal(v, 1, high=True) is None
    assert last_fractal(-v, 7, high=False) == -9


def test_long_trade_after_sweep_and_mss():
    trades, sig = run(scenario(+1))
    assert len(trades) == 1 and trades["direction"].iloc[0] == "long"
    assert str(trades["entry_time"].iloc[0])[:16] == f"{DAY} 13:45"   # MSS bar 13:30 -> next open
    assert str(trades["exit_time"].iloc[0])[:16] == f"{DAY} 17:45"    # 4 hours
    assert sig.counters["sweeps"] == 1 and sig.counters["mss"] == 1


def test_short_mirror_and_trend_gate():
    trades, _ = run(scenario(-1))
    assert trades["direction"].tolist() == ["short"]
    # long pattern in a down-trend: no trade (the trend allows shorts only, and there is no high sweep)
    df = scenario(-1)
    df_long = scenario(+1)
    mask = df_long["bar_start_utc"] >= pd.Timestamp(DAY, tz="UTC")
    df.loc[mask.to_numpy(), ["open", "high", "low", "close"]] = df_long.loc[mask, ["open", "high", "low", "close"]].to_numpy()
    assert run(df)[0].empty


def test_exit_at_2045_when_earlier_than_4h():
    trades, _ = run(scenario(+1, sweep_time="16:45"))
    assert str(trades["entry_time"].iloc[0])[11:16] == "17:30" and str(trades["exit_time"].iloc[0])[11:16] == "20:45"


def test_mss_must_come_within_8_bars():
    assert len(run(scenario(+1, mss_offset=8))[0]) == 1
    assert run(scenario(+1, mss_offset=9))[0].empty


def test_sweep_outside_window_is_ignored():
    assert run(scenario(+1, sweep_time="17:00"))[0].empty
    assert run(scenario(+1, sweep_time="11:45"))[0].empty


def test_one_trade_per_day():
    second = {"18:00": (P, P, P - 0.0016, P - 0.0004), "18:30": (P, P + 0.0012, P, P + 0.0011)}
    trades, sig = run(scenario(+1, extra=second))
    assert len(trades) == 1 and sig.counters["signals"] == 1


def test_future_bars_do_not_change_the_signal():
    df = scenario(+1)
    cut = pd.Timestamp(f"{DAY} 13:45", tz="UTC")
    changed = df.copy()
    later = changed["bar_start_utc"] > cut
    changed.loc[later, ["open", "high", "low", "close"]] = changed.loc[later, ["open", "high", "low", "close"]] - 0.01
    a, b = run(df)[0], run(changed)[0]
    assert a["entry_time"].tolist() == b["entry_time"].tolist() and a["entry_price"].tolist() == b["entry_price"].tolist()
    truncated = run(df[df["bar_start_utc"] <= cut])[0]                # data ends at the entry bar
    assert truncated["entry_time"].tolist() == a["entry_time"].tolist()


def test_random_matched_is_reproducible_and_one_per_day():
    df = scenario(+1)
    data = prepare(df, StubCost())
    a = backtest(data, random_matched_strategy(5, 0.5, False), "M15")
    b = backtest(data, random_matched_strategy(5, 0.5, False), "M15")
    pd.testing.assert_frame_equal(a, b)
    assert a["entry_time"].dt.date.value_counts().max() == 1
    hours = a["entry_time"].dt.hour * 60 + a["entry_time"].dt.minute
    assert ((hours >= 12 * 60 + 15) & (hours <= 19 * 60)).all()
    trend = backtest(data, random_matched_strategy(5, 0.5, True), "M15")
    assert (trend["direction"] == "long").all()
