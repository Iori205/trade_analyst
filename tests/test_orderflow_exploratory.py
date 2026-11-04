import numpy as np
import pandas as pd
import pytest

from src.research.orderflow_exploratory import (TestLog, add_conditions, add_features, add_forward, analyse,
                                                cluster_corr, merge_inputs, partial_corr, pre_roll_thin)
from src.research.exploratory_stats import clean_bars


def flow_bars(start="2021-03-01 00:00", n=60, freq="15min", delta=None, volume=None, **cols):
    t = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    d = pd.Series(np.arange(n) % 7 - 3.0 if delta is None else delta, dtype=float)
    v = pd.Series(100.0 + np.arange(n) % 5 if volume is None else volume, dtype=float)
    f = pd.DataFrame({"bar_start_utc": t, "delta": d, "volume": v, "delta_ratio": d / v,
                      "roll_flag": False, "degraded_flag": False})
    for k, val in cols.items():
        f[k] = val
    return f


def spot_bars(times, opens=None, closes=None):
    n = len(times)
    o = np.full(n, 1.2) if opens is None else np.asarray(opens, dtype=float)
    c = o if closes is None else np.asarray(closes, dtype=float)
    b = pd.DataFrame({"bar_start_utc": times, "open": o, "close": c, "any_gap": False, "any_flag": False})
    return clean_bars(b)


def test_pre_roll_thin_is_friday_and_sunday_evening_before_a_monday_roll():
    t = pd.date_range("2021-03-11 12:00", "2021-03-15 03:00", freq="h", tz="UTC")
    t = t[(t.dayofweek < 5) | ((t.dayofweek == 6) & (t.hour >= 22))]
    f = pd.DataFrame({"bar_start_utc": t, "roll_flag": t == pd.Timestamp("2021-03-15 00:00", tz="UTC")})
    thin = pre_roll_thin(f)
    marked = t[thin.to_numpy()]
    assert marked.min() == pd.Timestamp("2021-03-12 00:00", tz="UTC")
    assert marked.max() == pd.Timestamp("2021-03-14 23:00", tz="UTC")
    assert not thin[t >= pd.Timestamp("2021-03-15 00:00", tz="UTC")].any()


def test_features_at_t_ignore_every_later_bar():
    base = add_features(flow_bars(n=80))
    changed = flow_bars(n=80)
    changed.loc[50:, ["delta", "delta_ratio"]] = 999.0
    changed.loc[50:, "volume"] = 5000.0
    other = add_features(changed)
    cols = ["delta_ratio", "delta_z", "cum_delta", "volume_spike", "spike_signed"]
    pd.testing.assert_frame_equal(base.loc[:49, cols], other.loc[:49, cols])


def test_z_score_uses_the_twenty_bars_before_t():
    delta = np.r_[np.tile([1.0, 3.0], 10), 22.0]
    f = add_features(flow_bars(n=21, delta=delta))
    past = pd.Series(delta[:20])
    assert f["delta_z"].iloc[20] == pytest.approx((22 - past.mean()) / past.std())
    assert f["delta_z"].iloc[:20].isna().all()


def test_volume_spike_is_over_the_prior_median():
    v = np.r_[np.full(20, 100.0), 300.0]
    assert add_features(flow_bars(n=21, volume=v))["volume_spike"].iloc[20] == pytest.approx(3.0)


def test_left_out_bar_empties_the_windows_that_hold_it():
    flagged = np.zeros(60, dtype=bool)
    flagged[30] = True
    f = add_features(flow_bars(n=60, degraded_flag=flagged))
    assert np.isnan(f["delta_ratio"].iloc[30])
    assert f["delta_z"].iloc[31:51].isna().all()
    assert f["delta_z"].iloc[51:].notna().all()
    assert f["left_out"].sum() == 1


def test_cum_delta_resets_at_each_session():
    f = flow_bars(start="2021-03-01 06:30", n=4, delta=[1.0, 2.0, 4.0, 8.0])  # 06:30, 06:45, then London
    assert list(add_features(f)["cum_delta"]) == [1, 3, 4, 12]


def test_cum_delta_stays_empty_after_a_left_out_bar_in_the_session():
    f = flow_bars(n=6, delta=[1.0] * 6, degraded_flag=[False, False, True, False, False, False])
    assert add_features(f)["cum_delta"].isna().tolist() == [False, False, True, True, True, True]


def test_forward_return_starts_at_the_next_open():
    t = pd.date_range("2021-03-01", periods=6, freq="15min", tz="UTC")
    s = add_forward(spot_bars(t, [1.2000, 1.2010, 1.2020, 1.2030, 1.2040, 1.2050], [1.2005, 1.2015, 1.2025, 1.2035, 1.2045, 1.2055]), 15)
    assert s["fwd_1"][0] == pytest.approx(5)    # close(1) - open(1)
    assert s["fwd_2"][0] == pytest.approx(15)   # close(2) - open(1)
    assert s["fwd_4"][0] == pytest.approx(35)   # close(4) - open(1)


def test_forward_return_needs_every_bar_on_the_path():
    t = pd.date_range("2021-03-01", periods=8, freq="15min", tz="UTC").delete(2)
    s = add_forward(spot_bars(t), 15)
    assert np.isnan(s["fwd_2"][0]) and not np.isnan(s["fwd_1"][0])   # t+2 is missing
    assert np.isnan(s["fwd_4"][0])
    assert np.isnan(s["fwd_1"][1])                                   # t+1 is missing


def test_forward_return_does_not_jump_a_weekend():
    fri = pd.date_range("2021-03-05 20:00", periods=2, freq="h", tz="UTC")
    sun = pd.date_range("2021-03-07 22:00", periods=4, freq="h", tz="UTC")
    s = add_forward(spot_bars(fri.append(sun)), 60)
    assert np.isnan(s["fwd_1"][1])


def conditions(ret, delta_z=3.0, delta=10.0, unit=4.0):
    d = pd.DataFrame({"delta": [delta], "delta_z": [delta_z], "ret": [ret], "move_unit": [unit]})
    r = add_conditions(d).iloc[0]
    return r.absorption, r.divergence, r.continuation


def test_condition_definitions():
    assert conditions(0.5) == (True, False, False)
    assert conditions(-3.0) == (False, True, False)
    assert conditions(3.0) == (False, False, True)
    assert conditions(1.5) == (False, False, False)            # between the two thresholds
    assert conditions(0.5, delta_z=1.0) == (False, False, False)  # delta not large
    assert conditions(0.5, delta_z=-3.0) == (False, False, False)  # z and delta disagree


def test_sell_side_divergence_is_price_rising():
    assert conditions(3.0, delta_z=-3.0, delta=-10.0) == (False, True, False)


def test_cluster_corr_widens_for_repeated_days():
    rng = np.random.default_rng(3)
    x, y = rng.normal(size=200), rng.normal(size=200)
    one = cluster_corr(x, y, np.arange(200))
    repeated = cluster_corr(np.tile(x, 5), np.tile(y, 5), np.tile(np.arange(200), 5))
    assert repeated["estimate"] == pytest.approx(one["estimate"])
    assert abs(repeated["z"]) == pytest.approx(abs(one["z"]), rel=0.05)


def planted(n=6000, strength=4.0, seed=5):
    """delta_ratio drives the next bar's spot return when strength > 0."""
    rng = np.random.default_rng(seed)
    t = pd.date_range("2021-03-01", periods=n, freq="15min", tz="UTC")
    t = t[(t.hour >= 8) & (t.hour < 16)]
    delta = rng.normal(0, 30, len(t))
    f = flow_bars(n=len(t), delta=delta, volume=np.full(len(t), 100.0))
    f["bar_start_utc"] = t
    pips = rng.normal(0, 3, len(t)) + strength * np.r_[0, delta[:-1]] / 30
    closes = 1.2 + pips * 1e-4
    d = merge_inputs(f, spot_bars(t, np.full(len(t), 1.2), closes), 15)
    d["cost"] = 1.0
    return d


def test_planted_signal_is_found_and_noise_is_not():
    hit = analyse({"M15": planted()})["tests"].set_index("test_id")
    assert hit.loc["corr M15 h1 all delta_ratio", "significant_fdr"]
    assert hit.loc["corr M15 h1 all delta_ratio", "estimate"] > 0.5
    assert hit.loc["spread M15 h1 all Q5-Q1", "edge_pips"] > 3
    noise = analyse({"M15": planted(strength=0.0)})["tests"]
    assert noise["significant_fdr"].mean() < 0.02


def test_same_bar_link_does_not_show_up_as_prediction():
    rng = np.random.default_rng(6)
    t = pd.date_range("2021-03-01", periods=6000, freq="15min", tz="UTC")
    t = t[(t.hour >= 8) & (t.hour < 16)]
    delta = rng.normal(0, 30, len(t))
    f = flow_bars(n=len(t), delta=delta, volume=np.full(len(t), 100.0))
    f["bar_start_utc"] = t
    opens = np.full(len(t), 1.2)
    closes = opens + (delta / 30) * 4e-4             # flow moves the price inside its own bar only
    d = merge_inputs(f, spot_bars(t, opens, closes), 15)
    d["cost"] = 1.0
    r = analyse({"M15": d})["tests"].set_index("test_id")
    assert abs(r.loc["corr M15 h1 all delta_ratio", "estimate"]) < 0.05


def test_small_cells_get_no_p_value():
    t = TestLog()
    t.add("condition", "M15", 1, "all", "x", {"n": 5, "estimate": 1.0, "z": 3.0, "p": 0.01}, "pips")
    assert np.isnan(t.rows[0]["p"])


def test_partial_corr_removes_a_link_that_runs_through_the_control():
    rng = np.random.default_rng(7)
    c = rng.normal(size=4000)
    d = pd.DataFrame({"x": c + rng.normal(0, 0.5, 4000), "c": c, "y": -c + rng.normal(0, 0.5, 4000), "day": np.arange(4000) // 20})
    assert cluster_corr(d["x"], d["y"], d["day"])["estimate"] < -0.5
    assert abs(partial_corr(d, "x", "c", "y")["estimate"]) < 0.05


def test_partial_corr_keeps_a_link_of_its_own():
    rng = np.random.default_rng(8)
    c, x = rng.normal(size=4000), rng.normal(size=4000)
    d = pd.DataFrame({"x": x, "c": c, "y": c + x, "day": np.arange(4000) // 20})
    assert partial_corr(d, "x", "c", "y")["estimate"] > 0.9
