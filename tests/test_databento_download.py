"""Tests for the batch 1 downloader. No network; client and record counter are stubs, files hold dummy bytes."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.data import databento_download as d

PRICE = 10.0
PRICES = {r["id"]: PRICE for r in d.REQUESTS}


class Client:
    def __init__(self, prices=None, records=10, fail_on=None):
        self.prices, self.records, self.fail_on, self.calls = dict(prices or PRICES), records, fail_on, []
        self.metadata = SimpleNamespace(get_cost=self.cost, get_record_count=lambda **k: records)
        self.timeseries = SimpleNamespace(get_range=self.get_range)

    def _id(self, k):
        return next(r["id"] for r in d.REQUESTS if r["schema"] == k["schema"] and r["start"] == k["start"])

    def cost(self, **k):
        return self.prices[self._id(k)]

    def get_range(self, path, **k):
        rid = self._id(k)
        self.calls.append(rid)
        Path(path).write_bytes(b"partial" if rid == self.fail_on else rid.encode())
        if rid == self.fail_on:
            raise ConnectionError("dropped")


def counter(n=10):
    def count(path):
        schema = Path(path).parent.name
        return n, schema, d.DATASET
    return count


@pytest.fixture
def root(tmp_path):
    (tmp_path / d.APPROVAL).parent.mkdir(parents=True)
    (tmp_path / d.APPROVAL).write_text("approved table", encoding="utf-8")
    return tmp_path


def test_only_the_approved_requests():
    assert [(r["schema"], r["start"], r["end"]) for r in d.REQUESTS] == [("ohlcv-1m", "2015-01-01", "2024-01-01")] + [
        ("trades", f"{y}-01-01", f"{y + 1}-01-01") for y in range(2019, 2024)]
    assert all(d.request_args(r)["symbols"] == "6E.v.0" and d.request_args(r)["stype_in"] == "continuous" for r in d.REQUESTS)
    assert d.CAP_USD == 102.0


def test_refuses_without_approval_or_approval_file(root):
    c = Client()
    with pytest.raises(d.StopDownload, match="not approved"):
        d.download(root, c)
    (root / d.APPROVAL).unlink()
    with pytest.raises(d.StopDownload, match="missing"):
        d.download(root, c, approved=True, count=counter())
    assert c.calls == []


def test_full_run_writes_manifest_and_files(root):
    m = d.download(root, Client(), approved=True, count=counter())
    assert set(m["files"]) == {r["id"] for r in d.REQUESTS}
    e = m["files"]["trades_2019"]
    f = root / d.OUT_DIR / "trades/2019.dbn.zst"
    assert f.exists() and e["sha256"] == d.sha256_of(f) and e["records"] == 10 and e["size_bytes"] == f.stat().st_size
    assert (root / d.OUT_DIR / "ohlcv-1m/2015-2023.dbn.zst").exists()
    assert not list((root / d.OUT_DIR).rglob("*.part"))


def test_planned_total_over_cap_spends_nothing(root):
    c = Client({**PRICES, "trades_2023": 60.0})
    with pytest.raises(d.StopDownload, match="over the"):
        d.download(root, c, approved=True, count=counter())
    assert c.calls == []


def test_price_rise_during_run_stops_before_passing_cap(root):
    c = Client()
    real = c.get_range

    def rising(path, **k):
        real(path, **k)
        if len(c.calls) == 2:
            c.prices["trades_2020"] = 95.0
    c.timeseries.get_range = rising
    with pytest.raises(d.StopDownload, match="would pass"):
        d.download(root, c, approved=True, count=counter())
    assert c.calls == ["ohlcv-1m_2015-2023", "trades_2019"]


def test_interrupted_run_resumes_and_counts_the_failed_attempt(root):
    c = Client(fail_on="trades_2020")
    with pytest.raises(ConnectionError):
        d.download(root, c, approved=True, count=counter())
    m = d.load_manifest(root / d.MANIFEST)
    assert m["attempts"][-1]["status"] == "started" and "trades_2020" not in m["files"]
    assert d.committed_usd(m) == pytest.approx(3 * PRICE)
    c2 = Client()
    m2 = d.download(root, c2, approved=True, count=counter())
    assert c2.calls == ["trades_2020", "trades_2021", "trades_2022", "trades_2023"]  # finished files are not re-requested
    assert d.committed_usd(m2) == pytest.approx(7 * PRICE)


def test_failed_attempts_count_against_cap_on_resume(root):
    prices = {r["id"]: 15.0 for r in d.REQUESTS}
    c = Client(prices, fail_on="trades_2023")
    with pytest.raises(ConnectionError):
        d.download(root, c, approved=True, count=counter())             # 6 x 15 = 90 committed
    c2 = Client(prices)
    with pytest.raises(d.StopDownload, match="over the"):
        d.download(root, c2, approved=True, count=counter())            # 90 + 15 > 102
    assert c2.calls == []


def test_count_mismatch_stops_and_blocks_paying_again(root):
    c = Client()
    with pytest.raises(d.StopDownload, match="expected 10"):
        d.download(root, c, approved=True, count=counter(9))
    assert c.calls == ["ohlcv-1m_2015-2023"]
    assert not (root / d.OUT_DIR / "ohlcv-1m/2015-2023.dbn.zst").exists()
    assert (root / d.OUT_DIR / "ohlcv-1m/2015-2023.dbn.zst.part").exists()
    with pytest.raises(d.StopDownload, match="kept for the owner"):
        d.download(root, c, approved=True, count=counter())
    assert c.calls == ["ohlcv-1m_2015-2023"]


def test_changed_or_unknown_file_is_never_overwritten(root):
    d.download(root, Client(), approved=True, count=counter())
    f = root / d.OUT_DIR / "trades/2021.dbn.zst"
    f.write_bytes(b"changed")
    c = Client()
    with pytest.raises(d.StopDownload, match="does not match"):
        d.download(root, c, approved=True, count=counter())
    assert c.calls == [] and f.read_bytes() == b"changed"


def test_stray_file_not_in_manifest_stops(root):
    f = root / d.OUT_DIR / "trades/2019.dbn.zst"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"stray")
    with pytest.raises(d.StopDownload, match="not in the manifest"):
        d.download(root, Client(), approved=True, count=counter())


def partial_root(root):
    f = root / d.OUT_DIR / d.PARTIAL_FILE
    f.parent.mkdir(parents=True)
    f.write_bytes(b"partial bytes")
    d.save_manifest(root / d.MANIFEST, {**d.load_manifest(root / d.MANIFEST), "attempts": [
        {"id": "trades_2019", "usd": 16.0, "expected_records": 20, "started": "t", "status": "started"}]})
    return f


class TailClient(Client):
    def _id(self, k):
        return d.TAIL_REQUEST["id"] if k["start"] == d.TAIL_REQUEST["start"] else super()._id(k)

    def cost(self, **k):
        return 1.2


def test_tail_keeps_part_file_records_it_and_blocks_the_old_plan(root):
    f = partial_root(root)
    before = f.read_bytes()
    c = TailClient()
    m = d.download_tail(root, c, approved=True, count=counter())
    assert c.calls == ["trades_2019_tail"] and f.read_bytes() == before
    assert m["partial"]["trades_2019"]["sha256"] == d.sha256_of(f)
    assert [a["status"] for a in m["attempts"]] == ["interrupted", "ok"]
    assert (root / d.OUT_DIR / d.TAIL_REQUEST["file"]).exists()
    assert d.committed_usd(m) == pytest.approx(17.2)
    d.download_tail(root, c, approved=True, count=counter())           # already done: no second request
    assert c.calls == ["trades_2019_tail"]
    with pytest.raises(d.StopDownload, match="plan changed"):
        d.download(root, Client(), approved=True, count=counter())


def test_tail_needs_approval(root):
    with pytest.raises(d.StopDownload, match="not approved"):
        d.download_tail(root, TailClient())


def test_approval_lists_every_request_and_total():
    text = d.render_approval({r["id"]: {"usd": 10.0, "records": 5} for r in d.REQUESTS}, "2026-11-04T00:00:00Z")
    assert "**Total: $60.00**" in text and all(r["file"] in text for r in d.REQUESTS) and "$102.00" in text
