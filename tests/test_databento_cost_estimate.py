"""Tests for the Databento cost estimate. No network; the metadata client is a stub."""

from pathlib import Path

import pytest

from src.data import databento_cost_estimate as d


def test_load_key_tolerates_indentation_and_never_shows_content(tmp_path):
    p = tmp_path / ".env"
    p.write_text('   DATABENTO_API_KEY=db-abc', encoding="utf-8")
    assert d.load_key(p) == "db-abc"
    p.write_text('export DATABENTO_API_KEY="db-abc"\n', encoding="utf-8")
    assert d.load_key(p) == "db-abc"
    p.write_text("OTHER=secret-value\n", encoding="utf-8")
    with pytest.raises(RuntimeError) as e:
        d.load_key(p)
    assert "secret-value" not in str(e.value)


def test_no_query_reaches_test_period():
    for q in d.QUERIES:
        d.check_query(q)
    with pytest.raises(ValueError, match="test period"):
        d.check_query({"id": "x", "end": "2024-01-02"})


def test_only_allowed_metadata_calls_in_source():
    src = Path(d.__file__).read_text(encoding="utf-8")
    for banned in ("timeseries", "batch.", "get_range(", "submit_job"):
        assert banned not in src


def test_estimate_uses_query_arguments():
    seen = []

    class Meta:
        def get_record_count(self, **k):
            seen.append(k)
            return 10

        def get_billable_size(self, **k):
            return 2_000_000_000

        def get_cost(self, **k):
            return 3.5

    r = d.estimate(Meta(), d.QUERIES[0])
    assert (r["records"], r["bytes"], r["usd"]) == (10, 2_000_000_000, 3.5)
    assert seen[0]["symbols"] == "6E.FUT" and seen[0]["stype_in"] == "parent" and seen[0]["end"] == "2024-01-01"


def test_combos_skip_overlap_and_mark_credit():
    res = [{"id": i, "usd": u, "bytes": 1} for i, u in zip("abcd", (10.0, 200.0, 30.0, 100.0))]
    t = d.combos(res, credit=125.0).set_index("combo")
    assert "b+c" not in t.index and "a+b+c" not in t.index
    assert bool(t.loc["a", "fits"]) and not bool(t.loc["a+c+d", "fits"]) and not bool(t.loc["b", "fits"])
    assert t.loc["a+d", "left_usd"] == pytest.approx(15.0)
