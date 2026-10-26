# Timezone evidence checklist

Created 2026-10-26 07:44 UTC. **Planning only.**
- Nothing was downloaded, converted, cleaned or modified.
- No timezone rule is chosen; the default stays C6, the naive source clock.
- No model training or backtesting was done.

Builds on:
- `reports/fxcm_first_batch_proposal_20261026T073505Z/summary.md` (weeks, events, availability, terms)
- `reports/timestamp_policy_proposal_20261022T110251Z/summary.md` §3A (the pre-registered decision rule)

## 1. Hypotheses still open, and the minimum dates that separate them

Offset = reference UTC minus HistData label, in minutes.

| Regime (weekdays) | H1 fixed UTC−5 | H2 New York | H3 NY offsets on EU dates | Separates |
|---|---|---|---|---|
| both_standard | +300 | +300 | +300 | nothing (method/UTC control only) |
| both_summer | +300 | +240 | +240 | H1 vs H2/H3 |
| US-only window | +300 | +240 | +300 | H2 vs H1/H3 |

**Candidates under test:**
- **C4:** H2 until a change point, then H3.
- **C5:** C4 plus an exception for the 2024-10-27 Sunday evening.
- **C1, C2 and C3:** the single-rule alternatives (H1, H2 or H3 for the whole period).

**Minimum dates:** one week per separating regime per era, plus the 2024 question. These are tier 1 of the proposal; no week can be dropped without losing a test.

| # | FXCM year/week | Mon | Regime | Question answered | Event anchor (UTC) |
|---|---|---|---|---|---|
| 1 | 2018/12 | 03-19 | US-only | H2 vs H3, pre-change | FOMC 03-21 18:00 |
| 2 | 2018/43 | 10-22 | both summer | H1 vs H2/H3, pre-change | none verified |
| 3 | 2018/44 | 10-29 | US-only | H2 vs H3; lower bound of the change point | Payrolls 11-02 12:30 |
| 4 | 2019/11 | 03-11 | US-only | H2 vs H3; upper bound of the change point | CPI 03-12 12:30 |
| 5 | 2019/44 | 10-28 | US-only | H2 vs H3, post-change; repeated hour on Sunday 10-27 | FOMC 10-30 18:00; Payrolls 11-01 12:30 |
| 6 | 2024/43 | 10-21 | both summer | H1 vs H2/H3, late era | none verified |
| 7 | 2024/44 | 10-28 | US-only | C5: Sunday 10-27 open vs weekday H3 | Payrolls 11-01 12:30 |
| 8 | 2024/45 | 11-04 | both standard | US-end Sunday 11-03; control | FOMC 11-07 19:00 |

- **Late-era summer control:** week 6 is the only both-summer week in the late era. Without it, H1 vs H3 in that era rests on internal evidence alone.
- **Change point:** cannot be pinned more finely than the gap between 2018-11-04 and 2019-03-10, since every week in between is both-standard.

## 2. Usage status

| Group | Dates | Status | Why |
|---|---|---|---|
| **A. Usable now (already local)** | HistData 2015–2026; Dukascopy 2025-03-19; FXCM `53.csv` (2019-12-29 to 2020-01-03) | Usable for read-only research | Files are on disk and audited. `53.csv` was saved by you; it falls within the README years. |
| **B. Pending your confirmation** | Weeks 1–4 (2018–2019, all in the planned list) | Not yet fetchable | Inside the README's documented years 2017–2020 with "personal use" wording, but the EULA is unread and FXCM's email is **not on file**. |
| **B′. Pending confirmation plus approval as an addition** | Week 5 (2019/44) | Not yet fetchable | Same as B. It is also **not in the planned list**; availability comes only from the 2026-10-22 probe (HTTP 206, 132,928 B). |
| **C. Permission must be clarified** | Weeks 6–8 (2024/43–45); tier-2 2024-W11; anything outside 2017–2020 | Not usable | Outside the README years, and nothing on record grants permission. Not assumed. |

Group A cannot separate the hypotheses:
- `53.csv` is both-standard.
- Dukascopy is probably HistData's upstream, so it isn't independent.

So **no decisive test can run until group B is cleared.**

## 3. Action checklist

| Step | Action | Depends on | Who | Expected output | Acceptance criterion |
|---|---|---|---|---|---|
| 0 | Save FXCM's email reply (text, date, sender) under `docs/` or `reports/` | none | **You** | Recorded terms | It states whether personal research use is allowed and which years it covers |
| 1 | Approve fetching weeks 1–5 (about 0.71 MB) | 0 | **You** | Written approval | Covers each listed week, including week 5 as an addition |
| 2 | Pre-register the analysis | none (can run now) | Me | Frozen thresholds and event list in a dated file, written before any fetch. Thresholds: r ≥ 0.3, ratio ≥ 3, ≥ 300 shared minutes, ≥ 90 % match, ≥ 5 decisive days per regime. Events as in §1. | File hash recorded before step 3 |
| 3 | Fetch weeks 1–5 into a new `reference/fxcm/` folder, unmodified | 1, 2 | Me | `.csv.gz` files, SHA-256 manifest, HTTP Last-Modified per file | The manifest verifies, and no other file changes |
| 4 | Check that each file's content matches its intended week | 3 | Me | First and last timestamp per file | Each file spans Sunday evening to Friday of the intended week. Otherwise the file is excluded, not re-labelled. |
| 5 | Audit each file (existing `fxcm_audit` checks) | 4 | Me | Report with schema, gaps, bid/ask and spread checks | Schema matches `53.csv`, and the results are documented |
| 6 | Validate FXCM's UTC claim on its own | 5 | Me | Activity at each documented event, at 0 and ±60 min | The peak falls at the documented UTC minute for every event with a clear spike, in summer and US-only weeks too. If any fails, FXCM cannot serve as the reference. |
| 7 | Run the per-day offset scan against HistData | 6 | Me | For each day: best offset, correlation, ratio, decisive flag, and the offset each hypothesis predicts | Day results are computed only under the pre-registered rules |
| 8 | Write an interim (exploratory) result by era and regime | 7 | Me | Report, with no conversion | States which hypotheses each era fits, and how many decisive days are still missing |
| 9 | Clarify 2024 permission with FXCM; if covered, approve weeks 6–8 | 0 | **You** | Recorded permission and approval | Explicitly covers 2024 |
| 10 | Repeat steps 3–8 for weeks 6–8 | 9 | Me | C5 evidence, late-era summer control | Same as steps 4–7 |
| 11 | Add tier 2 and a second independent UTC reference | 8, 10, your choice of source | Both | Enough decisive days with margin; a cross-check of FXCM | See §4 |
| 12 | Propose a timezone rule (not apply it) | 11 | Me | Policy report for your approval | Only if §4 is fully met |

## 4. Evidence required before choosing a timezone rule

All of the following must hold, per era. The era boundary is itself part of the test.

1. **The reference is validated.** FXCM's labels place documented events at the correct UTC minute in all three regimes, not only in winter. So does a second reference that is independent of both FXCM and HistData's upstream.
2. **Enough decisive days.** At least 5 decisive days per regime per era, under the pre-registered rule. Aim for at least 10 weekdays per cell for margin.
   - **Pre-change era:** both_standard (currently 0 planned in tier 1), both_summer, and the US-only window.
   - **Post-change era:** both_standard, both_summer, and the US-only window.
3. **Match rate.** At least 90 % of decisive days match the chosen candidate's predicted offset exactly. Contradicting days must be listed and explained, not dropped.
4. **The change point is bracketed.** The last US-only window that fits H2 and the first that fits H3 must both be confirmed by the reference. The rule must state that the change date is only known to lie between 2018-11-04 and 2019-03-10. The other option is to mark that winter as indeterminate; it is harmless, since all hypotheses agree in both-standard.
5. **Year-level consistency.** At least one decisive US-only window per year is needed in each era, or the years without one must be explicitly flagged. This is how a one-year exception like 2024 can be detected.
6. **The 2024-10-27 Sunday is resolved.** The reference must show whether it follows H2 or H3 with the first hour missing; that decides whether C5's exception is needed.
7. **Minute labelling.** Check that the best offsets fall on whole hours (start-of-minute labels) rather than ±1 minute.
8. **The artefacts are explained.** Show whether the 19:00 hole in March and the repeated hour in October on EU-switch Sundays are missing data or copied data. These hours get quality flags whichever rule is chosen.

**Until all eight hold, C6 (no conversion) remains the policy.**

## 5. Safety and tests

- **Hashes:** all files under `data/` and `reports/` plus the four Parquet files were hashed before and after this task (see `source_hashes_check.txt`). They were unchanged; the only new file is in this folder.
- **Tests:** results are recorded in `source_hashes_check.txt`.
- **No network requests** were made.
