"""Tests for the ML discovery pipeline. Synthetic data only (prices in the 2.x range).

Tests that fit models are skipped when scikit-learn is not installed.
"""

import numpy as np
import pandas as pd
import pytest

from src.research.ml_discovery import (
    BARRIERS, FEATURES, HORIZONS_H, NS_H, NS_MIN, candidates, deflated_sharpe, features, fold_masks, norm_ppf,
    random_trades, rule_trades, select_trades, trade_stats, triple_barrier, variant_name,
)
from tests.test_backtest_engine import StubCost

P = 2.1


def h1_bars(n=24 * 40, start="2019-01-01", seed=0):
    rng = np.random.default_rng(seed)
    t = pd.date_range(start, periods=n, freq="h", tz="UTC")
    c = P + np.cumsum(rng.normal(0, 0.0008, n))
    o = np.concatenate([[P], c[:-1]])
    return pd.DataFrame({"bar_start_utc": t, "open": o, "high": np.maximum(o, c) + 0.0004,
                         "low": np.minimum(o, c) - 0.0004, "close": c, "any_gap": False, "any_flag": False})


def m1_flat(start, minutes, price=P):
    t = pd.date_range(start, periods=minutes, freq="min", tz="UTC")
    return pd.DataFrame({"timestamp_utc": t, "high": price + 0.00001, "low": price - 0.00001, "close": price})


def one_candidate(entry="2019-01-02 10:00", price=P, atr=0.0010):
    return pd.DataFrame({"signal_start": [pd.Timestamp(entry, tz="UTC") - pd.Timedelta(hours=1)],
                         "entry_time": [pd.Timestamp(entry, tz="UTC")], "entry_price": [price], "atr": [atr],
                         "cost_pips": [1.0], "eligible": [True]})


END = int(pd.Timestamp("2022-01-01", tz="UTC").value)


def test_variant_count():
    assert len(BARRIERS) * len(HORIZONS_H) * 2 == 24
    labels = triple_barrier(one_candidate(), m1_flat("2019-01-02 10:00", 60 * 30), END)
    assert len(labels) == 24 and all(v["valid"].iloc[0] for v in labels.values())


def test_tp_sl_time_and_tie_rule():
    m1 = m1_flat("2019-01-02 10:00", 60 * 30)
    m1.loc[30, "high"] = P + 0.0016          # +16 pips at minute 30: TP 1.5 ATR (15 pips) long
    m1.loc[90, "low"] = P - 0.0011           # -11 pips at minute 90: SL 1 ATR long
    labels = triple_barrier(one_candidate(), m1, END)
    v = labels[variant_name("long", 1.5, 1.0, 4)].iloc[0]
    assert v["outcome"] == "tp" and v["y"] == 1 and v["ret_pips"] == pytest.approx(15.0)
    assert int(v["exit_ns"]) == int(m1["timestamp_utc"][30].value) + NS_MIN
    v2 = labels[variant_name("long", 2.0, 1.0, 4)].iloc[0]           # TP 20 pips never reached, SL at minute 90
    assert v2["outcome"] == "sl" and v2["ret_pips"] == pytest.approx(-10.0)
    s = labels[variant_name("short", 2.0, 1.5, 4)].iloc[0]            # short: SL 15 pips up is hit at minute 30
    assert s["outcome"] == "sl" and s["ret_pips"] == pytest.approx(-15.0)
    # both barriers inside the same minute -> SL
    m2 = m1_flat("2019-01-02 10:00", 60 * 30)
    m2.loc[5, ["high", "low"]] = [P + 0.0030, P - 0.0030]
    assert triple_barrier(one_candidate(), m2, END)[variant_name("long", 1.0, 1.0, 4)].iloc[0]["outcome"] == "sl"
    # nothing hit: time exit at the last close before the horizon
    m3 = m1_flat("2019-01-02 10:00", 60 * 30)
    m3.loc[60 * 4 - 1, "close"] = P + 0.0003
    t = triple_barrier(one_candidate(), m3, END)[variant_name("long", 1.0, 1.0, 4)].iloc[0]
    assert t["outcome"] == "time" and t["ret_pips"] == pytest.approx(3.0)
    assert int(t["exit_ns"]) == int(pd.Timestamp("2019-01-02 14:00", tz="UTC").value)


def test_censoring_gaps_and_split_end():
    m1 = m1_flat("2019-01-02 10:00", 60 * 30)
    m1 = m1.drop(index=range(300, 360)).reset_index(drop=True)        # 60-minute gap at 15:00
    labels = triple_barrier(one_candidate(), m1, END)
    assert labels[variant_name("long", 1, 1, 4)]["valid"].iloc[0]       # 10:00-14:00 has no gap
    assert not labels[variant_name("long", 1, 1, 8)]["valid"].iloc[0]   # 10:00-18:00 crosses the gap
    end = int(pd.Timestamp("2019-01-02 20:00", tz="UTC").value)
    lab = triple_barrier(one_candidate(), m1_flat("2019-01-02 10:00", 60 * 30), end)
    assert lab[variant_name("long", 1, 1, 8)]["valid"].iloc[0] and not lab[variant_name("long", 1, 1, 24)]["valid"].iloc[0]


def test_features_use_only_the_past():
    bars = h1_bars()
    f = features(bars)
    assert list(f.columns) == FEATURES
    changed = bars.copy()
    k = 500
    changed.loc[k + 1:, ["open", "high", "low", "close"]] += 0.02
    g = features(changed)
    pd.testing.assert_frame_equal(f.iloc[:k + 1], g.iloc[:k + 1])
    assert not f.iloc[k + 1:].equals(g.iloc[k + 1:])


def test_feature_values():
    bars = h1_bars()
    f = features(bars)
    i = 300
    a = f["atr_pips"].iloc[i] * 1e-4
    assert f["ret_4h_atr"].iloc[i] == pytest.approx((bars["close"][i] - bars["close"][i - 4]) / a)
    assert f["hour_utc"].iloc[i] == (bars["bar_start_utc"][i] + pd.Timedelta(hours=1)).hour
    before_asia = f[bars["bar_start_utc"].dt.hour < 6]
    assert before_asia["asia_high_dist_atr"].isna().all()               # Asia not complete yet
    assert f["ema50_h4_dist_atr"].iloc[:4 * 49].isna().all() and f["ema50_h4_dist_atr"].iloc[-1] == f["ema50_h4_dist_atr"].iloc[-1]


def test_candidates_follow_engine_entry_rules():
    bars = h1_bars(24 * 10, start="2019-01-07")
    bars.loc[30, "any_flag"] = True
    c = candidates(bars, StubCost(), "p75")
    assert not c.loc[29, "eligible"]                                     # entry bar 30 is flagged
    assert not c.loc[20, "eligible"]                                     # entry at 21:00 = rollover in the stub
    assert c.loc[40, "eligible"] and c.loc[40, "entry_price"] == bars.loc[41, "open"]
    assert not c.iloc[-1]["eligible"]                                    # no next bar


def test_walk_forward_embargo():
    t = pd.Series(pd.date_range("2015-01-01", "2019-12-31 23:00", freq="h", tz="UTC"))
    valid = np.ones(len(t), bool)
    tr, te = fold_masks(t, valid, 2018, 24)
    assert t[tr].max() < pd.Timestamp("2018-01-01", tz="UTC") - pd.Timedelta(hours=24) + pd.Timedelta(hours=1)
    assert t[tr].max() + pd.Timedelta(hours=24) <= pd.Timestamp("2018-01-01", tz="UTC")
    assert t[te].min() == pd.Timestamp("2018-01-01", tz="UTC") and t[te].max().year == 2018
    assert not (tr & te).any()


def test_select_trades_one_position():
    entry = np.array([0, 10, 20, 30, 40])
    exit_ = np.array([25, 15, 35, 45, 50])
    assert select_trades(np.arange(5), entry, exit_) == [0, 3]
    rng = np.random.default_rng(0)
    taken = random_trades(rng, np.arange(5), 5, entry, exit_)
    spans = sorted((entry[i], exit_[i]) for i in taken)
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))


def test_rule_trades_ev_filter():
    cands = pd.DataFrame({"entry_time": pd.date_range("2019-01-02", periods=4, freq="h", tz="UTC"),
                          "atr": 0.0010, "cost_pips": 1.0, "eligible": True})
    lab = pd.DataFrame({"valid": True, "y": [1, 0, 1, 0], "ret_pips": [10.0, -10.0, 10.0, -10.0],
                        "outcome": ["tp", "sl", "tp", "sl"],
                        "exit_ns": cands["entry_time"].astype("int64") + 30 * NS_MIN})
    p = np.array([0.6, 0.5, 0.56, np.nan])        # EV = 20p - 10 - 1 > 0  <=>  p > 0.55
    t = rule_trades(p, cands, lab, 1.0, 1.0, "long")
    assert len(t) == 2 and t["net_pips"].tolist() == [9.0, 9.0]


def test_stats_and_dsr():
    assert norm_ppf(0.975) == pytest.approx(1.959964, abs=1e-6) and norm_ppf(0.01) == pytest.approx(-2.326348, abs=1e-6)
    st = trade_stats(pd.DataFrame({"net_pips": [1.0, 2.0, 3.0, 4.0]}))
    assert st["t"] == pytest.approx(2.5 / np.std([1, 2, 3, 4], ddof=1) * 2)
    trials = np.random.default_rng(0).normal(0, 0.05, 48)
    assert deflated_sharpe(0.5, 400, 0.0, 3.0, trials) > 0.99
    assert deflated_sharpe(0.0, 400, 0.0, 3.0, trials) < 0.5


def test_walk_forward_models_fit():
    pytest.importorskip("sklearn")
    from src.research.ml_discovery import walk_forward
    n = 24 * 365 * 5
    t = pd.Series(pd.date_range("2015-01-01", periods=n, freq="h", tz="UTC"))
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(n, len(FEATURES))), columns=FEATURES)
    lab = pd.DataFrame({"valid": t.dt.year <= 2019, "y": (X["hour_utc"] > 0).astype(int)})
    for kind in ("tree", "hgb"):
        p, fitted = walk_forward(X, lab, t, 4, kind)
        oof = ~np.isnan(p)
        assert oof.any() and (t[oof].dt.year >= 2018).all()
        assert ((p[oof] > 0.5) == (X["hour_utc"].to_numpy()[oof] > 0)).mean() > 0.95
