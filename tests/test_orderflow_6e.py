import hashlib

import numpy as np
import pandas as pd
import pytest

from src.data.orderflow_6e import (KEY, add_returns, build_bars, gap_stats, merge_overlap, roll_table, split_bars,
                                   spot_compare, tick_check)
from src.data.splits import Split, TestSetLockedError

SIDE = {"buy": "B", "sell": "A"}
T0 = pd.Timestamp("2021-03-01 10:00", tz="UTC").value
MIN = 60_000_000_000


def trades(rows):
    """rows: (minutes after T0, price, size, side, sequence, instrument_id)."""
    df = pd.DataFrame(rows, columns=["m", "price", "size", "side", "sequence", "instrument_id"])
    df["ts_event"] = T0 + (df.pop("m") * MIN).astype("int64")
    df["price"] = (df["price"] * 1e9).round().astype("int64")
    return df


def test_delta_is_buy_minus_sell_and_volume_adds_up():
    t = trades([(0, 1.2, 3, "B", 1, 7), (1, 1.2, 5, "A", 2, 7), (2, 1.2, 2, "N", 3, 7), (3, 1.3, 4, "B", 4, 7)])
    b = build_bars(t, 15, SIDE).iloc[0]
    assert (b.buy_volume, b.sell_volume, b.unknown_volume, b.volume) == (7, 5, 2, 14)
    assert b.delta == b.buy_volume - b.sell_volume == 2
    assert b.delta_ratio == pytest.approx(2 / 14)
    assert b.trade_count == 4
    assert b.vwap == pytest.approx((1.2 * 10 + 1.3 * 4) / 14)


def test_side_map_decides_the_sign():
    t = trades([(0, 1.2, 3, "B", 1, 7)])
    assert build_bars(t, 15, SIDE).delta[0] == 3
    assert build_bars(t, 15, {"buy": "A", "sell": "B"}).delta[0] == -3


def test_trade_on_the_boundary_starts_the_next_bar():
    t = trades([(14.999, 1.1, 1, "B", 1, 7), (15, 1.2, 2, "A", 2, 7)])
    b = build_bars(t, 15, SIDE)
    assert list(b.bar_start_utc) == [pd.Timestamp("2021-03-01 10:00", tz="UTC"), pd.Timestamp("2021-03-01 10:15", tz="UTC")]
    assert list(b.close) == pytest.approx([1.1, 1.2])


def test_later_trades_never_change_an_earlier_bar():
    t = trades([(m, 1.1 + m / 1000, 1 + m, "B" if m % 2 else "A", m, 7) for m in range(0, 90, 7)])
    full = add_returns(build_bars(t, 15, SIDE))
    for cut in range(1, len(t)):
        part = add_returns(build_bars(t.iloc[:cut], 15, SIDE))
        closed = part.iloc[:-1]  # the last bar can still be filling
        pd.testing.assert_frame_equal(closed, full.iloc[: len(closed)])


def test_bar_label_is_the_start_with_hourly_width():
    t = trades([(0, 1.1, 1, "B", 1, 7), (59, 1.1, 1, "B", 2, 7), (60, 1.1, 1, "B", 3, 7)])
    b = build_bars(t, 60, SIDE)
    assert list(b.volume) == [2, 1]


def test_unsorted_trades_are_refused():
    with pytest.raises(ValueError):
        build_bars(trades([(5, 1.1, 1, "B", 1, 7), (1, 1.1, 1, "B", 2, 7)]), 15, SIDE)


def test_overlap_removed_but_repeated_fills_kept():
    part = trades([(0, 1.1, 1, "A", 1, 7), (0, 1.1, 1, "A", 1, 7), (5, 1.2, 1, "A", 2, 7), (5, 1.2, 1, "A", 2, 7),
                   (6, 1.2, 2, "B", 3, 7)])
    tail = trades([(5, 1.2, 1, "A", 2, 7), (5, 1.2, 1, "A", 2, 7), (6, 1.2, 2, "B", 3, 7), (9, 1.3, 1, "B", 4, 7)])
    merged, stats = merge_overlap(part, tail)
    assert stats["removed"] == 3
    assert len(merged) == 6
    assert merged.duplicated(KEY).sum() == 2  # one repeat before the join, one in the overlap
    assert merged["ts_event"].is_monotonic_increasing


def test_part_row_missing_from_the_tail_survives():
    part = trades([(5, 1.2, 1, "A", 2, 7), (6, 1.2, 9, "B", 3, 7)])
    tail = trades([(5, 1.2, 1, "A", 2, 7), (7, 1.3, 1, "B", 4, 7)])
    merged, stats = merge_overlap(part, tail)
    assert stats["part_only_in_overlap"] == 1
    assert len(merged) == 3


def test_roll_inside_a_bar():
    t = trades([(1, 1.1, 1, "B", 1, 7), (2, 1.2, 1, "B", 2, 8), (20, 1.2, 1, "B", 3, 8)])
    b = add_returns(build_bars(t, 15, SIDE))
    assert list(b.roll_flag) == [True, False]
    assert list(b.roll_inside_bar) == [True, False]
    assert (b.instrument_id_first[0], b.instrument_id_last[0]) == (7, 8)
    assert np.isnan(b.ret_log[0])
    assert b.ret_log[1] == pytest.approx(0.0)


def test_roll_on_the_bar_boundary_is_flagged_and_gets_no_return():
    t = trades([(1, 1.10, 1, "B", 1, 7), (16, 1.11, 1, "B", 2, 7), (30, 1.16, 1, "B", 3, 8), (46, 1.17, 1, "B", 4, 8)])
    b = add_returns(build_bars(t, 15, SIDE))
    assert list(b.roll_flag) == [False, False, True, False]
    assert not b.roll_inside_bar.any()
    assert np.isnan(b.ret_log[2])
    assert b.ret_log[1] == pytest.approx(np.log(1.11 / 1.10))
    assert b.ret_log[3] == pytest.approx(np.log(1.17 / 1.16))


def test_no_return_crosses_a_roll_at_a_gap():
    t = trades([(1, 1.10, 1, "B", 1, 7), (600, 1.20, 1, "B", 2, 8)])
    b = add_returns(build_bars(t, 60, SIDE))
    assert b.ret_log.isna().all()


def test_degraded_flag_is_kept_not_dropped():
    t = trades([(0, 1.1, 1, "B", 1, 7), (60 * 24, 1.1, 1, "B", 2, 7)])
    b = build_bars(t, 60, SIDE, ["2021-03-02"])
    assert len(b) == 2
    assert list(b.degraded_flag) == [False, True]


def test_same_input_same_hash(tmp_path):
    t = trades([(m, 1.1 + m / 1e4, 1 + m % 3, "ABN"[m % 3], m, 7 if m < 40 else 8) for m in range(100)])
    hashes = []
    for name in "ab":
        p = tmp_path / f"{name}.parquet"
        add_returns(build_bars(t, 15, SIDE)).to_parquet(p, index=False, compression="snappy")
        hashes.append(hashlib.sha256(p.read_bytes()).hexdigest())
    assert hashes[0] == hashes[1]


def test_bars_cannot_reach_the_locked_split():
    splits = {"test": Split("test", pd.Timestamp("2021-01-01", tz="UTC"), pd.Timestamp("2022-01-01", tz="UTC"), True)}
    with pytest.raises(TestSetLockedError):
        split_bars(build_bars(trades([(0, 1.1, 1, "B", 1, 7)]), 15, SIDE), splits)


def test_tick_check_counts_only_within_one_contract():
    t = trades([(0, 1.1, 1, "A", 1, 7), (1, 1.2, 1, "B", 2, 7), (2, 1.1, 1, "A", 3, 7), (3, 1.3, 1, "A", 4, 8)])
    c = tick_check(t)
    assert (c["up_B"], c["down_A"], c["up_A"]) == (1, 1, 0)


def test_gap_stats_separates_the_weekend():
    fri = pd.Timestamp("2021-03-05 21:59", tz="UTC").value
    ts = np.array([fri, fri + 49 * 60 * MIN, fri + 52 * 60 * MIN])
    counts, rows = gap_stats(ts)
    assert counts["weekend"] == 1
    assert counts["2h+ not weekend"] == 1
    assert len(rows) == 1


def test_spot_compare_finds_a_planted_lag():
    idx = pd.date_range("2021-01-04", periods=4000, freq="min", tz="UTC")
    rng = np.random.default_rng(1)
    px = np.exp(np.cumsum(rng.normal(0, 1e-4, len(idx))))
    fut = pd.DataFrame({"ts_event": idx.as_unit("ns").asi8, "close": (px * 1e9).astype("int64"), "instrument_id": 7})
    spot = pd.DataFrame({"timestamp_utc": idx + pd.Timedelta(minutes=2), "close": px, "low_quality_period": False})
    best, _ = spot_compare(fut, spot)
    row = best[best.period == "2021"].iloc[0]
    assert row.best_lag == 2
    assert row.r_best == pytest.approx(1.0, abs=1e-3)


def test_spot_compare_counts_a_reversing_spike():
    idx = pd.date_range("2021-01-04", periods=4000, freq="min", tz="UTC")
    rng = np.random.default_rng(2)
    px = np.exp(np.cumsum(rng.normal(0, 1e-4, len(idx))))
    bad = px.copy()
    bad[2000] *= 1.02
    fut = pd.DataFrame({"ts_event": idx.as_unit("ns").asi8, "close": (bad * 1e9).astype("int64"), "instrument_id": 7})
    spot = pd.DataFrame({"timestamp_utc": idx, "close": px, "low_quality_period": False})
    row = spot_compare(fut, spot)[0].query("period == '2021'").iloc[0]
    assert row.spikes == 2
    assert row.r_lag0 < 0.6
    assert row.r_lag0_no_spikes > 0.99


def test_roll_table_takes_the_spot_move_out_of_the_jump():
    days = pd.bdate_range("2021-01-04", periods=40, tz="UTC")
    rows = [(d, 1.2000, 1.2000, 100, 7) for d in days[:-2]]
    rows.append((days[-2], 1.2000, 1.2000, 10, 7))                 # thin last weekday on the old contract
    rows.append((days[-1], 1.2060, 1.2060, 100, 8))                # new contract opens 60 pips higher
    o = pd.DataFrame(rows, columns=["ts", "open", "close", "volume", "instrument_id"])
    o = pd.DataFrame({"ts_event": o.ts.dt.as_unit("ns").astype("int64"), "open": (o.open * 1e9).round(), "close": (o.close * 1e9).round(),
                      "volume": o.volume, "instrument_id": o.instrument_id})
    spot = pd.Series([1.1, 1.1010], index=[days[-2], days[-1]])    # spot rose 10 pips
    r = roll_table(o, spot).iloc[0]
    assert (r.old_id, r.new_id) == (7, 8)
    assert r.jump_pips == pytest.approx(60)
    assert r.spot_move_pips == pytest.approx(10)
    assert r.basis_est_pips == pytest.approx(50)
    assert r.last_weekday_vol_ratio == pytest.approx(0.1)
