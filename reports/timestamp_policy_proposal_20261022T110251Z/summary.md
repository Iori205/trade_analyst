# Timestamp reference sources and policy proposal

Created 2026-10-22 (UTC). **This is a proposal only.** No data was downloaded, converted, cleaned or modified. No timezone conversion is chosen.

Builds on `reports/timestamp_investigation_20261022T104848Z/` (decision_table.csv).

Machine-readable files in this folder:

| File | Content |
|---|---|
| `candidate_timezone_decisions.csv` | Timezone candidates C1–C6: evidence for and against, confidence, data needed |
| `reference_sources.csv` | Independent reference options: timestamp basis, price type, coverage, access, terms |
| `comparison_plan.csv` | Sample dates per period and what each sample decides |
| `data_policy_proposals.csv` | P1–P5: duplicates, conflicts, gaps, 2023, Parquet regeneration |
| `source_hashes_check.txt` | SHA-256 verification of the 42 original files after this task |

## 1. Where the evidence stands

The previous investigation used only HistData itself (event anchors and weekly opens). Its conclusions:
- Fixed UTC−5 (the HistData FAQ claim) is contradicted in summer in both eras.
- 2015–2018 behaves like America/New_York.
- 2019–2026 behaves like New York offsets that switch on EU dates. The change falls between the autumn-2018 and spring-2019 windows.
- Autumn 2024 is internally inconsistent.
- The March holes and October repeats on EU switch Sundays are not the clock change itself.

All of this is internal evidence. **No independent UTC-stamped data is available locally.** The only other EURUSD files on this machine are HistData copies: the backup, `~/Desktop/EURUSD data`, and the ZIPs in `~/Downloads`. None of them is independent.

## 2. Independent reference options

Nothing was downloaded and nothing was signed up for. Terms of use were not reviewed in detail for any source.

| Source | UTC basis | Price type | Coverage | Access | Main limitation |
|---|---|---|---|---|---|
| FXCM MarketData | **Documented** ("Timestamps are in UTC") | Not documented | m1, 2017–2020 | Public URLs; personal use under FXCM EULA | Short coverage; price side unknown |
| OANDA v20 candles | **Documented** (UTC regardless of alignment settings) | Selectable mid, bid or ask | Long (M1 depth unconfirmed) | Account plus API token (practice account possible) | Needs an account; rate limits |
| Massive (ex-Polygon) forex aggregates | **Documented** (Unix ms, start of window, UTC) | "From quoted bid/ask"; OHLC side not stated | Since 2009-09-25 | Paid plan for full history | Cost; empty minutes omitted |
| Dukascopy | Reported GMT, not stated on the official page; DST oddities reported in some exports | Bid and ask (reported) | Long | Free export tool; JForex needs a demo login | Must self-verify timestamps; prefer building bars from ticks |
| TrueFX | Not stated | Top-of-book ticks | Reportedly since 2009 | Free registration | Timezone undocumented |
| LSEG / Bloomberg | Documented | Quotes and trades | Long | Institutional licence | Cost |

Rejected as not independent: FX-1-Minute-Data on GitHub (a re-host of HistData) and all local HistData copies.

**Recommended combination, if approved:**
- FXCM m1 for 2017–2020. It documents UTC, needs no login, and covers the 2018/2019 change point.
- A second source covering every period: OANDA (bid candles) if you can open a practice account, otherwise Dukascopy ticks.
- First, check each reference's own UTC claim on documented-time events (US 08:30 releases). A single reference must not be trusted blindly.

## 3. Comparison methodology (to run after approval)

**Principle.** Timing is inferred from *when price changes happen*, not from *price levels*. Price levels from different vendors differ by spread and liquidity pool and are strongly autocorrelated, so they "match" at many lags. Returns at 1-minute resolution are close to uncorrelated across lags, so the correct alignment stands out sharply.

### A. Timezone-alignment evidence (decisive)
1. Build 1-minute log returns from each source on its own clock: HistData on the naive source clock, the reference in UTC. Use only minutes present in both. Never fill missing minutes.
2. For each sampled day, shift HistData by candidate offsets k from −360 to +360 minutes in 1-minute steps. Compute the correlation of returns with the reference, and its rank (Spearman) variant.
3. The best lag is L_d. A day counts as **decisive** if both hold:
   - correlation at L_d is at least 0.3;
   - it is at least 3× the best correlation outside L_d ± 1 minute.
4. Each candidate (C1–C5) predicts a lag per day. A candidate is accepted for a period only if:
   - at least 90% of decisive days match its prediction exactly;
   - each regime in the period (both_standard, both_summer, US-only DST window) has at least 5 decisive days.
5. **Minute-level labelling.** If L_d is consistently ±1 minute away from a whole-hour offset, one source labels bars by end time. Record that as a separate finding.
6. **Event check on the reference itself.** US 08:30 releases must appear at 12:30 or 13:30 UTC in the reference, and the London fix at 15:00 or 16:00 UTC. This validates the reference's UTC claim independently of HistData.

These thresholds should be fixed before any reference data is examined.

### B. Price-similarity evidence (supporting only)
- Level difference at the best lag. For bid-vs-bid it should be near zero. For bid-vs-mid it should be roughly half the spread, about 0.1–0.5 pip for EURUSD; this range is an assumption to measure, not a fact.
- Median absolute close difference, and the share of minutes within 1 pip.
- This evidence is used to judge data quality (outages, the 2026-07-05 conflicts, the copied October hours), **never** to choose a timezone on its own.

### C. Controls for vendor and construction differences
- **Price type:** compare HistData (bid) with reference bid where available. Otherwise compare returns only, since a constant half-spread offset cancels in returns.
- **Spread spikes:** exclude 16:55–17:15 New York rollover minutes and the first 15 minutes after the Sunday open from the correlation step, and report them separately. Spreads widen there and can distort returns.
- **Bar construction:** some vendors omit empty minutes and others repeat the previous close. Restrict to minutes with a bar in both sources; report coverage per source.
- **Missing bars:** report the intersection size per day. If fewer than 300 shared minutes, the day is not decisive.
- **Vendor differences:** expect correlation well below 1 because of different liquidity pools. Interpret the *peak sharpness* (ratio to the next-best lag), not the absolute level.
- **Null check:** for each day, the best correlation at random lags at least 30 minutes from L_d should be near zero. If it isn't, the day is excluded.

### D. Sampling plan
Full list in `comparison_plan.csv`:
- **2015–2018:** January (control), July, and the US-only DST windows each year.
- **2018–2019 change point:** every week from 2018-10-21 to 2019-04-07.
- **2019–2023:**
  - controls and windows each year;
  - EU switch Sunday evenings (16:00–22:00 source clock);
  - all intraweek gaps over 30 minutes in February–July 2023, to test whether the outage is HistData-specific.
- **2024:** every day from 2024-03-08 to 04-05 and from 2024-10-20 to 11-10, including the Sunday evenings of 10-27 and 11-03 with tick-level data. Also 2024-01-16.
- **2025–Aug 2026:** the 2025 and 2026 spring windows, the 2025 autumn window (non-decisive internally), controls, the 2026-05-12 and 05-22 gaps, and 2026-07-05 17:00–18:00.

## 4. Candidate timezone decisions

| ID | Candidate | Confidence now | Status |
|---|---|---|---|
| C1 | Fixed UTC−5 (HistData FAQ) | Low: contradicted in summer, both eras | Not recommended |
| C2 | America/New_York throughout | Low overall; fits 2015–2018 only | Not recommended |
| C3 | New York offsets on EU dates throughout | Low overall; fits 2019–2026 only | Not recommended |
| C4 | **Piecewise: C2 until a change point (late 2018 to early 2019), then C3** | **Moderate, internal evidence only** | **Leading candidate to test; not approved** |
| C5 | C4 plus an exception for the 2024-10-27 Sunday evening | Low until the reference is checked | Pending |
| C6 | Keep the naive source clock (no conversion) | n/a | **Current default** |

Evidence for and against each candidate is in `candidate_timezone_decisions.csv`.

**No final UTC conversion is chosen.** The evidence comes from a single vendor's own data. C4 should only be adopted if the reference comparison accepts it under the rule in §3A, and if T_change and the autumn-2024 behaviour are pinned down.

## 5. Proposed data policies (not implemented)

Details are in `data_policy_proposals.csv`. Every policy applies only to a **new derived dataset**; the raw files stay untouched.

- **P1 — Identical duplicates** (6 October blocks):
  - keep one row per timestamp;
  - record the removed copy's file and line numbers in a provenance table;
  - if the reference shows the copy replaced a real hour, also flag that hour and exclude it from feature and label windows.
- **P2 — Conflicting duplicates** (2026-07-05, 4 minutes):
  - set those minutes to missing and flag them `conflicting_duplicate`;
  - keep both variants in provenance;
  - pick a variant only with decisive reference evidence;
  - never pick silently by row position. The existing Parquet files did exactly that: they kept the first occurrence.
- **P3 — Missing minutes and outages:**
  - never fill, forward-fill or interpolate;
  - keep a sparse index with per-bar gap and closure flags;
  - mask any feature window or label that crosses a long gap;
  - resampled bars carry completeness counts.
- **P4 — 2023 low-quality period:**
  - flag February–July 2023;
  - exclude it from training and evaluation metrics by default, with a sensitivity analysis that includes it;
  - do not splice in another vendor's data;
  - optionally compare against a fresh HistData download or the local 2023 ZIP, read-only and with approval.
- **P5 — Parquet regeneration:**
  - keep the 4 existing Parquet files as read-only legacy;
  - write new versioned files under `data/processed/`, with UTC index or source clock, the original timestamp string, file and line provenance, quality flags, and a manifest of input hashes, policy version and code version;
  - resample from the derived M1 with completeness counts and a documented bin alignment;
  - never overwrite.

## 6. Decisions needed from the owner
1. Which reference source(s) to use, and whether you accept the terms: FXCM (personal-use EULA), an OANDA practice account, Dukascopy, or a paid source.
2. Approval to download the specific samples in `comparison_plan.csv`. It's a few weeks per year, not full history.
3. Approval of the pre-registered decision rule in §3A, or different thresholds.
4. The open choices listed per policy in `data_policy_proposals.csv`.

## 7. Sources consulted (2026-10-22)
- HistData FAQ: https://www.histdata.com/f-a-q/
- FXCM MarketData README: https://github.com/fxcm/MarketData
- OANDA v20 Instrument Endpoints: https://developer.oanda.com/rest-live-v20/instrument-ep (direct fetch returned 404; details from the search summary)
- Massive (Polygon) forex custom bars: https://massive.com/docs/rest/forex/aggregates/custom-bars
- Dukascopy historical data: https://www.dukascopy.com/swiss/english/marketwatch/historical/ ; forum reports such as https://www.dukascopy.com/swiss/english/forex/jforex/forum/viewtopic.php?p=89668 and https://support.tickstory.com/viewtopic.php?p=10270
- TrueFX historical downloads: https://www.truefx.com/truefx-historical-downloads/
- FX-1-Minute-Data (HistData re-host): https://github.com/philipperemy/FX-1-Minute-Data
