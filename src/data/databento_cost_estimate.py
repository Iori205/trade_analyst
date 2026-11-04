"""Price estimate for CME 6E futures on Databento. Metadata calls only: nothing is downloaded.

Allowed client calls: metadata.get_cost, get_record_count, get_billable_size, get_dataset_range.
The API key is read from .env, is never printed or written, and is scrubbed from any error text.
End dates are exclusive in the Databento API, so "through 2023-12-31" is sent as end=2024-01-01T00:00Z.
"""

import itertools
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATASET = "GLBX.MDP3"
SYMBOLS = "6E.FUT"
STYPE_IN = "parent"
CREDIT_USD = 125.0
TEST_START = pd.Timestamp("2024-01-01", tz="UTC")
QUERIES = [
    {"id": "a", "schema": "ohlcv-1m", "start": "2015-01-01", "end": "2024-01-01", "label": "ohlcv-1m, 2015-2023"},
    {"id": "b", "schema": "trades", "start": "2015-01-01", "end": "2024-01-01", "label": "trades, 2015-2023"},
    {"id": "c", "schema": "trades", "start": "2021-01-01", "end": "2022-01-01", "label": "trades, 2021"},
    {"id": "d", "schema": "tbbo", "start": "2021-01-01", "end": "2022-01-01", "label": "tbbo, 2021"},
]
OVERLAPS = [{"b", "c"}]  # c is contained in b, so buying both pays twice for 2021


def load_key(env_path: Path, name: str = "DATABENTO_API_KEY") -> str:
    """Plain read of .env; tolerates indentation, `export` and quotes. Raises without showing the content."""
    for line in Path(env_path).read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ").strip()
        if line.startswith(f"{name}="):
            value = line.split("=", 1)[1].strip().strip("\"'")
            if value:
                return value
    raise RuntimeError(f"{name} not found in {env_path}")


def check_query(q: dict) -> None:
    """Refuse any range that reaches the test period."""
    if pd.Timestamp(q["end"], tz="UTC") > TEST_START:
        raise ValueError(f"query {q['id']} reaches the test period")


def estimate(metadata, q: dict) -> dict:
    check_query(q)
    args = dict(dataset=DATASET, symbols=SYMBOLS, stype_in=STYPE_IN, schema=q["schema"], start=q["start"], end=q["end"])
    return {**q,
            "records": int(metadata.get_record_count(**args)),
            "bytes": int(metadata.get_billable_size(**args)),
            "usd": float(metadata.get_cost(**args))}


def combos(results: list[dict], credit: float = CREDIT_USD) -> pd.DataFrame:
    """Every non-empty combination, cheapest first. Combinations with overlapping data are left out."""
    rows = []
    for r in range(1, len(results) + 1):
        for group in itertools.combinations(results, r):
            ids = {g["id"] for g in group}
            if any(o <= ids for o in OVERLAPS):
                continue
            usd = sum(g["usd"] for g in group)
            rows.append({"combo": "+".join(g["id"] for g in group), "usd": usd,
                         "gb": sum(g["bytes"] for g in group) / 1e9, "fits": usd <= credit,
                         "left_usd": credit - usd})
    return pd.DataFrame(rows).sort_values(["usd", "combo"], ignore_index=True)


def render(results, ranges, table, generated, head, versions) -> str:
    lines = [
        "# Databento cost estimate: CME 6E futures", "",
        f"Generated {generated} by `src/data/databento_cost_estimate.py` (HEAD `{head}`, databento {versions}). "
        "Only metadata calls were made. Nothing was downloaded and no data was bought.", "",
        f"Dataset `{DATASET}`, symbols `{SYMBOLS}`, stype_in `{STYPE_IN}`. The credit of ${CREDIT_USD:.0f} is the "
        "figure from the task. The balance on the account was not checked.", "",
        "## Estimates", "",
        "| id | request | UTC range (end exclusive) | records | size (GB) | price ($) | within credit |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(f"| {r['id']} | {r['label']} | {r['start']} to {r['end']} | {r['records']:,} | "
                     f"{r['bytes'] / 1e9:.3f} | {r['usd']:.2f} | {'yes' if r['usd'] <= CREDIT_USD else 'no'} |")
    lines += ["", "Size is the billable uncompressed DBN size (1 GB = 10^9 bytes).", "",
              f"## Combinations against ${CREDIT_USD:.0f}", "",
              "b+c is left out because c is contained in b.", "",
              "| combination | price ($) | size (GB) | fits | credit left ($) |", "|---|---:|---:|---:|---:|"]
    for _, t in table.iterrows():
        lines.append(f"| {t['combo']} | {t['usd']:.2f} | {t['gb']:.3f} | {'yes' if t['fits'] else 'no'} | "
                     f"{t['left_usd']:.2f} |")
    lines += ["", "## Dataset range", "",
              f"`{DATASET}`: {ranges.get('start')} to {ranges.get('end')}.", "",
              "| schema | start | end |", "|---|---|---|"]
    for s, v in sorted((ranges.get("schema") or {}).items()):
        if s in {q["schema"] for q in QUERIES}:
            lines.append(f"| {s} | {v.get('start')} | {v.get('end')} |")
    lines += ["", "## Notes", "",
              "- The test period (2024 on) was not priced. Every requested range ends at 2024-01-01T00:00Z, exclusive.",
              "- The parent symbol covers all 6E instruments: every expiry and calendar spreads, not one continuous "
              "front-month series. Records for one continuous contract would be fewer.",
              "- `databento` is in `.venv` but not pinned in `requirements.txt`.", ""]
    return "\n".join(lines)


def run(root: Path = Path(".")) -> Path:
    import databento

    root = Path(root)
    key = load_key(root / ".env")
    try:
        client = databento.Historical(key)
        ranges = client.metadata.get_dataset_range(DATASET)
        results = [estimate(client.metadata, q) for q in QUERIES]
    except Exception as e:  # keep the key out of any traceback text
        raise RuntimeError(f"{type(e).__name__}: {str(e).replace(key, '[redacted]')}") from None
    table = combos(results)
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    out = root / "reports" / f"databento_cost_estimate_{ts}"
    out.mkdir(parents=True, exist_ok=False)
    text = render(results, ranges, table, now.strftime("%Y-%m-%dT%H:%M:%SZ"), head, databento.__version__)
    (out / "summary.md").write_text(text, encoding="utf-8")
    (out / "run.json").write_text(json.dumps({"dataset": DATASET, "symbols": SYMBOLS, "stype_in": STYPE_IN,
                                              "results": results, "dataset_range": ranges}, indent=2), encoding="utf-8")
    if key in text or key in (out / "run.json").read_text(encoding="utf-8"):
        raise RuntimeError("key found in report output")
    print(text)
    return out


if __name__ == "__main__":
    run()
