"""Price estimate v2: front-month continuous 6E on Databento. Metadata calls only: nothing is downloaded.

Tries 6E.v.0 (volume rule) and falls back to 6E.c.0 only if the API rejects the symbol or returns no records.
The API key is handled as in v1. Comparison figures come from the v1 run.json, not a new request.
"""

import itertools
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.data.databento_cost_estimate import CREDIT_USD, DATASET, check_query, load_key

SYMBOL_CANDIDATES = ["6E.v.0", "6E.c.0"]
STYPE_IN = "continuous"
RESERVE_USD = 15.0
YEARS = list(range(2015, 2024))
TRAIN_YEARS = list(range(2015, 2022))
VALIDATION_YEARS = [2022, 2023]
MIN_TRAIN_YEARS = 3
PREV_RUN = "reports/databento_cost_estimate_20261104T055537Z/run.json"
FULL_OHLCV = {"id": "a", "schema": "ohlcv-1m", "start": "2015-01-01", "end": "2024-01-01", "label": "ohlcv-1m, 2015-2023"}
FULL_TRADES = {"id": "b", "schema": "trades", "start": "2015-01-01", "end": "2024-01-01", "label": "trades, 2015-2023"}


def year_query(year: int) -> dict:
    return {"id": f"c{year}", "schema": "trades", "start": f"{year}-01-01", "end": f"{year + 1}-01-01",
            "label": f"trades, {year}"}


def request_args(q: dict, symbol: str) -> dict:
    check_query(q)
    return dict(dataset=DATASET, symbols=symbol, stype_in=STYPE_IN, schema=q["schema"], start=q["start"], end=q["end"])


def estimate(metadata, q: dict, symbol: str) -> dict:
    args = request_args(q, symbol)
    return {**q, "symbol": symbol,
            "records": int(metadata.get_record_count(**args)),
            "bytes": int(metadata.get_billable_size(**args)),
            "usd": float(metadata.get_cost(**args))}


def choose_symbol(metadata, candidates=SYMBOL_CANDIDATES, client_error=Exception) -> tuple[str, list[dict]]:
    """First symbol the API accepts with records on the full ohlcv-1m range, plus a log of each attempt.

    A 401 or 403 is an account problem, not a symbol problem, so it is raised instead of trying the next symbol.
    """
    attempts = []
    for symbol in candidates:
        try:
            n = int(metadata.get_record_count(**request_args(FULL_OHLCV, symbol)))
        except client_error as e:
            if getattr(e, "http_status", None) in (401, 403):
                raise
            attempts.append({"symbol": symbol, "ok": False, "detail": f"{type(e).__name__}: {e}"})
            continue
        attempts.append({"symbol": symbol, "ok": n > 0, "detail": f"{n:,} records"})
        if n > 0:
            return symbol, attempts
    raise RuntimeError(f"no symbol worked: {attempts}")


def options(ohlcv: dict, years: dict[int, dict], credit=CREDIT_USD, reserve=RESERVE_USD) -> pd.DataFrame:
    """All trades-year sets meeting the task conditions, best first.

    Ranking, fixed before seeing the prices: most train years; then a block with no holes ending at 2021 (next to
    validation, same market regime as far as possible); then most trades.
    """
    base = ohlcv["usd"] + sum(years[y]["usd"] for y in VALIDATION_YEARS)
    rows = []
    for k in range(MIN_TRAIN_YEARS, len(TRAIN_YEARS) + 1):
        for train in itertools.combinations(TRAIN_YEARS, k):
            usd = base + sum(years[y]["usd"] for y in train)
            left = credit - usd
            if left < reserve:
                continue
            chosen = list(train) + VALIDATION_YEARS
            rows.append({"train_years": train, "n_train": k, "block_to_2021": list(train) == TRAIN_YEARS[-k:],
                         "usd": usd, "left_usd": left, "trades": sum(years[y]["records"] for y in chosen),
                         "gb": (ohlcv["bytes"] + sum(years[y]["bytes"] for y in chosen)) / 1e9})
    cols = ["train_years", "n_train", "block_to_2021", "usd", "left_usd", "trades", "gb"]
    t = pd.DataFrame(rows, columns=cols)
    return t.sort_values(["n_train", "block_to_2021", "trades"], ascending=False, ignore_index=True)


def next_step_usd(ohlcv: dict, years: dict[int, dict], n_train: int) -> float:
    """Cheapest total with `n_train` train years, the ohlcv and both validation years."""
    cheapest = sorted(years[y]["usd"] for y in TRAIN_YEARS)[:n_train]
    return ohlcv["usd"] + sum(years[y]["usd"] for y in VALIDATION_YEARS) + sum(cheapest)


def saving(new: float, old: float) -> float:
    return 100 * (1 - new / old)


def compare(prev: dict, a: dict, b: dict, y2021: dict) -> list[dict]:
    old = {r["id"]: r for r in prev["results"]}
    return [{"label": n["label"], "old_records": old[i]["records"], "new_records": n["records"],
             "old_usd": old[i]["usd"], "new_usd": n["usd"], "saving_pct": saving(n["usd"], old[i]["usd"])}
            for i, n in (("a", a), ("b", b), ("c", y2021))]


def render(generated, head, version, symbol, attempts, a, b, years, cmp_rows, opts) -> str:
    year_sum = sum(y["usd"] for y in years.values())
    budget = CREDIT_USD - RESERVE_USD
    lines = ["# Databento cost estimate v2: 6E front-month continuous", "",
             f"Generated {generated} by `src/data/databento_cost_estimate_v2.py` (HEAD `{head}`, databento {version}). "
             "Only metadata calls were made. Nothing was downloaded and no data was bought.", "",
             f"Dataset `{DATASET}`, stype_in `{STYPE_IN}`, symbol used: **`{symbol}`**.", "",
             "Symbol attempts:", ""]
    lines += [f"- `{x['symbol']}`: {'worked' if x['ok'] else 'failed'} ({x['detail']})" for x in attempts]
    lines += ["", "## Estimates", "", "| id | request | records | size (GB) | price ($) |", "|---|---|---:|---:|---:|"]
    for r in [a, b] + list(years.values()):
        lines.append(f"| {r['id']} | {r['label']} | {r['records']:,} | {r['bytes'] / 1e9:.3f} | {r['usd']:.2f} |")
    lines += ["", f"The nine yearly prices sum to ${year_sum:.2f}; the full-range price is ${b['usd']:.2f}.", "",
              "## Compared with `6E.FUT`", "",
              f"From `{PREV_RUN}`. Saving = 1 − new price / old price.", "",
              "| request | 6E.FUT records | continuous records | 6E.FUT ($) | continuous ($) | saving |",
              "|---|---:|---:|---:|---:|---:|"]
    for c in cmp_rows:
        lines.append(f"| {c['label']} | {c['old_records']:,} | {c['new_records']:,} | {c['old_usd']:.2f} | "
                     f"{c['new_usd']:.2f} | {c['saving_pct']:.1f}% |")
    lines += ["", "## Recommendation", "",
              f"Conditions: full ohlcv-1m 2015-2023; trades for 2022, 2023 and at least {MIN_TRAIN_YEARS} train years; "
              f"at least ${RESERVE_USD:.0f} left of ${CREDIT_USD:.0f}, so at most ${budget:.0f} spent. Ranking, fixed "
              "before the prices were seen: most train years, then a block ending at 2021, then most trades.", ""]
    if opts.empty:
        lines += ["No combination meets the conditions.", ""]
    else:
        best = opts.iloc[0]
        lines += [f"**Buy:** ohlcv-1m 2015-2023 and trades for "
                  f"{', '.join(map(str, list(best['train_years']) + VALIDATION_YEARS))}. "
                  f"Total ${best['usd']:.2f}, ${best['left_usd']:.2f} left, {best['gb']:.3f} GB.", "",
                  f"{len(opts)} of the possible train-year sets meet the conditions. Top 10:", "",
                  "| train years | price ($) | left ($) | trades | size (GB) |", "|---|---:|---:|---:|---:|"]
        for _, o in opts.head(10).iterrows():
            lines.append(f"| {', '.join(map(str, o['train_years']))} | {o['usd']:.2f} | {o['left_usd']:.2f} | "
                         f"{o['trades']:,} | {o['gb']:.3f} |")
        more = int(best["n_train"]) + 1
        if more <= len(TRAIN_YEARS):
            usd = next_step_usd(a, years, more)
            lines += ["", f"{more} train years do not fit: the cheapest such set costs ${usd:.2f}, which leaves "
                          f"${CREDIT_USD - usd:.2f}, under the ${RESERVE_USD:.0f} reserve."]
        lines.append("")
    lines += ["## Notes", "",
              "- The test period (2024 on) was not priced. Every range ends at 2024-01-01T00:00Z or earlier, exclusive.",
              f"- The credit of ${CREDIT_USD:.0f} is the figure from the task. The account balance was not checked.",
              "- These are estimates from the metadata API, for this account, on the generation date.", ""]
    return "\n".join(lines)


def run(root: Path = Path(".")) -> Path:
    import databento
    from databento.common.error import BentoClientError

    root = Path(root)
    key = load_key(root / ".env")
    prev = json.loads((root / PREV_RUN).read_text(encoding="utf-8"))
    try:
        meta = databento.Historical(key).metadata
        symbol, attempts = choose_symbol(meta, client_error=BentoClientError)
        a, b = estimate(meta, FULL_OHLCV, symbol), estimate(meta, FULL_TRADES, symbol)
        years = {y: estimate(meta, year_query(y), symbol) for y in YEARS}
    except Exception as e:  # keep the key out of any traceback text
        raise RuntimeError(f"{type(e).__name__}: {str(e).replace(key, '[redacted]')}") from None
    opts = options(a, years)
    cmp_rows = compare(prev, a, b, years[2021])
    now = datetime.now(timezone.utc)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    out = root / "reports" / f"databento_cost_estimate_v2_{now.strftime('%Y%m%dT%H%M%SZ')}"
    out.mkdir(parents=True, exist_ok=False)
    text = render(now.strftime("%Y-%m-%dT%H:%M:%SZ"), head, databento.__version__, symbol, attempts, a, b, years, cmp_rows, opts)
    payload = json.dumps({"dataset": DATASET, "symbol": symbol, "stype_in": STYPE_IN, "attempts": attempts, "a": a, "b": b,
                          "years": years, "compare": cmp_rows}, indent=2)
    if key in text or key in payload:
        raise RuntimeError("key found in report output")
    (out / "summary.md").write_text(text, encoding="utf-8")
    (out / "run.json").write_text(payload, encoding="utf-8")
    print(text)
    return out


if __name__ == "__main__":
    run()
