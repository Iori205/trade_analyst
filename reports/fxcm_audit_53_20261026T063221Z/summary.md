# FXCM M1 audit: `data/fxcm/53.csv` (read-only)

Generated (UTC): 2026-10-26 06:32:21. No file was modified, shifted, filled or converted. Tracked files unchanged during run: **YES** (44 files).

## 1. File

`{"bytes": 441558, "gzip_magic": false, "data_rows": 5010, "trailing_newline": true}`. Gzip-compressed: **no (plain CSV text)**. The file contains no instrument column; EURUSD is inferred from price levels and the HistData match below.

## 2. Schema (all fields read as text first)

| column | stored_as | empty_values | parsed_dtype | fraction_nonzero_ms | non_numeric | min | max | max_decimals_written | decimals_distribution |
|---|---|---|---|---|---|---|---|---|---|
| DateTime | text | 0 | datetime64 (naive label) | 0.0 | nan | nan | nan | nan | nan |
| BidOpen | text | 0 | float64 | nan | 0.0 | [redacted] | [redacted] | 5.0 | 2:17,3:35,4:415,5:4543 |
| BidHigh | text | 0 | float64 | nan | 0.0 | [redacted] | [redacted] | 5.0 | 2:15,3:43,4:440,5:4512 |
| BidLow | text | 0 | float64 | nan | 0.0 | [redacted] | [redacted] | 5.0 | 2:18,3:44,4:393,5:4555 |
| BidClose | text | 0 | float64 | nan | 0.0 | [redacted] | [redacted] | 5.0 | 2:17,3:35,4:416,5:4542 |
| AskOpen | text | 0 | float64 | nan | 0.0 | [redacted] | [redacted] | 5.0 | 2:7,3:39,4:461,5:4503 |
| AskHigh | text | 0 | float64 | nan | 0.0 | [redacted] | [redacted] | 5.0 | 2:10,3:54,4:442,5:4504 |
| AskLow | text | 0 | float64 | nan | 0.0 | [redacted] | [redacted] | 5.0 | 2:11,3:43,4:407,5:4549 |
| AskClose | text | 0 | float64 | nan | 0.0 | [redacted] | [redacted] | 5.0 | 2:7,3:39,4:462,5:4502 |

Date order: `{"first_field_max": 12, "second_field_max": 31, "verdict": "MM/DD/YYYY (established: second field exceeds 12)"}`. Timestamps carry **no timezone designator**; FXCM's statement that they are UTC is documentation, not something the file establishes.

## 3. Coverage, ordering, duplicates (label clock)

`{"rows": 5010, "first_label": "2019-12-29 22:03:00", "last_label": "2020-01-03 21:59:00", "min_label": "2019-12-29 22:03:00", "max_label": "2020-01-03 21:59:00", "monotonic_increasing": true, "rows_not_after_previous": 0, "duplicate_timestamp_rows": 0, "duplicate_timestamps": 0, "nonzero_seconds": 0}`

## 4. Gaps (hypothesis categories; none verified as market closures)

| hypothesis_category | gaps | missing_bars |
|---|---|---|
| possible_holiday | 1 | 2157 |
| short_gap_unexplained | 21 | 30 |

Gaps longer than the short-gap threshold:

| last_bar_before | first_bar_after | duration | missing_bars | category | hypothesis_category | hypothesis_basis |
|---|---|---|---|---|---|---|
| 2019-12-31 19:01:00 | 2020-01-02 06:59:00 | 1 days 11:58:00 | 2157 | intraweek_long | possible_holiday | New Year's Eve, New Year's Day |

## 5. OHLC validity

Violations (bid and ask checked separately): 0.

## 6. Bid/ask and spreads

| field | ask_below_bid | ask_equals_bid | spread_min_pips | spread_median_pips | spread_p99_pips | spread_max_pips |
|---|---|---|---|---|---|---|
| open | 196 | 1192 | -0.3 | 0.1 | 3.29 | 5.8 |
| high | 248 | 1351 | -0.4 | 0.1 | 3.2 | 5.9 |
| low | 220 | 1315 | -0.7 | 0.1 | 3.1 | 5.4 |
| close | 196 | 1192 | -0.3 | 0.1 | 3.29 | 5.8 |

Bars with a negative spread or an open/close spread above 5.0 pips: 680 (spread_anomalies.csv).

| timestamp_text | line_number | spread_pips_open | spread_pips_high | spread_pips_low | spread_pips_close |
|---|---|---|---|---|---|
| 12/29/2019 22:03:00.000 | 2 | 5.8 | 5.8 | 4.7 | 4.7 |
| 12/29/2019 22:12:00.000 | 10 | 1.2 | 5.9 | 2.2 | 5.7 |
| 12/29/2019 22:16:00.000 | 11 | 5.7 | 5.8 | 5.4 | 5.4 |
| 12/29/2019 22:17:00.000 | 12 | 5.4 | 5.3 | 4.9 | 4.7 |
| 12/29/2019 22:29:00.000 | 19 | 3.3 | 5.6 | 3.5 | 5.8 |
| 12/29/2019 22:30:00.000 | 20 | 5.8 | 4.8 | 4.3 | 4.8 |
| 12/29/2019 22:35:00.000 | 25 | 2.5 | -0.2 | 3.0 | 4.0 |
| 12/30/2019 00:42:00.000 | 150 | 0.2 | 0.2 | -0.1 | 0.1 |
| 12/30/2019 00:47:00.000 | 155 | 0.1 | 0.1 | -0.1 | 0.1 |
| 12/30/2019 00:49:00.000 | 157 | 0.1 | 0.1 | -0.1 | 0.1 |
| 12/30/2019 01:31:00.000 | 199 | 0.1 | 0.0 | 0.1 | -0.1 |
| 12/30/2019 01:32:00.000 | 200 | -0.1 | 0.0 | 0.0 | 0.1 |
| 12/30/2019 01:58:00.000 | 226 | 0.0 | 0.0 | -0.1 | 0.0 |
| 12/30/2019 01:59:00.000 | 227 | 0.0 | 0.0 | 0.0 | -0.1 |
| 12/30/2019 02:00:00.000 | 228 | -0.1 | -0.1 | 0.1 | 0.1 |
| 12/30/2019 02:03:00.000 | 231 | 0.0 | -0.1 | 0.1 | 0.1 |
| 12/30/2019 02:07:00.000 | 235 | 0.0 | 0.0 | -0.1 | 0.0 |
| 12/30/2019 02:14:00.000 | 242 | 0.1 | 0.0 | 0.0 | -0.1 |
| 12/30/2019 02:15:00.000 | 243 | -0.1 | 0.1 | 0.0 | 0.0 |
| 12/30/2019 02:17:00.000 | 245 | 0.1 | 0.0 | -0.1 | 0.0 |

Median close spread by label hour:

| label_hour | count | median | max |
|---|---|---|---|
| 0 | 178 | 0.1 | 0.3 |
| 1 | 180 | 0.1 | 0.3 |
| 2 | 180 | 0.1 | 0.2 |
| 3 | 180 | 0.1 | 0.3 |
| 4 | 179 | 0.1 | 0.3 |
| 5 | 179 | 0.1 | 0.3 |
| 6 | 181 | 0.1 | 0.2 |
| 7 | 240 | 0.1 | 0.3 |
| 8 | 240 | 0.1 | 0.2 |
| 9 | 240 | 0.1 | 0.2 |
| 10 | 240 | 0.1 | 0.3 |
| 11 | 240 | 0.1 | 0.2 |
| 12 | 240 | 0.1 | 0.2 |
| 13 | 240 | 0.1 | 0.3 |
| 14 | 240 | 0.1 | 0.2 |
| 15 | 240 | 0.1 | 0.3 |
| 16 | 240 | 0.1 | 0.2 |
| 17 | 240 | 0.1 | 0.3 |
| 18 | 240 | 0.1 | 0.5 |
| 19 | 182 | 0.1 | 0.6 |
| 20 | 180 | 0.1 | 0.3 |
| 21 | 177 | 0.2 | 5.0 |
| 22 | 157 | 2.5 | 5.8 |
| 23 | 177 | 0.2 | 1.1 |

Bid jumps above 20.0 pips between consecutive bars: 0.

## 7. Event check on FXCM labels (independent of HistData)

| event | utc | basis | day_median_abs_return_bp | max_bp_at_-60min | ratio_to_median_at_-60min | max_bp_at_+0min | ratio_to_median_at_+0min | max_bp_at_+60min | ratio_to_median_at_+60min | strongest_shift_min |
|---|---|---|---|---|---|---|---|---|---|---|
| FOMC minutes (Dec 10-11 meeting) | 2020-01-03 19:00 | Federal Reserve press release: 2:00 p.m. EST | 0.448 | 0.9 | 2.0 | 1.97 | 4.4 | 1.79 | 4.0 | 0 |
| ISM manufacturing (Dec) | 2020-01-03 15:00 | 10:00 a.m. ET per a market preview (secondary source) | 0.448 | 1.8 | 4.0 | 6.54 | 14.6 | 1.52 | 3.4 | 0 |

## 8. Dukascopy

Files: ['EUR-USD_1Minute_BID_2025-03-19_00_00-23_59_Etc_UTC.csv']. Overlapping FXCM dates: none; no comparison possible.

## 9. HistData overlap comparison (no timestamps shifted)

HistData files: `data/HISTDATA_COM_ASCII_EURUSD_M12019/DAT_ASCII_EURUSD_M1_2019.csv`, `data/HISTDATA_COM_ASCII_EURUSD_M12020/DAT_ASCII_EURUSD_M1_2020.csv`

Exact labels (offset 0): presence {'both': 4582, 'reference_only': 428, 'histdata_only': 0}.

| field | pairs | mean_diff_pips | median_diff_pips | median_abs_diff_pips | p95_abs_diff_pips | max_abs_diff_pips | share_exact | share_within_0_5_pip |
|---|---|---|---|---|---|---|---|---|
| open | 4582 | -0.432 | -0.4 | 10.4 | 32.3 | 52.7 | 0.0033 | 0.041 |
| high | 4582 | -0.474 | -0.5 | 10.7 | 32.2 | 51.6 | 0.0037 | 0.0384 |
| low | 4582 | -0.41 | -0.4 | 10.4 | 32.6 | 52.8 | 0.0046 | 0.0402 |
| close | 4582 | -0.445 | -0.5 | 10.4 | 32.295 | 52.7 | 0.0035 | 0.0415 |

Offset scan on bid 1-minute log returns (FXCM label = HistData label + k):

| measure | best_offset_minutes | best_offset_hours | best_correlation | best_shared_minutes | runner_up_offset_minutes | runner_up_correlation | peak_ratio | correlation_ge_min | peak_ratio_ge_min | shared_minutes_ge_min | decisive_day | variant |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pearson | 300 | 5.0 | 0.9864 | 4977 | -692 | 0.054 | 18.26 | True | True | True | True | pearson |
| spearman | 300 | 5.0 | 0.9738 | 4977 | -708 | 0.055 | 17.7 | True | True | True | True | spearman |

Null check: `{"far_offsets": 1382, "far_abs_corr_median": 0.01, "far_abs_corr_p99": 0.0402}`

| hypothesis | regime | predicted_offset_minutes | matches_best_offset |
|---|---|---|---|
| H1_fixed_utc-5 | both_standard | 300 | True |
| H2_america_new_york | both_standard | 300 | True |
| H3_ny_offset_eu_dates | both_standard | 300 | True |

Price levels at the best offset (bid vs bid; supporting evidence only): presence {'both': 5004, 'histdata_only': 747, 'reference_only': 6}.

| field | pairs | mean_diff_pips | median_diff_pips | median_abs_diff_pips | p95_abs_diff_pips | max_abs_diff_pips | share_exact | share_within_0_5_pip |
|---|---|---|---|---|---|---|---|---|
| open | 5004 | -0.058 | -0.1 | 0.1 | 0.3 | 15.1 | 0.2658 | 0.986 |
| high | 5004 | -0.08 | -0.1 | 0.1 | 0.3 | 14.6 | 0.2564 | 0.9854 |
| low | 5004 | -0.046 | -0.1 | 0.1 | 0.2 | 3.1 | 0.3347 | 0.987 |
| close | 5004 | -0.063 | -0.1 | 0.1 | 0.2 | 2.4 | 0.2918 | 0.9866 |

Presence by day (FXCM day after applying the best offset to HistData labels, for pairing only):

| day | reference_only | histdata_only | both |
|---|---|---|---|
| 2019-12-29 | 0 | 11 | 106 |
| 2019-12-30 | 1 | 5 | 1434 |
| 2019-12-31 | 0 | 180 | 1140 |
| 2020-01-01 | 0 | 120 | 0 |
| 2020-01-02 | 4 | 430 | 1006 |
| 2020-01-03 | 1 | 1 | 1318 |

Largest bid differences at the best offset:

| fxcm_timestamp_text | histdata_label | fxcm_line_number | histdata_line_number | open_diff_pips | high_diff_pips | low_diff_pips | close_diff_pips | max_abs_diff_pips |
|---|---|---|---|---|---|---|---|---|
| 01/02/2020 06:59:00.000 | 2020-01-02 01:59:00 | 2683.0 | 540.0 | -15.1 | -14.6 | 0.1 | -0.1 | 15.1 |
| 12/30/2019 23:00:00.000 | 2019-12-30 18:00:00 | 1483.0 | 371151.0 | 4.0 | -1.0 | 2.7 | -0.1 | 4.0 |
| 12/29/2019 22:36:00.000 | 2019-12-29 17:36:00 | 26.0 | 369688.0 | 3.8 | 0.3 | 0.4 | 1.2 | 3.8 |
| 12/29/2019 22:59:00.000 | 2019-12-29 17:59:00 | 47.0 | 369711.0 | 3.2 | 1.1 | 2.0 | 1.6 | 3.2 |
| 01/03/2020 21:59:00.000 | 2020-01-03 16:59:00 | 5011.0 | 2875.0 | -1.4 | -1.4 | -3.1 | -1.2 | 3.1 |
| 12/29/2019 22:28:00.000 | 2019-12-29 17:28:00 | 18.0 | 369680.0 | 1.3 | 2.8 | -0.2 | 0.7 | 2.8 |
| 12/29/2019 22:37:00.000 | 2019-12-29 17:37:00 | 27.0 | 369689.0 | 2.7 | 0.1 | 0.5 | -0.7 | 2.7 |
| 01/02/2020 22:05:00.000 | 2020-01-02 17:05:00 | 3588.0 | 1446.0 | 0.2 | -0.1 | 2.5 | 2.3 | 2.5 |
| 12/30/2019 22:41:00.000 | 2019-12-30 17:41:00 | 1464.0 | 371132.0 | 1.8 | 1.8 | 2.4 | 2.4 | 2.4 |
| 12/30/2019 22:42:00.000 | 2019-12-30 17:42:00 | 1465.0 | 371133.0 | 2.4 | 2.4 | 0.6 | 2.4 | 2.4 |
| 12/30/2019 22:43:00.000 | 2019-12-30 17:43:00 | 1466.0 | 371134.0 | 0.7 | 2.4 | 0.8 | 0.4 | 2.4 |
| 12/29/2019 22:12:00.000 | 2019-12-29 17:12:00 | 10.0 | 369664.0 | 0.7 | 2.3 | 1.1 | 1.6 | 2.3 |
| 12/29/2019 22:22:00.000 | 2019-12-29 17:22:00 | 14.0 | 369674.0 | -0.1 | 2.3 | -0.2 | 0.3 | 2.3 |
| 01/02/2020 22:06:00.000 | 2020-01-02 17:06:00 | 3589.0 | 1447.0 | 2.3 | 1.7 | 2.3 | 2.0 | 2.3 |
| 01/02/2020 22:07:00.000 | 2020-01-02 17:07:00 | 3590.0 | 1448.0 | 2.0 | 1.8 | 2.1 | 2.2 | 2.2 |
