"""Databento batch 1 downloader: exact approved requests only, under a hard spending cap.

    python -m src.data.databento_download quote                 # free: writes docs/approvals/databento_batch1.md
    python -m src.data.databento_download download --approved   # costs money: only after the owner says yes
    python -m src.data.databento_download tail --approved       # costs money: the approved end of trades 2019

Each paid request is written to the ledger in manifest.json BEFORE it starts, so an interrupted request still counts
against the cap. Files are streamed to <name>.part and moved into place only after the checks pass. Finished files are
recognised by SHA-256 and never requested twice. Files are only counted, not decoded into bars.
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from src.data.databento_cost_estimate import check_query, load_key

DATASET = "GLBX.MDP3"
SYMBOL = "6E.v.0"
STYPE_IN = "continuous"
CAP_USD = 102.0
ESTIMATE_USD = 100.46
OUT_DIR = Path("data/raw/databento/6E_v0")
APPROVAL = Path("docs/approvals/databento_batch1.md")
MANIFEST = OUT_DIR / "manifest.json"


def _request(rid, schema, start, end, name):
    return {"id": rid, "schema": schema, "start": start, "end": end, "file": f"{schema}/{name}.dbn.zst"}


REQUESTS = [_request("ohlcv-1m_2015-2023", "ohlcv-1m", "2015-01-01", "2024-01-01", "2015-2023")] + [
    _request(f"trades_{y}", "trades", f"{y}-01-01", f"{y + 1}-01-01", str(y)) for y in range(2019, 2024)]


# Approved 2026-11-04 after trades_2019 broke at 92.5%. Kept apart from the part file; overlap is removed in processing.
TAIL_REQUEST = {"id": "trades_2019_tail", "schema": "trades", "start": "2019-11-22T09:00:00Z", "end": "2020-01-01",
                "file": "trades/2019_tail_from_20191122T0900Z.dbn.zst"}
PARTIAL_ID = "trades_2019"
PARTIAL_FILE = "trades/2019.dbn.zst.part"


class StopDownload(Exception):
    """The run stopped on purpose; nothing further is requested."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def request_args(r: dict) -> dict:
    check_query(r)
    return dict(dataset=DATASET, symbols=SYMBOL, stype_in=STYPE_IN, schema=r["schema"], start=r["start"], end=r["end"])


def quote(client, r: dict) -> dict:
    args = request_args(r)
    return {"usd": float(client.metadata.get_cost(**args)), "records": int(client.metadata.get_record_count(**args))}


def count_dbn_records(path: Path) -> tuple[int, str, str]:
    """Record count, schema and dataset, read in chunks only to verify the file. Nothing is written or kept."""
    import databento

    store = databento.DBNStore.from_file(path)
    return sum(len(a) for a in store.to_ndarray(count=1_000_000)), str(store.schema), str(store.dataset)


def load_manifest(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"dataset": DATASET, "symbol": SYMBOL, "stype_in": STYPE_IN, "cap_usd": CAP_USD, "files": {}, "attempts": []}


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def committed_usd(manifest: dict) -> float:
    """Everything requested so far, failed attempts included: a failed request may still have been billed."""
    return sum(a["usd"] for a in manifest["attempts"])


def is_done(root: Path, manifest: dict, r: dict) -> bool:
    entry = manifest["files"].get(r["id"])
    target = root / OUT_DIR / r["file"]
    if entry is None:
        if target.exists():
            raise StopDownload(f"{r['file']} exists but is not in the manifest; not touching it")
        return False
    if not target.exists():
        raise StopDownload(f"{r['file']} is in the manifest but missing; paying again needs the owner's decision")
    if sha256_of(target) != entry["sha256"]:
        raise StopDownload(f"{r['file']} does not match its SHA-256 in the manifest; not touching it")
    return True


def check_no_failed_checks(manifest: dict, todo: list[dict]) -> None:
    for r in todo:
        last = next((a for a in reversed(manifest["attempts"]) if a["id"] == r["id"]), None)
        if last is not None and last["status"] == "count_mismatch":
            raise StopDownload(f"{r['id']} failed its checks earlier; its .part file is kept for the owner to inspect")


def fetch_one(root: Path, client, r: dict, manifest: dict, q: dict, count=count_dbn_records) -> None:
    target = root / OUT_DIR / r["file"]
    part = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    part.unlink(missing_ok=True)                          # left by an interrupted attempt, already in the ledger
    attempt = {"id": r["id"], "usd": q["usd"], "expected_records": q["records"], "started": utc_now(), "status": "started"}
    manifest["attempts"].append(attempt)
    save_manifest(root / MANIFEST, manifest)              # on disk before any money is spent
    client.timeseries.get_range(**request_args(r), path=part)
    records, schema, dataset = count(part)
    if records != q["records"] or schema != r["schema"] or dataset != DATASET:
        attempt["status"] = "count_mismatch"
        attempt["found"] = {"records": records, "schema": schema, "dataset": dataset}
        save_manifest(root / MANIFEST, manifest)
        raise StopDownload(f"{r['id']}: expected {q['records']:,} {r['schema']} records in {DATASET}, "
                           f"found {records:,} {schema} in {dataset}")
    digest, size = sha256_of(part), part.stat().st_size
    os.replace(part, target)
    attempt["status"] = "ok"
    manifest["files"][r["id"]] = {**r, "symbol": SYMBOL, "stype_in": STYPE_IN, "dataset": DATASET, "sha256": digest,
                                  "records": records, "expected_records": q["records"], "size_bytes": size,
                                  "quoted_usd": q["usd"], "finished": utc_now()}
    save_manifest(root / MANIFEST, manifest)


def download(root: Path, client, approved: bool = False, count=count_dbn_records) -> dict:
    if not approved:
        raise StopDownload("not approved: the owner must say yes before any paid request")
    if not (root / APPROVAL).exists():
        raise StopDownload(f"{APPROVAL} is missing")
    manifest = load_manifest(root / MANIFEST)
    if manifest.get("partial"):
        raise StopDownload("the plan changed after trades_2019 broke; this command would request it again")
    todo = [r for r in REQUESTS if not is_done(root, manifest, r)]
    check_no_failed_checks(manifest, todo)
    quotes = {r["id"]: quote(client, r) for r in todo}
    total = committed_usd(manifest) + sum(q["usd"] for q in quotes.values())
    if total > CAP_USD:
        raise StopDownload(f"planned total ${total:.2f} is over the ${CAP_USD:.2f} cap; nothing requested")
    for r in todo:
        q = quote(client, r)                              # fresh price right before the request
        spent = committed_usd(manifest)
        if spent + q["usd"] > CAP_USD:
            raise StopDownload(f"{r['id']}: ${spent:.2f} + ${q['usd']:.2f} would pass the ${CAP_USD:.2f} cap")
        fetch_one(root, client, r, manifest, q, count)
    return manifest


def record_partial(root: Path, manifest: dict, count=count_dbn_records) -> None:
    """Put the interrupted 2019 file in the manifest as unverified. The file itself is not changed."""
    if manifest.get("partial"):
        return
    path = root / OUT_DIR / PARTIAL_FILE
    records, _, _ = count(path)
    manifest["partial"] = {PARTIAL_ID: {"file": PARTIAL_FILE, "sha256": sha256_of(path), "records": records,
                                        "size_bytes": path.stat().st_size, "status": "interrupted, count not verified"}}
    for a in manifest["attempts"]:
        if a["id"] == PARTIAL_ID and a["status"] == "started":
            a["status"] = "interrupted"
    save_manifest(root / MANIFEST, manifest)


def download_tail(root: Path, client, approved: bool = False, count=count_dbn_records) -> dict:
    if not approved:
        raise StopDownload("not approved: the owner must say yes before any paid request")
    manifest = load_manifest(root / MANIFEST)
    record_partial(root, manifest, count)
    r = TAIL_REQUEST
    if is_done(root, manifest, r):
        return manifest
    check_no_failed_checks(manifest, [r])
    q = quote(client, r)
    spent = committed_usd(manifest)
    if spent + q["usd"] > CAP_USD:
        raise StopDownload(f"{r['id']}: ${spent:.2f} + ${q['usd']:.2f} would pass the ${CAP_USD:.2f} cap")
    fetch_one(root, client, r, manifest, q, count)
    return manifest


def render_approval(quotes: dict, generated: str) -> str:
    total = sum(q["usd"] for q in quotes.values())
    lines = ["# Databento batch 1: download approval", "",
             f"Written {generated} by `src/data/databento_download.py`, before any paid request. Prices and record "
             "counts are fresh from `metadata.get_cost` and `metadata.get_record_count`.", "",
             f"Dataset `{DATASET}`, symbols `{SYMBOL}`, stype_in `{STYPE_IN}`. End dates are exclusive.", "",
             "| # | schema | start | end | records | price ($) | file |", "|---:|---|---|---|---:|---:|---|"]
    for i, r in enumerate(REQUESTS, 1):
        q = quotes[r["id"]]
        lines.append(f"| {i} | {r['schema']} | {r['start']} | {r['end']} | {q['records']:,} | {q['usd']:.2f} | "
                     f"`{OUT_DIR / r['file']}` |")
    lines += ["", f"**Total: ${total:.2f}** (task estimate ${ESTIMATE_USD:.2f}). **Hard cap: ${CAP_USD:.2f}.**", "",
              "Requests outside this table are not allowed. The test period (2024 on) is not requested.", "",
              "Status: awaiting the owner's approval.", ""]
    return "\n".join(lines)


def render_report(manifest: dict, status: str, generated: str) -> str:
    lines = ["# Databento download batch 1", "", f"Generated {generated}. **Status: {status}**", "",
             f"Dataset `{DATASET}`, symbols `{SYMBOL}`, stype_in `{STYPE_IN}`. Files are in `{OUT_DIR}`; the manifest "
             "is `manifest.json` there. Files were only counted and hashed, not decoded into bars.", "",
             "| file | records | expected | match | size (MB) | quoted ($) | SHA-256 |", "|---|---:|---:|---:|---:|---:|---|"]
    for e in manifest["files"].values():
        lines.append(f"| {e['file']} | {e['records']:,} | {e['expected_records']:,} | "
                     f"{'yes' if e['records'] == e['expected_records'] else 'no'} | {e['size_bytes'] / 1e6:.1f} | "
                     f"{e['quoted_usd']:.2f} | `{e['sha256']}` |")
    lines += ["", f"Requested in total, failed attempts included: ${committed_usd(manifest):.2f} "
                  f"(cap ${CAP_USD:.2f}). This is from quotes; the billed amount was not read from the account.", "",
              f"Attempts: {len(manifest['attempts'])}. Not ok: "
              f"{sum(a['status'] != 'ok' for a in manifest['attempts'])}.", ""]
    return "\n".join(lines)


def write_report(root: Path, manifest: dict, status: str) -> Path:
    now = datetime.now(timezone.utc)
    out = root / "reports" / f"databento_download_batch1_{now.strftime('%Y%m%dT%H%M%SZ')}"
    out.mkdir(parents=True, exist_ok=False)
    (out / "summary.md").write_text(render_report(manifest, status, now.strftime("%Y-%m-%dT%H:%M:%SZ")), encoding="utf-8")
    return out


def main(argv=None) -> None:
    import databento

    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["quote", "download", "tail"])
    p.add_argument("--approved", action="store_true")
    a = p.parse_args(argv)
    root = Path(".")
    key = load_key(root / ".env")
    client = databento.Historical(key)
    try:
        if a.command == "quote":
            if (root / APPROVAL).exists():
                raise StopDownload(f"{APPROVAL} already exists")
            text = render_approval({r["id"]: quote(client, r) for r in REQUESTS}, utc_now())
            (root / APPROVAL).write_text(text, encoding="utf-8")
            print(text)
            return
        status = "complete"
        try:
            run = download_tail if a.command == "tail" else download
            manifest = run(root, client, approved=a.approved)
        except StopDownload as e:
            status = f"stopped: {e}"
            manifest = load_manifest(root / MANIFEST)
        print(status, write_report(root, manifest, status))
    except Exception as e:  # keep the key out of any traceback text
        raise SystemExit(f"{type(e).__name__}: {str(e).replace(key, '[redacted]')}") from None


if __name__ == "__main__":
    main()
