# FXCM reference-data access check: stopped before retrieval

Date: 2026-10-22 (UTC). **No reference data was downloaded.** You chose to confirm FXCM's terms first. No comparison was run, no conversion or cleaning was done, and the timezone stays **unresolved**. The default is still C6: the naive source clock.

## 1. Documentation reviewed
Sources: the FXCM MarketData README (raw GitHub, fetched 2026-10-22), the example script `CandleData(pandas).py`, and GitHub repository metadata.

| Item | Finding |
|---|---|
| Offer | "FXCM provide several sample data for free. Historical candle data." |
| Timestamps | "Timestamps are in UTC" (README note) |
| Price type | **Not documented.** The README doesn't say whether candles are bid, ask or mid, or whether there are separate bid/ask columns. Only file contents would show this. |
| Quality note | "Data points are indicative and based on the lowest spreads available exclusively on Active Trader accounts" |
| Schema | **Not documented** in the README. The example script reads files with `pd.read_csv(..., compression='gzip')` and shows no columns. |
| Week numbering | The example script uses `date.isocalendar()` (ISO weeks). This is assumed, not verified against file contents. |
| Documented years | 2017, 2018, 2019, 2020 |
| Terms | "This is for personal use and abides by our EULA" with a link to https://www.fxcm.com/uk/forms/eula/ |
| EULA content | That page ("FXCM Software End User License Agreement") only links to an e-signature form. **The clauses can't be read without using the form**, and I didn't. |
| Repository licence | None (GitHub API `license: null`) |

**Why I stopped:** permission for personal use is stated, but the agreement it refers to can't be read. It is also unclear whether a *software* licence governs the data files, and whether files outside the documented 2017–2020 range are covered at all.

## 2. Coverage actually served
I probed each weekly file by requesting only its first byte, so **no candle data was retrieved**. Results are in `fxcm_m1_eurusd_coverage.tsv`.

| Year | Weekly files available (HTTP 206) |
|---|---|
| 2012 | 53 / 53 (spot check) |
| 2015, 2016, 2017 | 52 each (week 53 missing) |
| 2018 | 53 |
| 2019, 2020 | 52 (week 1 missing) |
| 2021, 2022 | 52 |
| 2023 | 53 |
| 2024 | 48 (weeks 1, 35, 51, 52, 53 missing) |
| 2025 | 49 (weeks 1, 2, 29, 30 missing) |
| 2026 | 27 (weeks 1–17 and 32–41) |

- **Total:** 647 files, about 126 KB on average.
- **Outside the README:** coverage goes well beyond the documented 2017–2020. It includes October 2024 (ISO weeks 43–44) and the full October 2018 – April 2019 change period, except ISO week 1 of 2019.
- **Revisions:** some files have Last-Modified dates long after their week, for example 2019 week 13 modified 2020-01-15. FXCM may revise files after publication.
- **Access quirk:** the CDN (Cloudflare) answered 403 to my Python HEAD requests but served files to curl. Automated access may be filtered.

## 3. Prepared, not executed
`planned_fetch_list.csv` lists the minimum files needed for the priority samples:

| Sample | Purpose | Files | Size |
|---|---|---|---|
| A1, A2 | Winter and summer controls, 2015–2018 | 12 | 1.8 MB |
| A3 | US-only DST windows, 2015–2018 | 21 | 3.1 MB |
| B0 | Change point, 2018-10-21 to 2019-04-07 | 23 | 3.1 MB (2019 week 1 unavailable) |
| B1 | Winter and summer controls, 2019–2023 | 15 | 1.7 MB |
| C2 | October 2024 anomaly | 4 | 0.4 MB |

That's 75 files in total (74 available, about 10 MB). 44 of them are in the documented 2017–2020 years.

If approved, the files would be stored in a separate `reference/fxcm/` folder, unmodified, with a SHA-256 manifest. They would never be merged into the HistData data. The comparison would follow the decision rules already fixed in `reports/timestamp_policy_proposal_20261022T110251Z/summary.md` §3.

## 4. Draft enquiry to FXCM
Send it yourself if you wish; I have not contacted anyone. A copy is in `fxcm_terms_enquiry_draft.txt`.

## 5. Recommended next decision
1. **Ask FXCM** (api@fxcm.com) to confirm the terms. Specifically: is non-commercial personal research use of the candle files permitted, does that cover all served years or only 2017–2020, and are the candles bid, ask or mid?
2. **In parallel, choose a second reference.** An OANDA practice account gives documented UTC and selectable bid/ask/mid candles; it needs your sign-up and acceptance of OANDA's API terms. Dukascopy is the other option. Two independent references are needed anyway, so one vendor's UTC claim isn't a single point of failure.
3. Until then, keep timezone candidate C6 (no conversion). Leave all data and the four Parquet files untouched.

## 6. Safety
See `source_hashes_check.txt`. The 42 original files were verified unchanged after this task, and the test suite was run.
