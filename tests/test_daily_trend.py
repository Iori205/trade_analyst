"""Tests for daily trend v1. Synthetic data only (prices in the 2.x range)."""

import numpy as np
import pandas as pd
import pytest

from src.data.bars import BAR_FLAGS
from src.strategies.daily_trend import (
    SWAP_PIPS_PER_NIGHT, build_trades, daily_bars, direction_baseline, donchian_target, equity_by_day, ma_target,
    late_minutes, random_baseline, swap_units, trading_day,
)

PIP = 1e-4


def m1(stamps, price=2.1, **flags):
    t = pd.DatetimeIndex(stamps, tz="UTC")
    d = pd.DataFrame({"timestamp_utc": t, "open": price, "high": price, "low": price, "close": price})
    for f in BAR_FLAGS:
        d[f] = flags.get(f, False)
    return d


def bars(open_, high=None, low=None, close=None, start="2019-01-07"):
    """Daily bars on consecutive weekdays."""
    open_ = np.asarray(open_, float)
    close = open_ if close is None else np.asarray(close, float)
    high = np.maximum(open_, close) if high is None else np.asarray(high, float)
    low = np.minimum(open_, close) if low is None else np.asarray(low, float)
    days = pd.bdate_range(start, periods=len(open_))
    first = (days - pd.Timedelta(hours=2)).tz_localize("UTC")
    return pd.DataFrame({"trading_day": days, "open": open_, "high": high, "low": low, "close": close, "first_minute": first,
                         "last_minute": first + pd.Timedelta(hours=24) - pd.Timedelta(minutes=1)})


def test_day_rolls_at_17_new_york_in_winter_and_summer():
    # winter: 17:00 NY = 22:00 UTC; summer: 21:00 UTC
    t = ["2019-01-08 21:59", "2019-01-08 22:00", "2019-07-09 20:59", "2019-07-09 21:00"]
    assert [f"{d:%Y-%m-%d}" for d in trading_day(pd.DatetimeIndex(t, tz="UTC"))] == [
        "2019-01-08", "2019-01-09", "2019-07-09", "2019-07-10"]


def test_day_rolls_correctly_across_the_dst_switch():
    # Sunday 2019-03-10 is the US switch: Friday 17:00 is 22:00 UTC, Monday 17:00 is 21:00 UTC
    d = trading_day(pd.DatetimeIndex(["2019-03-11 20:59", "2019-03-11 21:00"], tz="UTC"))
    assert [f"{x:%Y-%m-%d}" for x in d] == ["2019-03-11", "2019-03-12"]


def test_sunday_session_joins_monday():
    # Sunday 17:30 New York and Monday 09:00 New York, one bar
    b = daily_bars(pd.concat([m1(["2019-01-06 22:30"], 2.1), m1(["2019-01-07 14:00"], 2.2)]))
    assert len(b) == 1 and b["trading_day"].iloc[0] == pd.Timestamp("2019-01-07")
    assert b["open"].iloc[0] == 2.1 and b["close"].iloc[0] == 2.2


def test_weekend_labelled_minutes_move_to_monday():
    # Friday 18:00 NY (label Saturday), Sunday 10:00 NY (label Sunday)
    assert set(trading_day(pd.DatetimeIndex(["2019-01-04 23:00", "2019-01-06 15:00"], tz="UTC"))) == {pd.Timestamp("2019-01-07")}


def test_ohlc_duplicates_and_flag_share():
    d = pd.concat([m1(["2019-01-08 10:00"], 2.1), m1(["2019-01-08 10:00"], 2.1), m1(["2019-01-08 10:01"], 2.3),
                   m1(["2019-01-08 10:02", "2019-01-08 10:03"], 2.0, gap_before=True)])
    b = daily_bars(d)
    assert b["minutes"].iloc[0] == 4
    assert (b["open"].iloc[0], b["high"].iloc[0], b["low"].iloc[0], b["close"].iloc[0]) == (2.1, 2.3, 2.0, 2.0)
    assert b["flagged_pct"].iloc[0] == pytest.approx(50.0)


def test_donchian_window_excludes_the_signal_day():
    # a new high on day 3 is a breakout of the 3 days before it, and needs a full window
    close = [2.10, 2.11, 2.12, 2.13, 2.135]
    b = bars(close)
    assert donchian_target(b, 3, 2).tolist() == [0, 0, 0, 1, 1]


def test_donchian_uses_highs_not_only_closes():
    b = bars([2.10, 2.10, 2.10, 2.11], high=[2.10, 2.12, 2.10, 2.11], low=[2.10] * 3 + [2.11])
    assert donchian_target(b, 3, 2)[-1] == 0        # close 2.11 is below the 2.12 high


def test_donchian_exit_on_shorter_window_goes_flat():
    b = bars([2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 2.145, 2.143, 2.142])
    # long on day 4; 2.143 is below the two prior lows (2.15, 2.145), but above the 4-day low, so flat and not short
    assert donchian_target(b, 4, 2).tolist() == [0, 0, 0, 0, 1, 1, 1, 0, 0]


def test_donchian_reverses_when_the_entry_low_breaks():
    b = bars([2.10, 2.11, 2.12, 2.13, 2.05])
    t = donchian_target(b, 3, 2)
    assert t.tolist() == [0, 0, 0, 1, -1]


def test_signals_do_not_change_when_the_future_changes():
    rng = np.random.default_rng(1)
    c = 2.1 + np.cumsum(rng.normal(0, 0.002, 400))
    a = bars(c)
    changed = c.copy()
    changed[300:] += 0.2
    b = bars(changed)
    assert (donchian_target(a, 20, 10)[:300] == donchian_target(b, 20, 10)[:300]).all()
    assert (ma_target(a, 50, 200)[:300] == ma_target(b, 50, 200)[:300]).all()


def test_ma_target_waits_for_both_averages_and_reverses():
    c = list(np.linspace(2.0, 2.2, 30)) + list(np.linspace(2.2, 1.9, 30))
    t = ma_target(bars(c), 2, 5)
    assert (t[:4] == 0).all() and t[4] == 1 and t[-1] == -1 and set(np.unique(t)) == {-1, 0, 1}
    assert np.count_nonzero(np.diff(t[4:])) == 1


def test_fill_is_next_open_and_cost_once():
    o = [2.10, 2.11, 2.12, 2.13, 2.14]
    b = bars(o, close=[2.10, 2.11, 2.15, 2.13, 2.14])
    t = build_trades(b, np.array([0, 1, 1, 0, 0]), np.full(5, 2.7))
    assert len(t) == 1
    r = t.iloc[0]
    assert r["entry_i"] == 2 and r["exit_i"] == 4 and r["gross_pips"] == pytest.approx((2.14 - 2.12) / PIP)
    assert r["net_no_swap_pips"] == pytest.approx(r["gross_pips"] - 2.7)
    assert r["entry_time"] == b["first_minute"].iloc[2] and r["hold_days"] == 2


def test_reversal_closes_and_opens_at_the_same_open():
    b = bars([2.10, 2.11, 2.12, 2.13])
    t = build_trades(b, np.array([1, -1, -1, -1]), np.ones(4))
    assert t["direction"].tolist() == ["long", "short"]
    assert t["exit_i"].iloc[0] == t["entry_i"].iloc[1] == 2


def test_signal_on_last_day_is_not_traded_and_open_position_closes_at_last_close():
    b = bars([2.10, 2.11, 2.12], close=[2.10, 2.11, 2.15])
    assert build_trades(b, np.array([0, 0, 1]), np.ones(3)).empty
    t = build_trades(b, np.array([0, 1, 1]), np.ones(3))
    assert t["exit_reason"].iloc[0] == "end_of_data" and t["gross_pips"].iloc[0] == pytest.approx((2.15 - 2.12) / PIP)


def nights(day_e, day_x, days):
    d = pd.DatetimeIndex(days)
    u = swap_units(d)
    return u[list(d).index(pd.Timestamp(day_x))] - u[list(d).index(pd.Timestamp(day_e))]


def test_swap_nights_and_wednesday_triple():
    days = pd.bdate_range("2019-01-07", periods=15)    # Monday start
    assert nights("2019-01-07", "2019-01-08", days) == 1          # Monday's rollover
    assert nights("2019-01-09", "2019-01-10", days) == 3          # Wednesday's rollover
    assert nights("2019-01-08", "2019-01-09", days) == 1          # Tuesday, entered Tue, out at Wed open
    assert nights("2019-01-10", "2019-01-11", days) == 1
    assert nights("2019-01-11", "2019-01-14", days) == 1          # Friday -> Monday is one rollover, no weekend extra
    assert nights("2019-01-07", "2019-01-14", days) == 7          # a full week is 7 nights


def test_swap_charges_a_holiday_missing_from_the_data():
    days = pd.bdate_range("2019-01-07", periods=10).delete(2)      # Wednesday has no bar
    assert nights("2019-01-08", "2019-01-10", days) == 4           # Tue + Wed x 3


def test_swap_is_the_same_for_long_and_short_and_reduces_net():
    b = bars(np.full(6, 2.10))                                     # Mon..Mon
    t = build_trades(b, np.array([1, 1, 1, 1, 0, 0]), np.zeros(6))
    assert t["direction"].tolist() == ["long"]                     # in at Tue open, out at next Mon open
    assert t["swap_pips"].iloc[0] == pytest.approx(6 * SWAP_PIPS_PER_NIGHT)   # Tue, Wed x 3, Thu, Fri
    assert (t["net_pips"] == -t["swap_pips"]).all()
    s = build_trades(b, -np.array([1, 1, 1, 1, 0, 0]), np.zeros(6))
    assert s["swap_pips"].iloc[0] == t["swap_pips"].iloc[0]


def test_end_of_data_does_not_pay_the_last_rollover():
    b = bars([2.10, 2.10, 2.10])                                   # Mon, Tue, Wed
    t = build_trades(b, np.array([1, 1, 1]), np.zeros(3))          # in at Tue open, out at Wed close
    assert t["swap_nights"].iloc[0] == 1                           # Tuesday's rollover only


def test_marked_to_market_sees_the_open_loss_that_closed_trades_miss():
    b = bars([2.10, 2.10, 2.00, 2.09, 2.11, 2.11])
    t = build_trades(b, np.array([1, 1, 1, 1, 0, 0]), np.zeros(6))
    eq = equity_by_day(b, t, swap=False)
    assert eq[-1] == pytest.approx(t["gross_pips"].sum())
    assert eq.min() == pytest.approx(-1000)
    assert t["gross_pips"].iloc[0] > 0


def test_equity_ends_at_total_net():
    rng = np.random.default_rng(2)
    b = bars(2.1 + np.cumsum(rng.normal(0, 0.002, 120)))
    t = build_trades(b, donchian_target(b, 10, 5), np.full(120, 2.7))
    assert equity_by_day(b, t)[-1] == pytest.approx(t["net_pips"].sum())


def test_random_baseline_has_no_edge_on_a_driftless_market_and_pays_costs():
    rng = np.random.default_rng(3)
    b = bars(2.1 + np.cumsum(rng.normal(0, 0.002, 900)))
    t = build_trades(b, donchian_target(b, 20, 10), np.full(900, 2.0))
    c = random_baseline(b, t, np.full(900, 2.0), 21, runs=300)
    assert np.mean(c["no_swap"]) == pytest.approx(-2.0, abs=3 * np.std(c["no_swap"]) / np.sqrt(300) + 1)
    assert (c["swap"] <= c["no_swap"]).all()


def test_random_baseline_keeps_positions_inside_the_data_when_always_in_market():
    b = bars(np.full(50, 2.1))
    t = build_trades(b, np.tile([1, 1, 1, 1, 1, -1, -1, -1, -1, -1], 5), np.zeros(50))
    c = random_baseline(b, t, np.zeros(50), 1, runs=50)
    assert np.isfinite(c["swap"]).all() and (c["no_swap"] == 0).all()


def test_direction_baseline_centres_on_minus_costs():
    t = pd.DataFrame({"gross_pips": [100.0, -40, 60, 20] * 10, "cost_pips": 3.0, "swap_pips": 2.0})
    c = direction_baseline(t, runs=2000)
    assert np.mean(c["no_swap"]) == pytest.approx(-3.0, abs=1.0) and np.mean(c["swap"]) == pytest.approx(-5.0, abs=1.0)


def test_late_minutes_counts_from_17_new_york_and_from_sunday_on_monday():
    b = pd.DataFrame({"trading_day": pd.to_datetime(["2019-01-07", "2019-01-08", "2019-07-09"]),
                      "first_minute": pd.to_datetime(["2019-01-06 22:00", "2019-01-08 00:00", "2019-07-08 21:05"], utc=True)})
    assert late_minutes(b).tolist() == [0, 120, 5]
