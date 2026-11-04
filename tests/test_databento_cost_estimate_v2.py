"""Tests for the Databento cost estimate v2. No network; the metadata client is a stub."""

from pathlib import Path

import pytest

from src.data import databento_cost_estimate_v2 as d


class Err(Exception):
    def __init__(self, status):
        super().__init__("rejected")
        self.http_status = status


class Meta:
    def __init__(self, outcome):
        self.outcome = outcome

    def get_record_count(self, **k):
        r = self.outcome[k["symbols"]]
        if isinstance(r, Exception):
            raise r
        return r


def years(prices):
    return {y: {"usd": p, "records": 100 + y, "bytes": 10**9} for y, p in zip(d.YEARS, prices)}


def test_symbol_prefers_volume_and_falls_back_only_on_rejection():
    assert d.choose_symbol(Meta({"6E.v.0": 5}), client_error=Err)[0] == "6E.v.0"
    s, log = d.choose_symbol(Meta({"6E.v.0": Err(422), "6E.c.0": 5}), client_error=Err)
    assert s == "6E.c.0" and log[0]["ok"] is False
    assert d.choose_symbol(Meta({"6E.v.0": 0, "6E.c.0": 5}), client_error=Err)[0] == "6E.c.0"
    with pytest.raises(Err):
        d.choose_symbol(Meta({"6E.v.0": Err(401), "6E.c.0": 5}), client_error=Err)
    with pytest.raises(RuntimeError, match="no symbol"):
        d.choose_symbol(Meta({"6E.v.0": 0, "6E.c.0": 0}), client_error=Err)


def test_all_queries_stay_before_test_period():
    for q in [d.FULL_OHLCV, d.FULL_TRADES] + [d.year_query(y) for y in d.YEARS]:
        assert d.request_args(q, "6E.v.0")["end"] <= "2024-01-01"


def test_source_has_no_download_calls():
    src = Path(d.__file__).read_text(encoding="utf-8")
    for banned in ("timeseries", "batch.", "get_range(", "submit_job"):
        assert banned not in src


def test_options_require_validation_three_train_years_and_reserve():
    ohlcv = {"usd": 10.0, "bytes": 10**9}
    t = d.options(ohlcv, years([20.0] * 9))              # base 50, budget 110: exactly 3 train years, left = 15
    assert len(t) == 35 and (t["n_train"] == 3).all() and t["left_usd"].min() == pytest.approx(15.0)
    assert t.iloc[0]["train_years"] == (2019, 2020, 2021)
    assert d.options(ohlcv, years([21.0] * 9)).empty     # 3 train years leave only 12


def test_options_prefer_more_years_over_block():
    y = years([5, 5, 5, 5, 30, 30, 10, 10, 10])          # train budget 80: the block 2019-2021 fits, six years beat it
    t = d.options({"usd": 10.0, "bytes": 1}, y)
    assert t.iloc[0]["train_years"] == (2015, 2016, 2017, 2018, 2020, 2021)
    assert ((t["n_train"] == 3) & t["block_to_2021"]).any()
    assert not (t["n_train"] == 7).any()


def test_next_step_uses_cheapest_train_years():
    y = years([5, 5, 5, 5, 30, 30, 10, 10, 10])
    assert d.next_step_usd({"usd": 10.0}, y, 5) == pytest.approx(60.0)


def test_saving():
    assert d.saving(50.0, 200.0) == pytest.approx(75.0)
