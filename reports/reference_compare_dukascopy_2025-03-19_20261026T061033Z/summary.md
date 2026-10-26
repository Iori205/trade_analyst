# HistData vs Dukascopy: read-only alignment check for 2025-03-19 (UTC)

Generated (UTC): 2026-10-26 06:10:33. No file was modified, shifted, deduplicated or converted. Source files unchanged during run: **YES** (43 files hashed).

- Reference: `data/dukascopy/EUR-USD_1Minute_BID_2025-03-19_00_00-23_59_Etc_UTC.csv`
- HistData: `data/HISTDATA_COM_ASCII_EURUSD_M12025/DAT_ASCII_EURUSD_M1_2025.csv`

## 1. Formats

| | Dukascopy | HistData |
|---|---|---|
| Delimiter / header | `,` with header `Etc/UTC,Open,High,Low,Close,Volume` | `;`, no header |
| Timestamp | `YYYY-MM-DDTHH:MM:SS+00:00` (explicit UTC offset) | `YYYYMMDD HHMMSS`, no zone (unverified source clock) |
| Columns | Etc/UTC, Open, High, Low, Close, Volume | timestamp, open, high, low, close, volume |
| Price type | BID (file name) | bid (HistData FAQ) |
| Volume | non-zero, vendor units | always 0 |

## 2. Profiles

| dataset | rows | first | last | expected_minutes_in_window | distinct_minutes | duplicate_timestamp_rows | monotonic_increasing | non_zero_seconds | ohlc_violations | zero_volume_rows |
|---|---|---|---|---|---|---|---|---|---|---|
| dukascopy (UTC) | 1439 | 2025-03-19 00:00:00+00:00 | 2025-03-19 23:59:00+00:00 | 1440 | 1439 | 0 | True | 0 | 0 | 0 |
| histdata, same calendar label | 1439 | 2025-03-19 00:00:00 | 2025-03-19 23:59:00 | 1440 | 1439 | 0 | True | 0 | 0 | 1439 |

Missing minutes: Dukascopy 1 (2025-03-19 21:21:00); HistData same label day 1 (2025-03-19 16:21:00).

## 3. Exact timestamp alignment (offset 0, labels taken at face value)

Pairing: {'both': 1438, 'reference_only': 1, 'histdata_only': 1}.

| field | pairs | mean_diff_pips | median_diff_pips | median_abs_diff_pips | p95_abs_diff_pips | max_abs_diff_pips | share_exact | share_within_0_5_pip |
|---|---|---|---|---|---|---|---|---|
| open | 1438 | -5.616 | -3.35 | 14.2 | 43.4 | 63.1 | 0.0028 | 0.0382 |
| high | 1438 | -5.582 | -3.2 | 14.1 | 42.7 | 61.6 | 0.0028 | 0.0327 |
| low | 1438 | -5.647 | -3.4 | 14.35 | 43.9 | 68.4 | 0.0076 | 0.0376 |
| close | 1438 | -5.615 | -3.3 | 14.2 | 43.315 | 63.0 | 0.0056 | 0.0382 |

## 4. Offset scan (reference minute = HistData label + k)

Scanned k = -720 to 720 minutes on 1-minute log returns (consecutive minutes only, duplicated labels excluded).

| offset_minutes | shared_minutes | pearson | spearman | shared_minutes_ex_rollover | pearson_ex_rollover | spearman_ex_rollover |
|---|---|---|---|---|---|---|
| -300 | 1435 | 0.040981113439144436 | -0.0060670698414891444 | 1414 | 0.041861832392076664 | -0.004937556699315978 |
| -240 | 1435 | -0.010243846444764077 | -0.0005996460964100232 | 1414 | -0.009349485118797603 | 0.0023491558500929343 |
| 0 | 1435 | 0.011899347774047922 | 0.00843490894018646 | 1414 | 0.012916704842185283 | 0.012643070318144605 |
| 240 | 1435 | 0.011918900682958568 | 0.028845271279849063 | 1414 | 0.009161250800084599 | 0.02617480934299114 |
| 299 | 1436 | 0.03843545897437877 | 0.013831584724566064 | 1415 | 0.03876357995442368 | 0.013756316414378933 |
| 300 | 1437 | 1.0 | 1.0 | 1416 | 1.0 | 0.9999999999999999 |
| 301 | 1436 | 0.038533356203835675 | 0.014164182637770823 | 1415 | 0.03795901885543926 | 0.012157437321291877 |

Day-level criteria (pre-registered): best correlation >= 0.3, >= 3.0x the best correlation outside best +/- 1 min, >= 300 shared minutes.

| measure | best_offset_minutes | best_offset_hours | best_correlation | best_shared_minutes | runner_up_offset_minutes | runner_up_correlation | peak_ratio | correlation_ge_min | peak_ratio_ge_min | shared_minutes_ge_min | decisive_day | variant |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pearson | 300 | 5.0 | 1.0 | 1437 | 331 | 0.0898 | 11.13 | True | True | True | True | pearson |
| spearman | 300 | 5.0 | 1.0 | 1437 | 476 | 0.0924 | 10.82 | True | True | True | True | spearman |
| pearson | 300 | 5.0 | 1.0 | 1416 | 269 | 0.0897 | 11.15 | True | True | True | True | pearson, rollover excluded |

Null check (|offset - best| >= 30 min): {"far_offsets": 1382, "far_abs_corr_median": 0.0175, "far_abs_corr_p99": 0.0611}

## 5. Hypothesis predictions for this day

| hypothesis | regime | predicted_offset_minutes | matches_best_offset |
|---|---|---|---|
| H1_fixed_utc-5 | us_summer_eu_standard | 300 | True |
| H2_america_new_york | us_summer_eu_standard | 240 | False |
| H3_ny_offset_eu_dates | us_summer_eu_standard | 300 | True |

## 6. Price levels at the best offset (supporting evidence only)

Pairing: {'both': 1439, 'reference_only': 0, 'histdata_only': 0}. HistData rows mapped into the UTC day: 1439.

| field | pairs | mean_diff_pips | median_diff_pips | median_abs_diff_pips | p95_abs_diff_pips | max_abs_diff_pips | share_exact | share_within_0_5_pip |
|---|---|---|---|---|---|---|---|---|
| open | 1439 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 1.0 |
| high | 1439 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 1.0 |
| low | 1439 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 1.0 |
| close | 1439 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 1.0 |

## 7. Event check (largest 1-minute moves, each on its own clock)

FOMC statement released 14:00 EDT = 18:00 UTC on 2025-03-19 (Federal Reserve press release).

Dukascopy:

| minute_label | abs_log_return_bp |
|---|---|
| 2025-03-19 18:00:00 | 13.88 |
| 2025-03-19 07:36:00 | 10.1 |
| 2025-03-19 18:41:00 | 7.43 |
| 2025-03-19 08:00:00 | 7.34 |
| 2025-03-19 14:52:00 | 6.8 |

HistData (same calendar label day):

| minute_label | abs_log_return_bp |
|---|---|
| 2025-03-19 13:00:00 | 13.88 |
| 2025-03-19 02:36:00 | 10.1 |
| 2025-03-19 13:41:00 | 7.43 |
| 2025-03-19 03:00:00 | 7.34 |
| 2025-03-19 09:52:00 | 6.8 |

## 8. Limitations

- One day only. The pre-registered acceptance rule needs >= 5 decisive days per DST regime, so this result cannot accept or reject a timezone candidate on its own.
- The reference's UTC claim is checked here only by the FOMC event; Dukascopy export settings were not seen.
- Both files are bid-based; residual level differences reflect vendor liquidity and bar construction.
