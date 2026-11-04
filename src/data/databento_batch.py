"""Databento batch jobs for trades 2020-2023: one job per year, split by month, under a hard cap.

    python -m src.data.databento_batch --approved

Jobs go one at a time. The next job is sent only after the previous one is done and its cost_usd is inside the cap.
A job is written to manifest.json before it is sent, and a restart reuses the stored job id, so a year is never
submitted twice. Downloads run after the jobs: they are free to repeat for 30 days and the client resumes partial
files. Files are only hashed and counted, not decoded into bars.
"""

import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.data.databento_cost_estimate import check_query, load_key
from src.data.databento_download import (
    DATASET, MANIFEST, OUT_DIR, STYPE_IN, SYMBOL, StopDownload, count_dbn_records, load_manifest, save_manifest,
    sha256_of, utc_now,
)

YEARS = [2020, 2021, 2022, 2023]
CAP_USD = 110.0
PORTAL_USD = 27.30           # read by the owner on the Databento portal, included in the cap
TAIL_USD = 1.21              # trades 2019 tail, bought after that reading
SPENT_BEFORE_USD = PORTAL_USD + TAIL_USD
POLL_SECONDS = 30
MAX_POLLS = 1440             # 12 hours
MAX_POLL_ERRORS = 20
MAX_DOWNLOAD_TRIES = 5
CONDITION_START, CONDITION_END = "2015-01-01", "2023-12-31"
TRADES_FROM = "2019-01-01"   # first day covered by the trades files


def request(year: int) -> dict:
    return {"id": f"trades_{year}", "schema": "trades", "start": f"{year}-01-01", "end": f"{year + 1}-01-01"}


def query_args(year: int) -> dict:
    r = request(year)
    check_query(r)
    return dict(dataset=DATASET, symbols=SYMBOL, stype_in=STYPE_IN, schema=r["schema"], start=r["start"], end=r["end"])


def job_args(year: int) -> dict:
    return {**query_args(year), "split_duration": "month", "encoding": "dbn", "compression": "zstd", "delivery": "download"}


def spent_usd(manifest: dict) -> float:
    """Real cost_usd once known, otherwise the quote: a job that was sent is money committed."""
    jobs = manifest.get("batch_jobs", {}).values()
    return SPENT_BEFORE_USD + sum(j["cost_usd"] if j.get("cost_usd") is not None else j["quoted_usd"] for j in jobs)


def matching_job(client, year: int) -> dict | None:
    """list_jobs returns only id, state and time, so each job's details are read to compare its parameters."""
    a = query_args(year)
    listed = client.batch.list_jobs(states="queued,processing,done,expired")
    jobs = [client.batch.get_job_details(j["id"]) for j in listed]
    same = [j for j in jobs if j.get("dataset") == DATASET and j.get("schema") == "trades" and SYMBOL in str(j.get("symbols"))
            and j.get("start") and pd.Timestamp(j["start"]) == pd.Timestamp(a["start"], tz="UTC")
            and pd.Timestamp(j["end"]) == pd.Timestamp(a["end"], tz="UTC")]
    if len(same) > 1:
        raise StopDownload(f"{len(same)} jobs already exist for {year}; the owner must look at them")
    return same[0] if same else None


def submit(client, year: int, manifest: dict, root: Path) -> None:
    """Send the job for `year` unless it is already known. Stops before anything that would pass the cap."""
    jobs = manifest.setdefault("batch_jobs", {})
    key = str(year)
    entry = jobs.get(key)
    if entry and entry.get("job_id"):
        return
    if entry:                                             # intent saved, crash before the id was stored
        found = matching_job(client, year)
        if found:
            entry["job_id"] = found["id"]
            save_manifest(root / MANIFEST, manifest)
            return
        del jobs[key]
    args = query_args(year)
    usd, records = float(client.metadata.get_cost(**args)), int(client.metadata.get_record_count(**args))
    spent = spent_usd(manifest)
    if spent + usd > CAP_USD:
        save_manifest(root / MANIFEST, manifest)
        raise StopDownload(f"trades {year}: ${spent:.2f} + ${usd:.2f} would pass the ${CAP_USD:.2f} cap; job not sent")
    jobs[key] = {"year": year, "job_id": None, "quoted_usd": usd, "expected_records": records, "cost_usd": None,
                 "status": "submitting", "submitted": utc_now()}
    save_manifest(root / MANIFEST, manifest)              # on disk before any money is spent
    jobs[key]["job_id"] = client.batch.submit_job(**job_args(year))["id"]
    jobs[key]["status"] = "submitted"
    save_manifest(root / MANIFEST, manifest)


def wait_done(client, entry: dict, sleep=time.sleep) -> dict:
    errors = 0
    for _ in range(MAX_POLLS):
        try:
            job = client.batch.get_job_details(entry["job_id"])
            errors = 0
        except Exception as e:
            errors += 1
            if errors > MAX_POLL_ERRORS or getattr(e, "http_status", None) in (401, 403):
                raise
            sleep(POLL_SECONDS)
            continue
        if job.get("state") == "expired":
            raise StopDownload(f"job {entry['job_id']} expired")
        if job.get("state") == "done":
            return job
        sleep(POLL_SECONDS)
    raise StopDownload(f"job {entry['job_id']} was not done after {MAX_POLLS} checks")


def record_cost(entry: dict, job: dict, manifest: dict, root: Path) -> None:
    """Stops when the cost is missing or the cap is passed, so the next job is not sent."""
    entry.update(status="done", job_record_count=job.get("record_count"), billed_size=job.get("billed_size"))
    if job.get("cost_usd") is None:
        save_manifest(root / MANIFEST, manifest)
        raise StopDownload(f"job {entry['job_id']} is done but has no cost_usd; next job not sent")
    entry["cost_usd"] = float(job["cost_usd"])
    save_manifest(root / MANIFEST, manifest)
    if spent_usd(manifest) > CAP_USD:
        raise StopDownload(f"spent ${spent_usd(manifest):.2f} is over the ${CAP_USD:.2f} cap; next job not sent")


def run_jobs(client, manifest: dict, root: Path, sleep=time.sleep) -> None:
    for year in YEARS:
        submit(client, year, manifest, root)
        entry = manifest["batch_jobs"][str(year)]
        if entry.get("cost_usd") is None:
            record_cost(entry, wait_done(client, entry, sleep), manifest, root)


def verify_files(job_dir: Path, listing: list[dict], entry: dict, count=count_dbn_records) -> dict:
    """Check every listed file against Databento's hash, then the total record count. Raises before anything moves."""
    files = {}
    for f in listing:
        path = job_dir / f["filename"]
        if not path.exists():
            raise StopDownload(f"{f['filename']} of job {entry['job_id']} is missing")
        digest = sha256_of(path)
        if digest != f["hash"].partition(":")[2]:
            raise StopDownload(f"{f['filename']} of job {entry['job_id']} failed its SHA-256 check")
        item = {"sha256": digest, "size_bytes": path.stat().st_size}
        if f["filename"].endswith(".dbn.zst"):
            records, schema, dataset = count(path)
            if schema != "trades" or dataset != DATASET:
                raise StopDownload(f"{f['filename']} holds {schema} from {dataset}")
            item["records"] = records
        files[f["filename"]] = item
    total = sum(i.get("records", 0) for i in files.values())
    if total != entry["expected_records"]:
        raise StopDownload(f"trades {entry['year']}: expected {entry['expected_records']:,} records, found {total:,}")
    return files


def fetch_year(client, entry: dict, manifest: dict, root: Path, count=count_dbn_records, sleep=time.sleep) -> None:
    if entry.get("status") == "verified":
        return
    year_dir = root / OUT_DIR / "trades" / str(entry["year"])
    job_dir = year_dir / entry["job_id"]
    for attempt in range(1, MAX_DOWNLOAD_TRIES + 1):
        try:
            client.batch.download(entry["job_id"], output_dir=year_dir)
            break
        except Exception as e:
            if attempt == MAX_DOWNLOAD_TRIES or getattr(e, "http_status", None) in (401, 403):
                raise
            sleep(POLL_SECONDS)
    listing = client.batch.list_files(entry["job_id"])
    files = verify_files(job_dir, listing, entry, count)
    for name in files:
        os.replace(job_dir / name, year_dir / name)
    if not any(job_dir.iterdir()):
        job_dir.rmdir()
    entry.update(status="verified", files=files, records=sum(i.get("records", 0) for i in files.values()), finished=utc_now())
    save_manifest(root / MANIFEST, manifest)


def bad_days(rows: list[dict]) -> pd.DataFrame:
    """Every day whose condition is not 'available', with what we hold for it."""
    t = pd.DataFrame([r for r in rows if r["condition"] != "available"], columns=["date", "condition", "last_modified_date"])
    t["files"] = ["ohlcv-1m + trades" if d >= TRADES_FROM else "ohlcv-1m" for d in t["date"]]
    return t.sort_values("date", ignore_index=True)


def render_report(manifest: dict, status: str, days: pd.DataFrame, n_days: int, generated: str) -> str:
    jobs = manifest.get("batch_jobs", {})
    lines = ["# Databento batch jobs: trades 2020-2023", "", f"Generated {generated}. **Status: {status}**", "",
             f"Dataset `{DATASET}`, symbols `{SYMBOL}`, stype_in `{STYPE_IN}`, split_duration `month`, one job per year. "
             f"Files are in `{OUT_DIR}/trades/<year>/`; hashes and counts are in `{OUT_DIR}/manifest.json`. Files were "
             "only hashed and counted, not decoded into bars.", "",
             "| year | job | records | expected | match | files | size (MB) | quoted ($) | cost_usd ($) | status |",
             "|---:|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for y in sorted(jobs):
        j = jobs[y]
        f = j.get("files", {})
        rec = j.get("records")
        cost = f"{j['cost_usd']:.2f}" if j.get("cost_usd") is not None else "n/a"
        lines.append(f"| {y} | `{j.get('job_id')}` | {rec if rec is None else format(rec, ',')} | {j['expected_records']:,} | "
                     f"{'yes' if rec == j['expected_records'] else 'no'} | {sum(n.endswith('.dbn.zst') for n in f)} | "
                     f"{sum(i['size_bytes'] for i in f.values()) / 1e6:.1f} | {j['quoted_usd']:.2f} | {cost} | {j['status']} |")
    lines += ["", f"Spent: ${PORTAL_USD:.2f} (portal reading by the owner) + ${TAIL_USD:.2f} (trades 2019 tail) + these jobs = "
                  f"**${spent_usd(manifest):.2f}** of the ${CAP_USD:.2f} cap. Jobs use cost_usd; a job without it uses its quote.", "",
              "## Days that are not fully available", "",
              f"`metadata.get_dataset_condition`, {CONDITION_START} to {CONDITION_END}: {len(days)} of {n_days} days. These "
              "conditions are for the whole dataset, not for 6E alone. `files` says what we hold for that day.", "",
              "| date | condition | last modified | files |", "|---|---|---|---|"]
    lines += [f"| {d['date']} | {d['condition']} | {d['last_modified_date']} | {d['files']} |" for _, d in days.iterrows()]
    return "\n".join(lines + [""])


def main(argv=None) -> None:
    import databento

    p = argparse.ArgumentParser()
    p.add_argument("--approved", action="store_true")
    if not p.parse_args(argv).approved:
        raise SystemExit("not approved")
    root = Path(".")
    key = load_key(root / ".env")
    client = databento.Historical(key)
    manifest = load_manifest(root / MANIFEST)
    status = "complete"
    try:
        try:
            run_jobs(client, manifest, root)
        except StopDownload as e:
            status = f"stopped: {e}"
        for entry in manifest.get("batch_jobs", {}).values():
            if entry.get("cost_usd") is not None:
                try:
                    fetch_year(client, entry, manifest, root)
                except StopDownload as e:
                    entry["status"] = f"failed checks: {e}"
                    save_manifest(root / MANIFEST, manifest)
                    status = f"stopped: {e}"
        rows = client.metadata.get_dataset_condition(DATASET, CONDITION_START, CONDITION_END)
        days = bad_days(rows)
        now = datetime.now(timezone.utc)
        out = root / "reports" / f"databento_download_batch1_jobs_{now.strftime('%Y%m%dT%H%M%SZ')}"
        out.mkdir(parents=True, exist_ok=False)
        text = render_report(manifest, status, days, len(rows), now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        if key in text:
            raise RuntimeError("key found in report output")
        (out / "summary.md").write_text(text, encoding="utf-8")
        print(status, out)
    except Exception as e:  # keep the key out of any traceback text
        raise SystemExit(f"{type(e).__name__}: {str(e).replace(key, '[redacted]')}") from None


if __name__ == "__main__":
    main()
