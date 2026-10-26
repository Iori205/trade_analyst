"""Tests for the spread / cost model. Synthetic fixtures only (prices in the 2.x range)."""

import copy
import gzip
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.data.cost_model import (
    CostModel, build, classify, hour_of_week, load_cost_config, minute_spreads, regime_test, rollover_hours, run, stats,
)
from src.data.inventory import sha256_file

PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "cost_model_v1.yaml"


@pytest.fixture
def cfg():
    return load_cost_config(PROJECT_CONFIG)


def week(sunday: str, spread_pips=0.2, file=None) -> pd.DataFrame:
    """One FXCM-like week: every minute from Sunday 17:00 to Friday 16:59 New York, labels in UTC."""
    ny = pd.date_range(f"{sunday} 17:00", periods=5 * 24 * 60, freq="min", tz="America/New_York")
    utc = ny.tz_convert("UTC").tz_localize(None)
    spread = spread_pips(ny) if callable(spread_pips) else spread_pips
    bid = pd.Series(2.0, index=range(len(utc)))
    return pd.DataFrame({"file": file or sunday, "timestamp_label": utc, "bid_close": bid,
                         "ask_close": bid + pd.Series(spread, index=bid.index) * 1e-4})


def utc(*ts):
    return pd.Series(pd.DatetimeIndex(ts, tz="UTC"))


def test_classify_follows_new_york_clock(cfg):
    c = classify(utc("2021-07-07 21:00", "2021-01-13 21:00", "2021-01-13 22:00", "2021-07-07 22:30",
                     "2021-07-11 21:10", "2021-01-10 22:10", "2021-01-10 23:10", "2021-07-10 12:00",
                     "2021-07-09 21:30", "2021-07-11 15:00", "2021-07-07 12:00"), cfg)
    assert c["segment"].tolist() == ["rollover", "regular", "rollover", "regular",
                                     "weekly_open_first_hour", "weekly_open_first_hour", "weekly_open_rest",
                                     "market_closed", "market_closed", "market_closed", "regular"]
    assert c["regime"].tolist()[:3] == ["summer", "winter", "winter"]
    assert rollover_hours(cfg) == {"summer": {20, 21}, "winter": {21, 22}}


def test_anomalies_are_counted_not_removed(cfg):
    fx = week("2021-07-11")
    fx.loc[[100, 101], "ask_close"] = fx.loc[[100, 101], "bid_close"] - 1e-5   # negative
    fx.loc[200, "ask_close"] = fx.loc[200, "bid_close"]                         # zero
    fx.loc[300, "ask_close"] = fx.loc[300, "bid_close"] + 9e-4                  # extreme, 9 pips
    m = minute_spreads(fx, cfg)
    assert len(m) == len(fx)
    assert m["category"].value_counts().to_dict() == {"normal": len(fx) - 4, "negative": 2, "zero": 1, "extreme": 1}
    assert int(m["used"].sum()) == len(fx) - 3  # extreme stays in the statistics


@pytest.fixture
def model(cfg):
    weeks = [week(s) for s in ("2021-01-10", "2021-01-17", "2021-01-24", "2021-07-11", "2021-07-18", "2021-07-25")]
    m = minute_spreads(pd.concat(weeks, ignore_index=True), cfg)
    built = build(m, cfg)
    return built, CostModel(built["hour_of_week"], built["segments"], built["fallback"], cfg)


def test_every_hour_of_the_week_gets_a_positive_value(model):
    _, cm = model
    for start in ("2021-01-10", "2021-07-11"):          # winter and summer weeks, Sunday 00:00 UTC
        hours = pd.date_range(start, periods=7 * 24 * 4, freq="15min", tz="UTC")
        for q in ("median", "p75", "p90"):
            out = cm.lookup(hours, q)
            assert len(out) == len(hours) and out["spread_pips"].notna().all() and (out["spread_pips"] > 0).all()
    assert set(out["segment"]) == {"regular", "rollover", "weekly_open_first_hour", "weekly_open_rest", "market_closed"}
    assert set(out["source"]) <= {"cell", "segment", "fallback"}


def test_fallback_for_thin_cells(cfg, model):
    built, cm = model
    table = built["hour_of_week"]
    assert len(table) == 120
    fri_late = table[(table["weekday_name"] == "Fri") & (table["hour_utc"].isin([22, 23]))]
    assert fri_late["fallback"].all() and (fri_late["n_minutes"] == 0).all()
    assert (fri_late["median"] == built["fallback"]["median"]).all()
    # Raising min_weeks above the weeks available sends every cell to the fallback
    thin = copy.deepcopy(cfg)
    thin["sample"]["min_weeks"] = 4
    t4 = hour_of_week(minute_spreads(pd.concat([week("2021-01-10"), week("2021-07-11")]), thin)
                      .query("used"), thin, built["fallback"])
    assert t4["fallback"].all()  # only 2 weeks in total
    out = cm.lookup(pd.DatetimeIndex(["2021-07-09 22:30"], tz="UTC"))  # Friday after the close
    assert out["source"].iloc[0] == "fallback" and out["spread_pips"].iloc[0] == built["fallback"]["median"]


def test_cell_and_segment_values_come_from_data(cfg):
    def spread(ny):  # 0.3 pip normally, 2.0 pips in the rollover window
        minutes = ny.hour * 60 + ny.minute
        return [2.0 if 16 * 60 + 55 <= m < 18 * 60 else 0.3 for m in minutes]
    weeks = [week(s, spread) for s in ("2021-07-11", "2021-07-18", "2021-07-25")]
    built = build(minute_spreads(pd.concat(weeks, ignore_index=True), cfg), cfg)
    cm = CostModel(built["hour_of_week"], built["segments"], built["fallback"], cfg)
    out = cm.lookup(pd.DatetimeIndex(["2021-07-28 12:00", "2021-07-28 21:30"], tz="UTC"))
    assert out["spread_pips"].tolist() == [0.3, 2.0] and out["source"].tolist() == ["cell", "segment"]


def test_cost_is_floored_above_zero(cfg):
    weeks = [week(s, 0.01) for s in ("2021-07-11", "2021-07-18", "2021-07-25")]   # 0.01 pip everywhere
    built = build(minute_spreads(pd.concat(weeks, ignore_index=True), cfg), cfg)
    cm = CostModel(built["hour_of_week"], built["segments"], built["fallback"], cfg)
    out = cm.lookup(pd.date_range("2021-07-25", periods=168, freq="h", tz="UTC"))
    assert (out["spread_pips"] == cfg["floor_pips"]).all()


def test_regime_test_detects_a_real_difference(cfg):
    rows = []
    for i in range(8):
        regime = "winter" if i < 4 else "summer"
        for cell in range(10):
            rows.append({"file": f"w{i}", "segment": "regular", "regime": regime, "weekday": cell % 5,
                         "hour": cell, "spread_pips": (0.6 if regime == "winter" else 0.2) + 0.01 * i})
    r = regime_test(pd.DataFrame(rows), cfg)
    assert r["separate"] and r["p_value"] <= 0.05 and r["statistic_pips"] > 0.3
    same = pd.DataFrame(rows).assign(spread_pips=0.2)
    assert not regime_test(same, cfg)["separate"]


def write_fxcm_dir(root: Path, frames: list[pd.DataFrame]) -> None:
    d = root / "data/reference/fxcm/v1"
    rows, sums = [], []
    for i, fx in enumerate(frames):
        local = f"m1/EURUSD/2021/{i + 1}.csv.gz"
        text = pd.DataFrame({"DateTime": fx["timestamp_label"].dt.strftime("%m/%d/%Y %H:%M:%S.000"),
                             **{f"{s}{f}": fx[f"{s.lower()}_close"].round(5)
                                for s in ("Bid", "Ask") for f in ("Open", "High", "Low", "Close")}})
        text = text[["DateTime", "BidOpen", "BidHigh", "BidLow", "BidClose", "AskOpen", "AskHigh", "AskLow", "AskClose"]]
        (d / local).parent.mkdir(parents=True, exist_ok=True)
        (d / local).write_bytes(gzip.compress(text.to_csv(index=False).encode(), mtime=0))
        rows.append({"local_path": local})
        sums.append(f"{sha256_file(d / local)}  {local}")
    pd.DataFrame(rows).to_csv(d / "MANIFEST.csv", index=False)
    (d / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")


def test_run_is_deterministic_and_never_overwrites(tmp_path, cfg):
    days = [week(s).iloc[:3000] for s in ("2021-01-10", "2021-07-11", "2021-07-18")]
    write_fxcm_dir(tmp_path, days)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/cost_model_v1.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    src = tmp_path / "data/reference/fxcm/v1/m1/EURUSD/2021/1.csv.gz"
    before = sha256_file(src)
    a = run(tmp_path, out_dir=Path("out/a"))
    b = run(tmp_path, out_dir=Path("out/b"))
    assert a["manifest"]["outputs"] == b["manifest"]["outputs"]
    assert a["manifest"]["inputs"]["audit_53_spread_by_hour"] is None
    assert sha256_file(src) == before
    loaded = CostModel.load(a["out_dir"], cfg)
    hours = pd.date_range("2021-07-18", periods=168, freq="h", tz="UTC")
    assert (loaded.lookup(hours)["spread_pips"] > 0).all()
    with pytest.raises(FileExistsError):
        run(tmp_path, out_dir=Path("out/a"))


def test_stats_quantiles(cfg):
    s = stats(pd.DataFrame({"file": ["a", "a", "b", "b"], "spread_pips": [0.1, 0.2, 0.3, 0.4]}), cfg)
    assert (s["n_minutes"], s["n_weeks"], s["median"], s["p90"]) == (4, 2, 0.25, 0.37)


@pytest.fixture
def varied(cfg):
    """Model whose spreads vary within every cell, so median < p75 < p90 everywhere."""
    cycle = [0.1, 0.2, 0.3, 0.5, 0.8, 1.3, 2.1]
    weeks = [week(s, lambda ny: [cycle[i % len(cycle)] for i in range(len(ny))])
             for s in ("2021-01-10", "2021-01-17", "2021-07-11", "2021-07-18", "2021-07-25")]
    built = build(minute_spreads(pd.concat(weeks, ignore_index=True), cfg), cfg)
    return CostModel(built["hour_of_week"], built["segments"], built["fallback"], cfg)


def test_cost_is_at_least_commission_plus_slippage(cfg, varied):
    tc = cfg["trading_costs"]
    hours = pd.date_range("2021-07-25", periods=7 * 24 * 4, freq="15min", tz="UTC")
    for q in ("median", "p75", "p90", None):
        out = varied.cost_for(hours, q)
        assert (out["total_pips"] >= tc["commission_pips_round_trip"] + tc["slippage_pips"] + cfg["floor_pips"] - 1e-12).all()
        assert (out["total_pips"] - out["spread_pips"] - out["commission_pips"] - out["slippage_pips"]).abs().max() < 1e-12


def test_cost_changes_with_percentile(cfg, varied):
    t = pd.DatetimeIndex(["2021-07-28 12:00", "2021-07-28 21:30", "2021-08-01 21:10"], tz="UTC")
    med, p75, p90 = (varied.cost_for(t, q)["total_pips"] for q in ("median", "p75", "p90"))
    assert (med < p75).all() and (p75 < p90).all()
    assert varied.cost_for(t)["percentile"].eq(cfg["trading_costs"]["spread_percentile"]).all()  # config default
    assert (varied.cost_for(t)["total_pips"] == p75).all()
    with pytest.raises(ValueError):
        varied.cost_for(t, "p99")


def test_cost_for_flags_and_scalar(varied):
    t = pd.DatetimeIndex(["2021-07-28 12:00", "2021-07-28 21:30", "2021-08-01 21:10", "2021-08-01 23:30",
                          "2021-07-31 12:00"], tz="UTC")
    out = varied.cost_for(t)
    assert out["is_rollover"].tolist() == [False, True, False, False, False]
    assert out["is_weekly_open"].tolist() == [False, False, True, True, False]
    assert out["is_market_closed"].tolist() == [False, False, False, False, True]
    one = varied.cost_for(pd.Timestamp("2021-07-28 21:30", tz="UTC"))
    assert isinstance(one, dict) and one["is_rollover"] and one["total_pips"] == out["total_pips"].iloc[1]
    with pytest.raises(TypeError):
        varied.cost_for(pd.Timestamp("2021-07-28 21:30"))  # naive time: no guessing of the timezone
