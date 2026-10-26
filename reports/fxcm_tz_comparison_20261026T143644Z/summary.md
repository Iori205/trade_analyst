# Timezone decision report: FXCM comparison (stage 1)

Generated 2026-10-26 (UTC).

**Decision: no timezone rule can be recommended yet. The provisional label stays C6** (naive source clock, no conversion). The leading candidate to test is still C4.

**No FXCM file was downloaded.** The download step stopped because the usage terms are not documented in the project (§5). Only the already-local `data/fxcm/53.csv` was compared.

## 1. What was built

- **Gated fetch** (`src/data/fxcm_fetch.py`):
  - **Refuses to run** without a completed approval note naming the terms basis and every requested week.
  - **URL** follows the README pattern `https://candledata.fxcorporate.com/m1/EURUSD/{year}/{week}.csv.gz`.
  - **Storage:** a new version directory `data/reference/fxcm/v1/` that is never reused. It holds the files as received in `m1/EURUSD/{year}/{week}.csv.gz`, plus `MANIFEST.csv`, `SHA256SUMS.txt`, the raw `http_headers/` and a copy of `APPROVAL.md`.
  - **Manifest** records the URL, retrieval time, HTTP status, Content-Length, Last-Modified, ETag, row count, actual first and last labels, and a `coverage_status` computed from the file contents (`ok`, `mismatch`, `bad_schema`, `unreadable`). The week number is never trusted to mean a calendar week.
- **Day-level comparison** (`src/data/fxcm_tz_compare.py`):
  - **Scan:** for each FXCM UTC weekday, bid 1-minute returns are scanned at offsets −720 to +720 min in 1-minute steps (HistData label + k = FXCM minute). Nothing is shifted on disk.
  - **Per-day output:** best offset, runner-up outside ±1 min, peak ratio, Spearman agreement, a null check, the correlation at each hypothesis's predicted offset, exact-label pairs, and the identical-OHLC share and pip differences both at offset 0 and at the best offset.
  - **Exclusions,** each recorded with its reason:
    - Saturdays and Sundays (closure and session open);
    - holiday-candidate dates;
    - days with an FXCM gap over 30 min inside the session;
    - days with a HistData gap over 30 min at the best offset.
    - At minute level: 16:55–17:15 New York rollover, and 15 minutes after any long gap.
  - **Grouping:** days are grouped by provisional era (≤ 2018 / ≥ 2019) and DST regime. Candidates C1–C4 are scored per cell with the pre-registered rule.
- **Tests:** 9 new (gating, manifest, content-coverage check, day scan, exclusions, verdict logic). **85 passed.**

## 2. Evidence so far (from `53.csv` only)

Files: `daily.csv`, `cells.csv`, `verdicts.csv`, `scans.csv` and `run.json`.

| UTC day | Regime | Best offset | r | Peak ratio | Shared min | Decisive | Counted | Exclusion |
|---|---|---|---|---|---|---|---|---|
| 2019-12-29 Sun | both_standard | +300 | 0.872 | 1.11 | 92 | no | no | weekend |
| 2019-12-30 Mon | both_standard | +300 | 0.985 | 10.6 | 1411 | yes | **yes** | |
| 2019-12-31 Tue | both_standard | +300 | 0.992 | 6.8 | 1138 | yes | no | holiday candidate (New Year's Eve) |
| 2020-01-01 Wed | both_standard | none | | | 0 | no | no | holiday (no FXCM bars) |
| 2020-01-02 Thu | both_standard | +300 | 0.993 | 9.4 | 963 | yes | **yes** | |
| 2020-01-03 Fri | both_standard | +300 | 0.993 | 4.9 | 1311 | yes | **yes** | |

- **Offsets:** 3 counted decisive days, all at +300. That fits H1, H2 and H3 equally, since all three predict +300 in winter. Spearman agrees on every decisive day.
- **Exact-label match (offset 0):** 0% identical OHLC. The two sources' labels are not on the same clock.
- **At +300:** only 1–3% of bars have all four OHLC fields identical. The median close difference is 0.1 pip. These are related but non-identical feeds; a shared upstream cannot be ruled out, but FXCM is not a copy of HistData.

## 3. Decision status by era and regime (counted decisive days)

| Era | both_standard | both_summer | US-only window | Expected after the 4 approved-in-principle weeks |
|---|---|---|---|---|
| ≤ 2018 | 0 | 0 | 0 | summer 5 (2018/43); US-only 10 (2018/12, 2018/44); **standard 0** |
| ≥ 2019 | 3 (all +300) | 0 | 0 | US-only 5 (2019/11); **standard 3; summer 0** |

| Candidate | Status now | Why |
|---|---|---|
| C1 fixed UTC−5 | Not testable yet | No summer days |
| C2 New York throughout | Not testable yet | No US-only days ≥ 2019 |
| C3 EU dates throughout | Not testable yet | No US-only days ≤ 2018 |
| C4 piecewise H2→H3 | Leading (internal evidence only) | No independent cell filled |
| C6 no conversion | **Provisional label** | |

**Confidence: low.** Only the method and FXCM's winter alignment are validated.

**Even with all four weeks, no candidate could be *accepted*:** three of the six era/regime cells would still be short of 5 decisive days. The four weeks *can* clearly contradict C1, C2 or C3:
- C2 would fail the 2019/11 US-only window if it shows +300.
- C3 would fail the 2018 US-only windows if they show +240.
- C1 would fail 2018/43 if it shows +240.

## 4. Smallest additional sample to make acceptance possible

All of these are inside the README years 2017–2020, and all show availability in the 2026-10-22 probe.

| Week | Cell filled | In planned list |
|---|---|---|
| 2018/45 (Mon 2018-11-05; FOMC 11-08 19:00 UTC) | ≤ 2018 both_standard | Yes |
| 2019/29 (Mon 2019-07-15) | ≥ 2019 both_summer | Yes |
| 2020/03 (Mon 2020-01-13) | ≥ 2019 both_standard (adds to `53.csv`'s 3 days) | Yes |
| 2019/44 (Mon 2019-10-28; FOMC 10-30, payrolls 11-01) | Margin for ≥ 2019 US-only, which has exactly 5 days otherwise | **No (needs explicit approval)** |

**Risks that remain even after acceptance on these weeks:**
- **2021–2026 rests on internal evidence only** for the ≥ 2019 rule.
- **The 2024-10-27 Sunday is unresolved;** it needs 2024 weeks, and 2024 permission is not documented.
- **The change date is only bracketed,** between 2018-11-04 and 2019-03-10.
- **FXCM is the only reference** for the offset tests. Dukascopy is probably HistData's upstream, so it doesn't count as independent.

## 5. Approval still needed (exact)

The download stopped at this check: `docs/approvals/fxcm_batch1.md` does not exist, and no FXCM terms correspondence is saved in the project. To proceed, you need to:

1. **Save FXCM's email reply** in the project (e.g. `docs/approvals/fxcm_email_<date>.txt`). It should show that non-commercial personal research use of the candledata files is permitted for 2018–2019.
2. **Create `docs/approvals/fxcm_batch1.md`** from `approval_template.md` in this folder, filling in `approved_by`, `approved_on`, `terms_basis` (pointing at the saved email) and `approved_weeks: 2018/12, 2018/43, 2018/44, 2019/11`.
   - Add 2019/44 only if you approve it.
   - Optionally add 2018/45, 2019/29 and 2020/03 now (§4), to avoid a second approval round.

Then run:
```
.venv/bin/python -m src.data.fxcm_fetch --approval docs/approvals/fxcm_batch1.md --weeks <the approved weeks>
.venv/bin/python -m src.data.fxcm_tz_compare --fxcm data/fxcm/53.csv data/reference/fxcm/v1/m1/EURUSD/*/*.csv.gz
```

## 6. Safety

- **Hashes:** in `run.json` (`tracked_files_unchanged: true`) and `source_hashes_check.txt`. All original HistData files, Parquet files, the Dukascopy sample and `53.csv` are unchanged.
- **Nothing else touched:** no file was filled, deduplicated or converted, and the timezone policy is unchanged (C6).
- **No network access** was used in this task.
