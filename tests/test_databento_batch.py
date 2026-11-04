"""Tests for the batch job runner. No network; the client is a stub and files hold dummy bytes."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.data import databento_batch as b
from src.data.databento_download import MANIFEST, OUT_DIR, StopDownload, load_manifest


class Client:
    def __init__(self, cost=18.0, quote=18.0, records=10, states=("done",), missing_cost=False, corrupt=False):
        self.cost, self.quote, self.records, self.states = cost, quote, records, list(states)
        self.missing_cost, self.corrupt = missing_cost, corrupt
        self.sent, self.jobs, self.downloads = [], {}, []
        self.metadata = SimpleNamespace(get_cost=lambda **k: self.quote, get_record_count=lambda **k: self.records)
        self.batch = SimpleNamespace(submit_job=self.submit_job, list_jobs=self.list_jobs,
                                     get_job_details=self.details, download=self.download, list_files=self.list_files)

    def submit_job(self, **k):
        job_id = f"JOB-{k['start'][:4]}"
        self.sent.append(k)
        self.jobs[job_id] = {"id": job_id, "state": "queued", "dataset": k["dataset"], "schema": k["schema"],
                             "symbols": [k["symbols"]], "start": f"{k['start']}T00:00:00Z", "end": f"{k['end']}T00:00:00Z"}
        return self.jobs[job_id]

    def list_jobs(self, states=None):                  # the real API returns only these three fields
        return [{"id": j["id"], "state": j["state"], "ts_received": "t"} for j in self.jobs.values()]

    def details(self, job_id):
        j = self.jobs[job_id]
        j["state"] = self.states.pop(0) if self.states else "done"
        j["record_count"] = self.records
        if not self.missing_cost:
            j["cost_usd"] = self.cost
        return dict(j)

    def download(self, job_id, output_dir):
        self.downloads.append(job_id)
        d = Path(output_dir) / job_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "a.trades.dbn.zst").write_bytes(job_id.encode())
        (d / "condition.json").write_bytes(b"{}")

    def list_files(self, job_id):
        good = "wrong" if self.corrupt else hashlib.sha256(job_id.encode()).hexdigest()
        return [{"filename": "a.trades.dbn.zst", "hash": f"sha256:{good}"},
                {"filename": "condition.json", "hash": "sha256:" + hashlib.sha256(b"{}").hexdigest()}]


def count(path):
    return 10, "trades", b.DATASET


def nosleep(_):
    pass


def test_job_arguments_are_exact():
    a = b.job_args(2021)
    assert a == {"dataset": "GLBX.MDP3", "symbols": "6E.v.0", "stype_in": "continuous", "schema": "trades",
                 "start": "2021-01-01", "end": "2022-01-01", "split_duration": "month", "encoding": "dbn",
                 "compression": "zstd", "delivery": "download"}
    assert b.YEARS == [2020, 2021, 2022, 2023] and b.CAP_USD == 110.0 and b.SPENT_BEFORE_USD == pytest.approx(28.51)


def test_one_job_per_year_and_restart_never_resubmits(tmp_path):
    c = Client()
    m = load_manifest(tmp_path / MANIFEST)
    b.run_jobs(c, m, tmp_path, nosleep)
    assert [s["start"] for s in c.sent] == ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01"]
    b.run_jobs(c, load_manifest(tmp_path / MANIFEST), tmp_path, nosleep)
    assert len(c.sent) == 4


def test_next_job_waits_for_previous_job_to_finish(tmp_path):
    c = Client(states=("queued", "processing", "done"))
    seen = []
    real = c.submit_job
    c.batch.submit_job = lambda **k: (seen.append(all(j["state"] == "done" for j in c.jobs.values())), real(**k))[1]
    b.run_jobs(c, load_manifest(tmp_path / MANIFEST), tmp_path, nosleep)
    assert seen == [True, True, True, True]


def test_quote_over_cap_sends_nothing(tmp_path):
    c = Client(quote=90.0)
    with pytest.raises(StopDownload, match="would pass"):
        b.run_jobs(c, load_manifest(tmp_path / MANIFEST), tmp_path, nosleep)
    assert c.sent == []


def test_real_cost_over_cap_stops_next_job(tmp_path):
    c = Client(cost=85.0)
    with pytest.raises(StopDownload, match="over the"):
        b.run_jobs(c, load_manifest(tmp_path / MANIFEST), tmp_path, nosleep)
    assert len(c.sent) == 1


def test_missing_cost_stops_next_job(tmp_path):
    c = Client(missing_cost=True)
    with pytest.raises(StopDownload, match="no cost_usd"):
        b.run_jobs(c, load_manifest(tmp_path / MANIFEST), tmp_path, nosleep)
    assert len(c.sent) == 1


def test_later_quote_stops_on_real_spend(tmp_path):
    c = Client(cost=30.0, quote=30.0)                  # 28.51 + 60 spent; a third job would reach 118.51
    with pytest.raises(StopDownload, match="would pass"):
        b.run_jobs(c, load_manifest(tmp_path / MANIFEST), tmp_path, nosleep)
    assert len(c.sent) == 2


def test_crash_after_send_adopts_job_instead_of_resending(tmp_path):
    c = Client()
    c.submit_job(**b.job_args(2020))
    m = load_manifest(tmp_path / MANIFEST)
    m["batch_jobs"] = {"2020": {"year": 2020, "job_id": None, "quoted_usd": 18.0, "expected_records": 10,
                                "cost_usd": None, "status": "submitting"}}
    b.submit(c, 2020, m, tmp_path)
    assert m["batch_jobs"]["2020"]["job_id"] == "JOB-2020" and len(c.sent) == 1


def test_crash_before_send_sends_once(tmp_path):
    c = Client()
    m = load_manifest(tmp_path / MANIFEST)
    m["batch_jobs"] = {"2020": {"year": 2020, "job_id": None, "quoted_usd": 18.0, "expected_records": 10,
                                "cost_usd": None, "status": "submitting"}}
    b.submit(c, 2020, m, tmp_path)
    assert len(c.sent) == 1


def test_expired_job_stops(tmp_path):
    c = Client(states=("expired",))
    with pytest.raises(StopDownload, match="expired"):
        b.run_jobs(c, load_manifest(tmp_path / MANIFEST), tmp_path, nosleep)


def test_polling_survives_short_outage():
    calls = []

    def flaky(job_id):
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("dropped")
        return {"id": job_id, "state": "done"}
    c = SimpleNamespace(batch=SimpleNamespace(get_job_details=flaky))
    assert b.wait_done(c, {"job_id": "J"}, nosleep)["state"] == "done"


def done_entry(tmp_path, c):
    m = load_manifest(tmp_path / MANIFEST)
    b.run_jobs(c, m, tmp_path, nosleep)
    return m, m["batch_jobs"]["2020"]


def test_files_land_in_year_folder_with_hash_and_count(tmp_path):
    c = Client()
    m, e = done_entry(tmp_path, c)
    b.fetch_year(c, e, m, tmp_path, count, nosleep)
    y = tmp_path / OUT_DIR / "trades/2020"
    assert (y / "a.trades.dbn.zst").exists() and (y / "condition.json").exists() and not (y / "JOB-2020").exists()
    saved = load_manifest(tmp_path / MANIFEST)["batch_jobs"]["2020"]
    assert saved["status"] == "verified" and saved["records"] == 10
    assert saved["files"]["a.trades.dbn.zst"]["sha256"] == hashlib.sha256(b"JOB-2020").hexdigest()
    b.fetch_year(c, e, m, tmp_path, count, nosleep)
    assert c.downloads == ["JOB-2020"]


def test_hash_failure_keeps_file_in_job_folder(tmp_path):
    c = Client(corrupt=True)
    m, e = done_entry(tmp_path, c)
    with pytest.raises(StopDownload, match="SHA-256"):
        b.fetch_year(c, e, m, tmp_path, count, nosleep)
    assert (tmp_path / OUT_DIR / "trades/2020/JOB-2020/a.trades.dbn.zst").exists()
    assert e["status"] != "verified"


def test_record_mismatch_stops(tmp_path):
    c = Client()
    m, e = done_entry(tmp_path, c)
    e["expected_records"] = 11
    with pytest.raises(StopDownload, match="expected 11"):
        b.fetch_year(c, e, m, tmp_path, count, nosleep)


def test_bad_days_lists_all_non_available_and_marks_files():
    t = b.bad_days([{"date": "2019-01-15", "condition": "degraded", "last_modified_date": "x"},
                    {"date": "2017-11-13", "condition": "missing", "last_modified_date": "x"},
                    {"date": "2019-01-16", "condition": "available", "last_modified_date": "x"}])
    assert t["date"].tolist() == ["2017-11-13", "2019-01-15"]
    assert t["files"].tolist() == ["ohlcv-1m", "ohlcv-1m + trades"]
