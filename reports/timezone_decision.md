# Timezone decision: HistData EURUSD M1 source clock

Written 2026-10-26 (UTC), as a recommendation for review.

> **Status update (2026-10-26):** the project owner **approved C4 as the timestamp policy** (version `C4-v1`, era boundary 2018-12-16). It has been applied only to a new derived dataset, `data/processed/eurusd_m1/v1/` (§8).
> - The raw HistData files and the legacy Parquet files are unchanged.
> - `config/research.yaml` still says `source_timezone: UNVERIFIED` for the audit modules, which read raw labels only. The policy for derived data is recorded in the dataset manifest.

## 1. Recommended rule

**C4: a piecewise rule with an era boundary at 2018-12-16.**

| HistData label date | Source clock (label =) | UTC = label + |
|---|---|---|
| before 2018-12-16 | **H2:** America/New_York local time | 5 h in US standard time; 4 h in US DST |
| from 2018-12-16 | **H3:** Europe/Zurich local time − 6 h | 5 h in EU standard time; 4 h in EU summer time |

**The boundary date is not identified by the data, and it doesn't need to be.**
- The last H2-like weekday is 2018-11-02 and the first H3-like weekday is 2019-03-11.
- Every weekday and Sunday session in between is both-standard, where H2 and H3 give the same offset (+300).
- So any boundary from 2018-11-04 to 2019-03-10 converts every bar identically. 2018-12-16 is a conventional choice inside that span.

**Confidence: high for the tested years. Moderate for the untested years**, where the rule relies on HistData's own anchors and the Sunday opens (§5).

## 2. Evidence by era: FXCM reference

**Reference:** FXCM m1 bid candles. FXCM documents them as UTC, and their UTC labels are validated in §3.
- **Files:** 11 weekly files, 10 fetched under `data/reference/fxcm/v1/` (manifest and SHA-256 there) plus `data/fxcm/53.csv`.
- **Method:** `src/data/fxcm_tz_compare.py`. Per UTC weekday, 1-minute return correlation over offsets from −720 to +720 min.
- **Pre-registered day rule:** r ≥ 0.3, at least 3× the best correlation outside ±1 min, and ≥ 300 shared minutes.
- **Exclusions:** weekends (11 Sundays), holiday candidates (Dec 31 and Jan 1) and long gaps, each with its reason. Rollover minutes and the first 15 minutes after a gap are dropped at minute level.
- **Outputs:** `reports/fxcm_tz_comparison_20261026T152233Z/`. The earlier `…152042Z` run is superseded (file names collided across years) and kept.

**Decisive days per era and DST regime** (counted days; every one passed the day rule):

| Era | Regime | Decisive days | Offsets seen | H1 match | H2 match | H3 match |
|---|---|---|---|---|---|---|
| before 2018-12-16 | both standard (2018/45) | 5 | +300 ×5 | 5 | 5 | 5 |
| before 2018-12-16 | both summer (2018/43) | 5 | +240 ×5 | **0** | 5 | 5 |
| before 2018-12-16 | US-only window (2018/12, 2018/44) | 10 | +240 ×10 | **0** | 10 | **0** |
| from 2018-12-16 | both standard (53.csv, 2020/3) | 8 | +300 ×8 | 8 | 8 | 8 |
| from 2018-12-16 | both summer (2019/29, 2025/28) | 10 | +240 ×10 | **0** | 10 | 10 |
| from 2018-12-16 | US-only window (2019/11, 2019/44, 2024/11) | 15 | +300 ×15 | 15 | **0** | 15 |

**Candidate verdicts** (`verdicts.csv`; at least 5 decisive days per cell, at least 90% matching):

| Candidate | Cells passed (of 6) | Contradicted in |
|---|---|---|
| **C4: H2, then H3 at 2018-12-16** | **6** | none (53/53 decisive days match) |
| C2: New York throughout | 5 | from-2018-12-16 US-only (0/15) |
| C3: Zurich − 6 h throughout | 5 | before-2018-12-16 US-only (0/10) |
| C4r: H3, then H2 | 4 | both US-only cells (0%) |
| C1: fixed UTC−5 | 3 | both summer cells and the before-2018-12-16 US-only cell (0%) |

The runner-up candidates, C2 and C3, each fail one whole regime cell at 0%, so they are clearly worse.

**Per-week table** (`weekly.csv`: one row per week and test). Best and second offsets come from the whole-week scan:

| Week | Era | Regime | Best (r) | Second (r) | Peak ratio | Close median / p95 abs diff (pips) at C4 offset | At rival offset |
|---|---|---|---|---|---|---|---|
| 2018/12 | before | US-only | +240 (0.988) | +269 (0.052) | 19.2 | 0.1 / 0.4 | H1/H3 +300: 5.5 / 22.2 |
| 2018/43 | before | summer | +240 (0.985) | +284 (0.042) | 23.3 | 0.1 / 0.4 | H1 +300: 4.6 / 20.6 |
| 2018/44 | before | US-only | +240 (0.988) | −45 (0.044) | 22.5 | 0.1 / 0.4 | H1/H3 +300: 4.8 / 21.5 |
| 2018/45 | before | standard | +300 (0.985) | +246 (0.045) | 21.7 | 0.2 / 0.4 | (all agree) |
| 2019/53 (53.csv) | from | standard | +300 (0.990) | −692 (0.051) | 19.5 | 0.1 / 0.2 | (all agree) |
| 2019/11 | from | US-only | +300 (0.991) | +29 (0.034) | 29.2 | 0.1 / 0.2 | H2 +240: 3.4 / 15.5 |
| 2019/29 | from | summer | +240 (0.991) | +242 (0.038) | 26.0 | 0.1 / 0.2 | H1 +300: 3.0 / 12.9 |
| 2019/44 | from | US-only | +300 (0.991) | +304 (0.054) | 18.5 | 0.1 / 0.2 | H2 +240: 2.9 / 12.7 |
| 2020/3 | from | standard | +300 (0.989) | +399 (0.038) | 25.8 | 0.1 / 0.2 | (all agree) |
| 2024/11 | from | US-only | +300 (0.989) | +280 (0.043) | 22.8 | 0.1 / 0.2 | H2 +240: 2.5 / 11.8 |
| 2025/28 | from | summer | +240 (0.986) | +279 (0.046) | 21.6 | 0.1 / 0.4 | H1 +300: 5.1 / 18.9 |

**Reading the table:**
- **Exact labels (k = 0)** never match: close median 5.5–12.8 pips, 0% identical OHLC. HistData is not on UTC.
- **Timestamp match %** (a FXCM bar has a HistData bar at the predicted label) is 98.7–100% at *every* candidate offset, because both feeds have nearly every minute. So it does **not** separate the hypotheses. The return correlation and the pip differences do.
- **Not a copy:** at the C4 offset only 0.2–5.6% of bars have all four OHLC fields identical, with a median close difference of 0.1 pip. FXCM and HistData are distinct feeds, so FXCM is not merely echoing HistData.

## 3. Is FXCM itself on UTC? (validation of the reference)

**Event check** (`fxcm_event_check.csv`): FXCM's 1-minute activity at documented release times, compared with ±60 min.

| Event (UTC) | FXCM week | Ratio to median at 0 / −60 / +60 | Strongest |
|---|---|---|---|
| FOMC 2018-03-21 18:00 | 2018/12 (US-only) | 44.9 / 5.0 / 10.1 | 0 |
| Employment Situation 2018-11-02 12:30 | 2018/44 (US-only) | 14.0 / 0.9 / 3.0 | 0 |
| FOMC 2018-11-08 19:00 | 2018/45 (standard) | 18.8 / 2.7 / 5.4 | 0 |
| CPI 2019-03-12 12:30 | 2019/11 (US-only) | 12.0 / 3.8 / 5.2 | 0 |
| FOMC 2019-10-30 18:00 | 2019/44 (US-only) | 27.8 / 1.5 / 17.0 | 0 |
| Employment Situation 2019-11-01 12:30 | 2019/44 (US-only) | 35.3 / 3.5 / 4.3 | 0 |
| ISM 2020-01-03 15:00 / FOMC minutes 19:00 | 53.csv | earlier audit: 0 for both | 0 |

- **Dates:** event dates are from the Federal Reserve FOMC calendars and the BLS release archives.
- **FXCM session opens:** each FXCM week starts at 21:00 UTC in US-DST weeks and at 22:00 UTC in winter. That equals 17:00 New York in UTC, so it is consistent with UTC labels.

## 4. Supporting evidence

**Dukascopy 2025-03-19** (`reports/reference_compare_dukascopy_2025-03-19_20261026T061109Z`):
- This is a US-only DST day after the boundary. The best offset is **+300** (r = 1.0), and the FOMC 18:00 UTC spike falls at HistData label 13:00.
- That matches H1 and H3 and rejects H2, consistent with C4.
- **Not independent:** 100% of OHLC are identical, including the same missing minute, so Dukascopy is almost certainly HistData's upstream. This counts only as supporting evidence.

**Sunday opens** (`reports/sunday_opens_20261026T150036Z/`; raw HistData, first Sunday bar per week, compared with the 17:00 New York open under C4):

| Era | Regime | Weeks | First-bar hour consistent with C4 |
|---|---|---|---|
| before 2018-12-16 | standard / summer / US-only | 67 / 123 / 13 | 67 / 123 / 13 (all) |
| from 2018-12-16 | standard / summer / US-only | 138 / 236 / 28 | 136 / 226 / 26 |

**The 14 inconsistent weeks are all late opens, never early ones:**
- 1 is 2019-05-26 at 23:00.
- 11 fall in 2023: 03-05, 03-19, 04-23 to 07-16, and 12-24. Most of them are in the known February–July 2023 low-quality period.
- 1 is 2024-10-27.

A late first bar is what a missing first hour or hours looks like. A clock difference would be needed to explain an early open, and none occurs. These weeks are consistent with C4 plus missing data, but are not proven to be that.

**2019-10-27 repeated hour** (EU-end Sunday): HistData labels 19:00–19:59 appear twice (source rows 305958–306077). **Both copies match FXCM at +300** (median close difference 0.1 pip, against 3.15 at +360). The repeat is a duplicated copy of the correct hour, not a shifted hour.

## 5. Years not covered by the independent reference

**FXCM-tested years:** 2018, 2019, 2020, 2024 and 2025.

**Not covered by FXCM:**
- **2015, 2016 and 2017:** the before-boundary rule relies on HistData's internal anchors (fit H2) and the Sunday opens (all consistent).
- **2021, 2022, 2023 and 2026:** the from-boundary rule relies on internal anchors (fit H3) and the Sunday opens.
- **Pre-boundary FXCM coverage is one year only** (2018).

## 6. Remaining risks

1. **Single independent reference.** Only FXCM is independent of HistData. Its UTC labelling is validated by 7 events and its session opens, but a second vendor has not been checked.
2. **2024-10-27 and 2023-03-19 Sunday evenings.** Under C4, the 17:00 first bar means the expected 16:00–16:59 hour is missing. It is not verified that the data is missing rather than mislabelled; FXCM 2024/44 would show which. These hours should be flagged.
3. **March EU-switch-Sunday holes (19:00–19:59, 2019+)** remain gaps. Under C4 the clock is continuous that evening, so they are missing data, not a clock jump. The **October repeats** are identical copies (§4), to be handled by duplicate policy P1.
4. **The 2026-07-05 conflicting duplicates** are untouched by this decision (policy P2).
5. **Price type: resolved.** FXCM's reply of 2026-10-23 states "The bar prices are bid OHLC and ask OHLC" and "Yes UTC". This matches the bid-vs-bid differences of about 0.1 pip.
6. **Terms: partly resolved.** The email is saved as `docs/approvals/fxcm_email_2026-10-23.txt` (SHA-256 `fea0f56c…98f0d`, kept out of git), and `fxcm_batch1.md` now points to it.
   - FXCM's reply says "You can use it for personal use." **It states no year range.** The question of which years are covered was not answered.
   - Use of the 2024 and 2025 weeks therefore rests on that general statement plus the owner's attestation.
7. **The 2015–2017 and 2021–2023/2026 conversions** rely on internal evidence only (§5). Any later finding there would require a new dataset version (v2), not an edit to v1.

## 7. Next action (needs approval)

Approve C4 as the timestamp policy. After approval, the next stage would:
- build a **new, versioned derived** M1 dataset under `data/processed/` with a UTC index computed by the C4 rule;
- keep the original label text and file/line provenance;
- flag the late-open Sunday hours, the EU-switch holes, the October repeats (per P1) and the 2026-07-05 conflicts (per P2);
- leave raw files and the existing Parquet files untouched.

Before that, you may optionally:
- save the FXCM email under `docs/approvals/`;
- approve FXCM 2024/44 to settle risk 2.

## 8. Applied: processed dataset `data/processed/eurusd_m1/v1/`

Built by `src/data/processed_m1.py` on 2026-10-26.

**Files:** `eurusd_m1_utc.parquet`, `late_open_sundays.csv`, `manifest.json` and `SHA256SUMS.txt`.

- **Rows:** 4,289,924 output rows, equal to the 4,289,924 input rows in 19 raw files. Nothing was filled, deduplicated or dropped.
- **Range:** UTC 2015-01-01 18:00 to 2026-09-01 03:58. The output is stably sorted by `timestamp_utc`, then source file, then source line.
- **Columns:**
  - `timestamp_utc`
  - `source_timestamp_text` (exact raw text), `source_label`, `source_file`, `source_line` (1-based)
  - OHLC and volume
  - `source_era`, `source_clock_rule`, `utc_offset_minutes`
  - the flags below

**Flags** (counts are rows):

| Flag | Rows | Meaning |
|---|---|---|
| `gap_before` / `gap_before_minutes` | 13,535 | Missing UTC minutes before the bar (weekends included) |
| `duplicate_identical` | 720 | Six identical repeated hours, both copies kept |
| `duplicate_conflict` | 8 | 2026-07-05, four minutes with two differing copies, both kept |
| `low_quality_period` | 136,100 | UTC 2023-02-01 to 2023-07-31 |
| `suspect_late_open` | 4,082 | Whole Sunday sessions of the 14 late-open weeks (§4), listed in `late_open_sundays.csv` |
| `dst_transition_hour` | 19,718 | Sunday-session rows on US and EU DST switch Sundays |
| `utc_unresolved` | 0 | Nonexistent or ambiguous local labels (none occur) |

**Checks:**
- `timestamp_utc` is non-decreasing. Offsets per era are −240/−300 min only.
- Re-joining with FXCM 2018/12, 2019/11 and 2024/11 at exact UTC gives a median close difference of 0.1 pip.
- All raw and legacy Parquet SHA-256 values are unchanged (recorded in the manifest).

**Manifest:**
- **Contents:** policy (C4-v1, boundary, evidence file SHA-256), SHA-256 and row count per input file, SHA-256 of each script, output SHA-256 and rows, flag counts, and the Python, pandas and pyarrow versions.
- **`git_commit` is null,** because the project is not a git repository; the script SHA-256 values identify the code version instead.
