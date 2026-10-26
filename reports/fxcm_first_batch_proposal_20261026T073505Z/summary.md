# FXCM first fetch batch: proposal (no data downloaded)

Created 2026-10-26 07:35 UTC. **This is a proposal only.**
- Nothing was downloaded and no FXCM URL was requested during this task.
- Raw data, Parquet files, existing reports and `planned_fetch_list.csv` were not modified (see §8).
- No timestamp was converted, and no timezone rule is selected. The default stays C6, the naive source clock.

Inputs read:
- `reports/reference_access_fxcm_20261022T133102Z/`: `planned_fetch_list.csv`, `fxcm_m1_eurusd_coverage.tsv`, `summary.md`, `fxcm_terms_enquiry_draft.txt`
- `reports/timestamp_investigation_20261022T104848Z/summary.md`
- `reports/timestamp_policy_proposal_20261022T110251Z/` (`summary.md`, `comparison_plan.csv`, `candidate_timezone_decisions.csv`)
- `reports/fxcm_audit_53_20261026T063221Z/summary.md`

Files in this folder:

| File | Content |
|---|---|
| `proposed_weeks.csv` | Proposed weeks (tier 1 and tier 2) with rationale, events, availability and terms status |
| `planned_list_annotated.csv` | Every row of the planned list, with weekday DST regimes and both week-number interpretations. The original CSV is unchanged. |
| `week_numbering_evidence.csv` | Per-year week-1 and week-53 presence from the 2026-10-22 probe, against ISO and US week conventions |
| `dst_switch_dates.csv` | US and EU switch Sundays, 2015–2026 |
| `source_hashes_check.txt` | Before/after SHA-256 check |

## 1. The planned fetch list

**Columns:** `sample_id, iso_year, iso_week, week_monday, note, available, bytes, documented_in_readme`.

- **Size:** 75 rows (74 available, about 10 MB). The list covers 2015–2018 and 2021–2024, plus 2019 and 2020.
- **Missing week:** 2019-W01 is marked `available=False`, because the probe returned 404.
- **Source of the availability data:** the `available` and `bytes` columns come from a 1-byte probe made on 2026-10-22. They show that a file was being served then, **not what dates it contains**. Some files carry Last-Modified dates long after their week, so FXCM may have revised them.
- **README coverage:** 44 rows fall in the README-documented years 2017–2020, and 31 rows fall outside them.

| Sample | Years | Weeks | What they are |
|---|---|---|---|
| A1, A2 | 2015–2018 | 12 | January and July controls |
| A3 | 2015–2018 | 21 | Labelled "US-only DST window" |
| B0 | 2018-W42 to 2019-W14 | 23 | Every week of the change period (W01 unavailable) |
| B1 | 2019–2023 | 15 | January and July controls |
| C2 | 2024-W42 to W45 | 4 | October 2024 anomaly |

**Two problems with the list itself.** I recorded these and did not edit the list.

1. **Eight "US-only window" rows are not US-only weeks.**
   - In 2015–2018, every week 10 (Mon 2–7 March) falls before US DST starts, so it is *both standard*.
   - Every week 43 falls before EU DST ends, so it is *both summer*.
   - Both kinds are still useful as adjacent controls, but they test nothing about H2 vs H3. See `planned_list_annotated.csv`, column `note_matches_iso_regime`.
2. **The list has no US-only window weeks for 2019 autumn, 2020–2023, or 2024–2026 spring**, apart from 2024-W44. These are samples B2/C1/D1 in the policy proposal. 2019 autumn is the cleanest post-change window: the internal anchor ratio is 2.27. It is not in the list, although the probe shows it served.

## 2. The FXCM week-number → date mapping is unverified

The list assumes the URL week number equals the ISO week. FXCM's example script uses `isocalendar()`, but the probe contradicts a pure ISO scheme:
- **Week 53 is served in 2012, 2018, 2019, 2023 and 2025**, all ISO years with only 52 weeks.
- **2015-W53 is not served**, although 2015 has an ISO week 53.
- **The one content check fits both conventions.** `53.csv` runs from Sun 2019-12-29 22:03 to Fri 2020-01-03, and its week number matches a Sunday-start week where week 1 contains 1 January. **We do not know the URL it came from**, and that one file cannot settle the scheme.

**Consequences:**
- **For 2015, 2017–2020 and 2023–2026,** ISO and Sunday-start numbering give the *same* trading week mid-year. So the proposed weeks (all in 2017–2020 and 2024) point to the intended week under either convention.
- **For 2016, 2021 and 2022,** the two conventions differ by one week. Under the Sunday-start reading:
  - planned 2016-W11 would be a both-standard week;
  - 2016-W44 would be a both-summer week.
  - The 15 affected rows are listed in `planned_list_annotated.csv`.

**Requirement for any future fetch:** check each file's first and last timestamps against the intended trading week before it is used. If they don't match, discard the file from the analysis (keep it on disk) rather than re-labelling it.

## 3. What still needs distinguishing

Offsets are listed as *reference UTC minus HistData label*.

| Regime (weekdays) | H1 fixed UTC−5 | H2 New York | H3 NY offsets on EU dates |
|---|---|---|---|
| both_standard | +300 | +300 | +300 |
| both_summer | **+300** | +240 | +240 |
| us_summer_eu_standard (US-only DST window) | +300 | **+240** | +300 |

So:
- **Both-summer weeks separate H1 (+300) from H2/H3 (+240).**
- **US-only windows separate H2 (+240) from H1/H3 (+300).**
- **Both-standard weeks separate nothing.** That includes `53.csv` and the whole Nov 2018 – Mar 2019 winter. They only validate the method and FXCM's UTC claim.

This has a consequence for the change point. **No offset test can locate it more precisely than the gap between two US-only windows:** 2018-10-28 to 11-04, then 2019-03-10 to 03-31. Every week between them is both-standard, and all three hypotheses predict the same offset there. The 21 winter B0 weeks in the planned list therefore add nothing to the H2/H3 question. They could only show a vendor or feed switch through non-offset evidence (exact-OHLC share, missing-minute patterns), and that is better tested against Dukascopy than FXCM.

Open questions the batch must address:
- **C4 piecewise rule:** is the pre-2019 era H2 and the post-2019 era H3 in an independent UTC-labelled source?
- **C1 rejection:** is H1 rejected in both summer by the independent source?
- **C5, 2024-10-27 Sunday:** the HistData open is at 17:00 with no 16:00 bars and no repeated hour, while weekday anchors fit H3. Is the Sunday evening on the H2 offset, or on H3 with its first hour missing?
- **EU-switch-Sunday artefacts (2019+):** is the 19:00 hole in March and the repeated hour in October missing or copied data?
- **FXCM itself:** is it UTC in summer and around switches? So far it is only established for one winter week.

## 4. Proposed weeks

Weekday regimes come from `dst_regime` on the ISO Monday–Friday. Event dates are checked against the Federal Reserve FOMC calendars and the BLS release archives (2026-10-26). Event times follow the standard schedule: 08:30 ET for BLS releases and 14:00 ET for FOMC statements. They should be confirmed in each release before the analysis is pre-registered.

### Tier 1: exploratory first batch (8 files, about 1.00 MB compressed: 1,002,718 bytes per the probe)

| # | FXCM year/week | Trading week (Mon) | Weekday regime | Tests | Documented event (UTC) | In planned list / available | Probe | Terms status |
|---|---|---|---|---|---|---|---|---|
| 1 | 2018 / 12 | 2018-03-19 | US-only ×5 | H2 vs H1/H3, pre-change era | FOMC 2018-03-21 18:00 | Yes (A3) / True | 206, 146,996 B | README year; EULA unread; **no email on file** |
| 2 | 2018 / 43 | 2018-10-22 | both summer ×5 | H1 vs H2/H3, pre-change; offset just before EU end | none verified | Yes (A3, mislabelled US-only) / True | 206, 145,937 B | README year; **no email on file** |
| 3 | 2018 / 44 | 2018-10-29 | US-only ×5 | H2 vs H1/H3; **lower bound of change point**; EU-end Sunday 10-28 evening | Employment Situation 2018-11-02 12:30 | Yes (A3) / True | 206, 144,833 B | README year; **no email on file** |
| 4 | 2019 / 11 | 2019-03-11 | US-only ×5 | H2 vs H1/H3; **upper bound of change point**; US-start Sunday 03-10 (first 16:00 open) | CPI 2019-03-12 12:30 | Yes (B0) / True | 206, 138,756 B | README year; **no email on file** |
| 5 | 2019 / 44 | 2019-10-28 | US-only ×5 | H2 vs H1/H3, late era; EU-end Sunday 10-27 repeated hour | FOMC 2019-10-30 18:00; Employment Situation 2019-11-01 12:30 | **Not in planned list** | 206, 132,928 B (probe only) | README year; **no email on file** |
| 6 | 2024 / 43 | 2024-10-21 | both summer ×5 | H1 vs H2/H3, late era; offset just before EU end | none verified | Yes (C2) / True | 206, 92,124 B | **Outside 2017–2020: not confirmed** |
| 7 | 2024 / 44 | 2024-10-28 | US-only ×5 | **C5:** Sunday 2024-10-27 evening vs weekday H3 anchors | Employment Situation 2024-11-01 12:30 | Yes (C2) / True | 206, 96,920 B | **Outside 2017–2020: not confirmed** |
| 8 | 2024 / 45 | 2024-11-04 | both standard ×5 | US-end Sunday 2024-11-03 evening; control | FOMC 2024-11-07 19:00 | Yes (C2) / True | 206, 104,224 B | **Outside 2017–2020: not confirmed** |

**Notes on the batch:**
- **Week 5 needs your explicit approval as an addition.** It was not in the planned list. Its availability comes only from the coverage probe, and I have not constructed or tested a URL for it.
- **Weeks 1–5 are within the README years and can go first on their own.** Weeks 6–8 should wait until 2024 permission is confirmed (§6). Without them, the C5 question stays open.
- **Sunday evenings won't meet the 300-minute rule.** The Sunday evenings for weeks 3, 4, 5, 7 and 8 have fewer than 300 shared minutes, so they can't be "decisive days" under the existing rule. They would be reported as **descriptive** evidence: which UTC hour FXCM opens, and which hour HistData's first bars match at the offsets each hypothesis predicts. They are not pass/fail evidence.

### Tier 2: extra weeks needed for acceptance (not requested now)

All rows below show a 206 status in the probe.
- **In the planned list:** 2018-W11 (CPI 2018-03-13 12:30), 2018-W45 (FOMC 2018-11-08 19:00), 2018-W28, 2017-W11, 2017-W44, 2019-W12 (FOMC 2019-03-20 18:00), 2019-W29 and 2020-W03.
- **Not in the planned list:** 2020-W11 and 2024-W11.
- **Further US-only windows** for 2015–2016 and 2021–2023 would still be needed for year-by-year coverage. For 2016, 2021 and 2022 the week mapping in §2 must be checked first.

## 5. Exploratory sample vs acceptance evidence

The pre-agreed rule (`timestamp_policy_proposal_20261022T110251Z/summary.md` §3A) accepts a candidate for a period only if both hold:
- **≥ 90 %** of decisive days match its predicted offset exactly;
- **every** DST regime in that period has **≥ 5 decisive days**. A decisive day has correlation ≥ 0.3, at least 3× the best correlation outside ±1 min, and ≥ 300 shared minutes.

Weekdays the tier-1 batch could contribute, as an upper bound, since not every day will be decisive:

| Era (provisional) | both_standard | both_summer | US-only window |
|---|---|---|---|
| Pre-change (≤ 2018) | **0** | 5 (2018-W43) | 10 (2018-W12, W44) |
| Post-change (≥ 2019) | 5 (2024-W45) + about 3 full days in `53.csv` | 5 (2024-W43) | 15 (2019-W11, W44, 2024-W44) |

**The first batch is exploratory and cannot by itself satisfy acceptance:**
- **No margin:** where a regime has exactly 5 weekdays, a single non-decisive day fails it.
- **Pre-change both-standard is empty.**
- **The era boundary is assumed:** using 2018/2019 as the split is the hypothesis under test.
- **Too few years to rule out per-year drift:** for example, the 2020 and 2025 internal windows were non-decisive.

The batch can do three things:
1. Show whether FXCM day-level scans are decisive in summer and US-only weeks at all.
2. Check FXCM's UTC claim on documented events in those regimes.
3. Give a first independent reading on H2 vs H3 in each era and on 2024-10-27.

**Acceptance would need:**
- tier 2 added;
- ≥ 5 decisive days per regime per era, with margin (aim for at least 10 weekdays each);
- at least one window per year in each era, so a single-year exception like 2024 can be seen;
- a second independent UTC reference, as recommended in the policy proposal §2. Dukascopy doesn't count, since it is probably HistData's upstream.

## 6. FXCM terms: what is actually on record

| Item | Recorded where | Status |
|---|---|---|
| "This is for personal use and abides by our EULA" | FXCM MarketData README, quoted in `reference_access_fxcm_.../summary.md` | Recorded |
| Documented years 2017, 2018, 2019, 2020 | Same README | Recorded |
| EULA clauses | fxcm.com/uk/forms/eula/ opens an e-signature form | **Not read**; contents unknown |
| Repository licence | GitHub API `license: null` | None |
| FXCM email reply | Your earlier message mentions "FXCM's email says UTC" | **No copy of the email, its date, sender or wording is saved in the project.** I cannot verify what it permits. |
| Enquiry draft | `fxcm_terms_enquiry_draft.txt` | Prepared; I did not send it |

**Flags:**
- **2017–2020:** personal-use wording exists in the README, but the EULA it points to is unread. Whether FXCM's email confirmed personal research use is **not recorded**.
- **Outside 2017–2020, including October 2024:** **permission is not confirmed by anything on record.** The README does not mention those years, and no saved correspondence covers them. Do not assume the README wording extends to them.
- **Weeks 6–8 of tier 1, and 2024-W11 in tier 2,** should be fetched only after you confirm in writing (ideally saved under `reports/` or `docs/`) that FXCM's reply covers 2024.

## 7. Recommendation

**First batch:**
1. **Fetch weeks 1–5** (2018-W12, 2018-W43, 2018-W44, 2019-W11, 2019-W44; about 0.71 MB). This is permitted only if you confirm that your FXCM correspondence covers personal research use. Week 5 also needs your explicit approval as an addition to the planned list.
2. **Then weeks 6–8** (2024-W43, W44, W45; about 0.29 MB), but only after 2024 permission is confirmed and recorded.

**Handling, if approved:**
- Store files exactly as served, under a new reference folder such as `reference/fxcm/<year>/<week>.csv.gz`, with a SHA-256 manifest and the HTTP Last-Modified header for each file.
- Verify each file's first and last timestamps before use (§2).
- Run the existing `fxcm_audit` and offset-scan code per day.
- Report results by era and regime against the pre-registered rule, with no conversion.

## 8. Safety

See `source_hashes_check.txt`. I hashed all files under `data/` and `reports/` and the four Parquet files before and after this task; all unchanged. That covers the 42 originals, `53.csv`, the Dukascopy sample and every existing report including `planned_fetch_list.csv`. No network request touched FXCM. The only web requests were to federalreserve.gov and bls.gov, to check event dates. No dependency was added.

Sources for event dates:
- https://www.federalreserve.gov/monetarypolicy/fomchistorical2018.htm
- https://www.federalreserve.gov/monetarypolicy/fomchistorical2019.htm
- https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm (2024)
- https://www.bls.gov/bls/news-release/empsit.htm
- https://www.bls.gov/bls/news-release/cpi.htm
