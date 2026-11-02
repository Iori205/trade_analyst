"""Tests for backtest engine v1. Synthetic bars (prices in the 2.x range) and a stub cost model."""

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.backtest.baselines import ma_crossover, monday_13, random_strategy
from src.backtest.engine import (
    TRIAL_COLUMNS, History, Strategy, backtest, daily_sharpe, log_trial, max_drawdown, metrics, prepare, run_backtest,
    load_context,
)
from src.data.splits import TestSetLockedError


class StubCost:
    """cost_for stand-in: fixed cost, optional per-hour cost, rollover at 21:00 UTC, Sunday = weekly open."""

    def __init__(self, base=1.0, by_hour=None):
        self.base, self.by_hour = base, by_hour or {}

    def cost_for(self, times, percentile=None):
        t = pd.DatetimeIndex(times)
        cost = np.array([self.by_hour.get(h, self.base) for h in t.hour], float)
        return pd.DataFrame({"total_pips": cost, "percentile": percentile or "p75", "is_rollover": t.hour == 21,
                             "is_weekly_open": t.dayofweek == 6, "is_market_closed": t.dayofweek == 5})


def make_bars(n=200, start="2019-01-07 00:00", freq="h", prices=None, seed=0, flags=None):
    t = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    if prices is None:
        rng = np.random.default_rng(seed)
        prices = 2.0 + np.cumsum(rng.normal(0, 0.0005, n))
    prices = np.asarray(prices, float)
    opens = np.concatenate([[prices[0]], prices[:-1]])
    df = pd.DataFrame({"bar_start_utc": t, "open": opens, "high": np.maximum(opens, prices) + 0.0001,
                       "low": np.minimum(opens, prices) - 0.0001, "close": prices,
                       "any_gap": False, "any_flag": False})
    for i in flags or []:
        df.loc[i, "any_flag"] = True
    return df


def always(side, hold=None, exit_on_signal=False):
    return Strategy("const", lambda h: side if h.position == 0 else None, {}, hold_bars=hold, exit_on_signal=exit_on_signal)


def test_signal_sees_only_closed_bars_and_fills_next_open():
    bars = make_bars(50)
    seen = []

    def spy(h: History):
        seen.append((h.i, len(h.close), h.time[-1]))
        with pytest.raises(IndexError):
            h.close[h.i + 1]                     # nothing beyond the closed bar exists
        return 1 if h.i == 10 and h.position == 0 else None

    data = prepare(bars, StubCost())
    trades = backtest(data, Strategy("spy", spy, hold_bars=3, exit_on_signal=False), "H1")
    assert all(n == i + 1 and t == data["time"][i] for i, n, t in seen)
    tr = trades.iloc[0]
    assert tr["entry_time"] == bars["bar_start_utc"][11] and tr["entry_price"] == bars["open"][11]
    assert tr["exit_time"] == bars["bar_start_utc"][14] and tr["exit_price"] == bars["open"][14]


def test_changing_the_future_does_not_change_past_decisions():
    base = make_bars(300, seed=1)
    changed = base.copy()
    changed.loc[200:, ["open", "high", "low", "close"]] += 0.05        # rewrite everything from bar 200 on
    data_a, data_b = prepare(base, StubCost()), prepare(changed, StubCost())
    ta, tb = backtest(data_a, ma_crossover(5, 20), "H1"), backtest(data_b, ma_crossover(5, 20), "H1")
    cutoff = base["bar_start_utc"][200]
    pa = ta[ta["exit_time"] < cutoff].drop(columns=["exit_reason"])
    pb = tb[tb["exit_time"] < cutoff].drop(columns=["exit_reason"])
    pd.testing.assert_frame_equal(pa.reset_index(drop=True), pb.reset_index(drop=True))
    assert len(pa) > 3


def test_cost_is_charged_once_per_trade_at_entry_time():
    flat = make_bars(100, prices=[2.0] * 100)
    cost = StubCost(base=1.0, by_hour={11: 2.5})
    trades = backtest(prepare(flat, cost), always(1, hold=2), "H1")
    assert (trades["gross_pips"] == 0).all()
    expected = [2.5 if t.hour == 11 else 1.0 for t in trades["entry_time"]]
    assert trades["cost_pips"].tolist() == expected and (trades["net_pips"] == -trades["cost_pips"]).all()
    m = metrics(trades, flat["bar_start_utc"].iloc[0], flat["bar_start_utc"].iloc[-1])
    assert m["expectancy_pips"] == pytest.approx(-np.mean(expected)) and m["win_rate"] == 0


def test_long_and_short_pnl():
    up = make_bars(10, prices=[2.0 + 0.001 * i for i in range(10)])   # each bar opens 10 pips above the last
    long_, short = backtest(prepare(up, StubCost(0)), always(1, hold=2), "H1"), backtest(prepare(up, StubCost(0)), always(-1, hold=2), "H1")
    assert long_["gross_pips"].iloc[0] == pytest.approx(20.0) and short["gross_pips"].iloc[0] == pytest.approx(-20.0)


def test_entries_blocked_on_flags_rollover_gaps_and_weekly_open():
    bars = make_bars(48, start="2019-01-07 00:00", flags=[5])
    bars = bars.drop(index=[30]).reset_index(drop=True)                   # gap: 06:00 on day 2 is missing
    trades = backtest(prepare(bars, StubCost()), always(1, hold=1), "H1")
    entries = set(trades["entry_time"])
    t = pd.Timestamp
    assert t("2019-01-07 05:00", tz="UTC") not in entries                  # any_flag bar
    assert t("2019-01-07 21:00", tz="UTC") not in entries                  # rollover
    assert t("2019-01-08 07:00", tz="UTC") not in entries                  # first bar after the gap
    assert t("2019-01-07 06:00", tz="UTC") in entries
    sunday = make_bars(6, start="2019-01-06 21:00")
    assert backtest(prepare(sunday, StubCost()), always(1, hold=1), "H1")["entry_time"].dt.dayofweek.ne(6).all()


def test_exit_on_signal_and_reversal():
    prices = [2.0] * 5 + [2.01] * 5
    sides = {2: 1, 6: -1}
    strat = Strategy("flip", lambda h: sides.get(h.i), {}, hold_bars=None, exit_on_signal=True)
    trades = backtest(prepare(make_bars(10, prices=prices), StubCost(0)), strat, "H1")
    assert trades["direction"].tolist() == ["long", "short"]
    assert trades["exit_reason"].tolist() == ["signal", "end_of_data"]
    assert trades["entry_time"].iloc[1] == trades["exit_time"].iloc[0]     # reversal at the same open


def test_random_strategy_expectancy_is_minus_cost():
    bars = make_bars(24 * 400, seed=3)
    data = prepare(bars, StubCost(1.0))
    exp = []
    for seed in range(20):
        t = backtest(data, random_strategy(seed, p_entry=0.1, hold=4), "H1")
        exp.append(t["net_pips"].mean())
    se = np.std(exp, ddof=1) / np.sqrt(len(exp))
    assert abs(np.mean(exp) + 1.0) < max(3 * se, 0.3)


def test_random_strategy_is_reproducible():
    data = prepare(make_bars(500, seed=4), StubCost())
    a = backtest(data, random_strategy(7), "H1")
    b = backtest(data, random_strategy(7), "H1")
    pd.testing.assert_frame_equal(a, b)


def test_monday_13_enters_13_and_exits_14():
    bars = make_bars(24 * 14, start="2019-01-07 00:00")
    trades = backtest(prepare(bars, StubCost()), monday_13(), "H1")
    assert len(trades) == 2
    assert (trades["entry_time"].dt.hour == 13).all() and (trades["exit_time"].dt.hour == 14).all()
    assert (trades["entry_time"].dt.dayofweek == 0).all()


def test_metrics_drawdown_and_sharpe():
    assert max_drawdown([5, -3, -4, 10, -1]) == 7
    t = pd.DataFrame({"exit_time": pd.DatetimeIndex(["2019-01-07 10:00", "2019-01-08 10:00"], tz="UTC"),
                      "net_pips": [2.0, -1.0], "cost_pips": [1.0, 1.0]})
    s = daily_sharpe(t, pd.Timestamp("2019-01-07", tz="UTC"), pd.Timestamp("2019-01-10", tz="UTC"))
    days = np.array([2.0, -1.0, 0.0])
    assert s == pytest.approx(days.mean() / days.std(ddof=1) * np.sqrt(252))


def test_trial_log_appends_and_refuses_other_header(tmp_path):
    p = tmp_path / "trials" / "trials.csv"
    log_trial(p, {"strategy": "a", "trades": 1})
    log_trial(p, {"strategy": "b", "trades": 2})
    rows = list(csv.DictReader(open(p)))
    assert [r["strategy"] for r in rows] == ["a", "b"] and list(rows[0]) == TRIAL_COLUMNS
    bad = tmp_path / "bad.csv"
    bad.write_text("x,y\n1,2\n")
    with pytest.raises(ValueError):
        log_trial(bad, {"strategy": "c"})
    assert bad.read_text() == "x,y\n1,2\n"


def test_run_backtest_defaults_to_train_and_guards_test(tmp_path, monkeypatch):
    root = tmp_path
    (root / "config").mkdir()
    (root / "config/splits.yaml").write_text(
        'splits:\n  train: {start: "2019-01-01", end: "2019-12-31"}\n'
        '  validation: {start: "2020-01-01", end: "2020-12-31"}\n'
        '  test: {start: "2021-01-01", end: "2021-12-31", locked: true}\n', encoding="utf-8")
    bars_dir = root / "data/processed/eurusd_bars/v1"
    bars_dir.mkdir(parents=True)
    for split, start in (("train", "2019-01-07"), ("test", "2021-01-04")):
        make_bars(100, start=start).to_parquet(bars_dir / f"eurusd_h1_{split}.parquet", index=False)
    monkeypatch.setattr("src.backtest.engine.load_cost_config", lambda p: {"trading_costs": {"spread_percentile": "p75"}})
    monkeypatch.setattr("src.backtest.engine.CostModel.load", classmethod(lambda cls, d, cfg: StubCost()))
    ctx = load_context(root)
    r = run_backtest(ctx, always(1, hold=2), "H1")
    assert r["record"]["split"] == "train" and r["metrics"]["trades"] > 0
    with pytest.raises(TestSetLockedError):
        run_backtest(ctx, always(1, hold=2), "H1", split="test")
    rows = list(csv.DictReader(open(root / "reports/trials/trials.csv")))
    assert len(rows) == 1 and json.loads(rows[0]["params"])["hold_bars"] == 2   # the refused run is not logged


def test_exit_clock_whichever_first():
    bars = make_bars(4 * 24 * 2, start="2019-01-07 00:00", freq="15min")
    entries = {"2019-01-07 17:00": 1, "2019-01-08 20:15": 1}

    def signal(h):
        return entries.get(str(pd.Timestamp(h.time[-1]))[:16]) if h.position == 0 else None
    strat = Strategy("clock", signal, {}, hold_bars=16, exit_on_signal=False, exit_clock_utc="20:45")
    trades = backtest(prepare(bars, StubCost()), strat, "M15")
    assert [str(t)[11:16] for t in trades["entry_time"]] == ["17:15", "20:30"]
    assert [str(t)[11:16] for t in trades["exit_time"]] == ["20:45", "20:45"]    # 4h would be 21:15 and 00:30 (next day)
    early = Strategy("clock", signal, {}, hold_bars=4, exit_on_signal=False, exit_clock_utc="20:45")
    assert str(backtest(prepare(bars, StubCost()), early, "M15")["exit_time"].iloc[0])[11:16] == "18:15"
