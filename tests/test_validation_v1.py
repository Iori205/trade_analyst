"""Tests for the one-time validation runner. Synthetic data in a temporary root only (prices in the 2.x range)."""

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn")

from src.backtest.engine import log_trial  # noqa: E402
from src.data.inventory import sha256_file  # noqa: E402
from src.research import validation_v1 as v  # noqa: E402
from tests.test_backtest_engine import StubCost  # noqa: E402

SPLITS = ('splits:\n  train: {start: "2015-01-01", end: "2021-12-31"}\n'
          '  validation: {start: "2022-01-01", end: "2023-12-31", exclude_flags: [low_quality_period]}\n'
          '  test: {start: "2024-01-01", end: "2026-08-31", locked: true}\n')


def synth_root(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "config").mkdir()
    (root / "config/splits.yaml").write_text(SPLITS, encoding="utf-8")
    rng = np.random.default_rng(0)
    # M1 from 2021-06 to 2022-06 (enough to train on late 2021 and validate early 2022)
    t = pd.date_range("2021-06-01", "2022-05-31 23:59", freq="min", tz="UTC")
    t = t[t.dayofweek < 5]
    c = 2.1 + np.cumsum(rng.normal(0, 0.00005, len(t)))
    m1 = pd.DataFrame({"timestamp_utc": t, "open": c, "high": c + 0.00003, "low": c - 0.00003, "close": c,
                       "utc_unresolved": False, "low_quality_period": False})
    (root / "data/processed/eurusd_m1/v1").mkdir(parents=True)
    m1.to_parquet(root / "data/processed/eurusd_m1/v1/eurusd_m1_utc.parquet", index=False)
    s = m1.set_index("timestamp_utc")
    h1 = s.resample("h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
    h1 = h1.rename(columns={"timestamp_utc": "bar_start_utc"})
    h1["any_gap"], h1["any_flag"] = False, False
    bars = root / "data/processed/eurusd_bars/v1"
    bars.mkdir(parents=True)
    h1[h1["bar_start_utc"] < "2022-01-01"].to_parquet(bars / "eurusd_h1_train.parquet", index=False)
    h1[h1["bar_start_utc"] >= "2022-01-01"].to_parquet(bars / "eurusd_h1_validation.parquet", index=False)
    frozen = ["config/splits.yaml", "data/processed/eurusd_bars/v1/eurusd_h1_train.parquet"]
    table = "\n".join(f"| {p} | `{sha256_file(root / p)}` |" for p in frozen)
    (root / "docs").mkdir()
    (root / "docs/preregistration_validation_v1.md").write_text(f"# prereg\n\n| file | SHA-256 |\n|---|---|\n{table}\n")
    log_trial(root / "reports/trials/trials.csv", {
        "strategy": "preregistration_validation_v1",
        "params": json.dumps({"sha256": sha256_file(root / "docs/preregistration_validation_v1.md")})})
    return root


@pytest.fixture
def root(tmp_path, monkeypatch):
    r = synth_root(tmp_path)
    monkeypatch.setattr("src.backtest.engine.load_cost_config", lambda p: {"trading_costs": {"spread_percentile": "p75"}})
    monkeypatch.setattr("src.backtest.engine.CostModel.load", classmethod(lambda cls, d, cfg: StubCost(0.5)))
    monkeypatch.setattr(v, "CONTROL_RUNS", 20)
    return r


def test_frozen_table_parsing():
    text = "| a/b.py | `" + "0" * 64 + "` |\n| not a row |\n"
    assert v.frozen_hashes(text) == {"a/b.py": "0" * 64}


def test_guard_refuses_changed_prereg_or_frozen_file(root):
    v.check_guards(root)
    p = root / "docs/preregistration_validation_v1.md"
    p.write_text(p.read_text() + "edited\n")
    with pytest.raises(v.ValidationGuardError, match="does not match"):
        v.check_guards(root)


def test_guard_refuses_changed_frozen_file(root):
    (root / "config/splits.yaml").write_text(SPLITS + "# changed\n", encoding="utf-8")
    with pytest.raises(v.ValidationGuardError, match="frozen files changed"):
        v.check_guards(root)


def test_lock_is_single_use(root):
    v.acquire_lock(root, "x")
    with pytest.raises(v.ValidationGuardError, match="already run"):
        v.acquire_lock(root, "x")


def test_evaluate_criteria():
    t = pd.DataFrame({"entry_time": pd.to_datetime(["2022-03-01", "2022-04-01", "2023-09-01", "2023-10-01"] * 30, utc=True),
                      "net_pips": [5.0, 3.0, 4.0, 2.0] * 30})
    ev = v.evaluate_a(t, np.zeros(100))
    assert ev["passed"] and all(ev["criteria"].values())
    ev2 = v.evaluate_a(t.assign(net_pips=np.where(t["entry_time"].dt.year == 2023, -1.0, 6.0)), np.zeros(100))
    assert not ev2["criteria"]["4. expectancy >= 0 in 2022 and 2023"]
    only_2022 = t[t["entry_time"].dt.year == 2022]
    assert not v.evaluate_a(only_2022, np.zeros(100))["criteria"]["4. expectancy >= 0 in 2022 and 2023"]
    assert not v.evaluate_a(t, np.full(100, 10.0))["criteria"]["3. above control p95"]
    assert not v.evaluate_b(t.iloc[:0])["passed"]


def test_full_run_once_on_synthetic_data(root):
    r = v.run(root)
    out = r["out_dir"]
    assert (out / "summary.md").exists() and (out / "charts" / "control_distribution.png").exists()
    assert len(pd.read_csv(out / "control_a.csv")) == 20
    rows = list(csv.DictReader(open(root / "reports/trials/trials.csv")))
    assert [x["split"] for x in rows[1:]] == ["validation", "validation"]
    assert (r["a"]["trades"]["entry_time"] >= pd.Timestamp("2022-01-01", tz="UTC")).all()
    with pytest.raises(v.ValidationGuardError):
        v.run(root)                                   # the second run is refused
    assert len(list(csv.DictReader(open(root / "reports/trials/trials.csv")))) == 3
