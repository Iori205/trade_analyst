# Timestamp, duplicate and gap investigation (read-only)

Generated (UTC): 2026-10-22 10:44:59. All times are naive source-clock values. No data was modified, sorted, deduplicated or converted on disk. Source files unchanged during run: **YES** (42 files).

## 1. Documented facts

- HistData FAQ (histdata.com/f-a-q): *"The timezone of all data is: Eastern Standard Time (EST) time-zone WITHOUT Day Light Savings adjustments."* Bars are built from the tick **bid** price.
- The local TXT status reports contain no timezone statement.
- 17:00 New York as the FX week/day boundary is a broker/industry convention (e.g. FXCM rollover help), with broker-to-broker variation. It is not an exchange rule.
- Anchor events with documented clock times: US releases at 08:30 New York; WM/Reuters fix at 16:00 London.

## 2. Hypotheses and their predictions (source clock)

- **H1_fixed_utc-5**: Fixed UTC-5 all year (HistData FAQ: EST without DST)
- **H2_america_new_york**: New York local time: UTC-5, UTC-4 during US DST
- **H3_ny_offset_eu_dates**: UTC-5, UTC-4 during EU summer time (New York offsets, EU switch dates)

| anchor | regime | H1_fixed_utc-5 | H2_america_new_york | H3_ny_offset_eu_dates |
|---|---|---|---|---|
| us_0830_release | both_standard | 08:30 | 08:30 | 08:30 |
| us_0830_release | both_summer | 07:30 | 08:30 | 08:30 |
| us_0830_release | us_summer_eu_standard | 07:30 | 08:30 | 07:30 |
| london_1600_fix | both_standard | 11:00 | 11:00 | 11:00 |
| london_1600_fix | both_summer | 10:00 | 11:00 | 11:00 |
| london_1600_fix | us_summer_eu_standard | 11:00 | 12:00 | 11:00 |
| weekly_open_1700_ny | both_standard | 17:00 | 17:00 | 17:00 |
| weekly_open_1700_ny | both_summer | 16:00 | 17:00 | 17:00 |
| weekly_open_1700_ny | us_summer_eu_standard | 16:00 | 17:00 | 16:00 |

## 3. Observed evidence: intraday anchors by era

Observed time = the candidate minute with the strongest activity (see CSV for strength ratios). Weekdays only; duplicated timestamps excluded.

| era | regime | anchor | weekdays | observed_time | H1_fixed_utc-5_predicts | H2_america_new_york_predicts | H3_ny_offset_eu_dates_predicts |
|---|---|---|---|---|---|---|---|
| 2015-2018 | both_standard | us_0830_release | 361 | 08:30 | 08:30 | 08:30 | 08:30 |
| 2015-2018 | both_standard | london_1600_fix | 361 | 11:00 | 11:00 | 11:00 | 11:00 |
| 2015-2018 | both_summer | us_0830_release | 615 | 08:30 | 07:30 | 08:30 | 08:30 |
| 2015-2018 | both_summer | london_1600_fix | 615 | 11:00 | 10:00 | 11:00 | 11:00 |
| 2015-2018 | us_summer_eu_standard | us_0830_release | 65 | 08:30 | 07:30 | 08:30 | 07:30 |
| 2015-2018 | us_summer_eu_standard | london_1600_fix | 65 | 12:00 | 11:00 | 12:00 | 11:00 |
| 2019-2026 | both_standard | us_0830_release | 683 | 08:30 | 08:30 | 08:30 | 08:30 |
| 2019-2026 | both_standard | london_1600_fix | 683 | 11:00 | 11:00 | 11:00 | 11:00 |
| 2019-2026 | both_summer | us_0830_release | 1175 | 08:30 | 07:30 | 08:30 | 08:30 |
| 2019-2026 | both_summer | london_1600_fix | 1175 | 11:00 | 10:00 | 11:00 | 11:00 |
| 2019-2026 | us_summer_eu_standard | us_0830_release | 140 | 07:30 | 07:30 | 08:30 | 07:30 |
| 2019-2026 | us_summer_eu_standard | london_1600_fix | 140 | 11:00 | 11:00 | 12:00 | 11:00 |

## 4. Observed evidence: US-summer/EU-standard windows by year

These windows are the only periods where H2 and H3 disagree; they are short (about 15 spring and 5 autumn weekdays per year), so individual years are noisier.

| year | part | anchor | weekdays | observed_time | strength_ratio_top_vs_second |
|---|---|---|---|---|---|
| 2015 | window_autumn | us_0830_release | 5 | 08:30 | 4.2 |
| 2015 | window_autumn | london_1600_fix | 5 | 12:00 | 1.59 |
| 2015 | window_spring | us_0830_release | 15 | 08:30 | 3.63 |
| 2015 | window_spring | london_1600_fix | 15 | 12:00 | 1.14 |
| 2016 | window_autumn | us_0830_release | 5 | 08:30 | 2.94 |
| 2016 | window_autumn | london_1600_fix | 5 | 12:00 | 1.39 |
| 2016 | window_spring | us_0830_release | 10 | 08:30 | 3.9 |
| 2016 | window_spring | london_1600_fix | 10 | 12:00 | 1.51 |
| 2017 | window_autumn | us_0830_release | 5 | 08:30 | 3.57 |
| 2017 | window_autumn | london_1600_fix | 5 | 12:00 | 1.11 |
| 2017 | window_spring | us_0830_release | 10 | 08:30 | 1.04 |
| 2017 | window_spring | london_1600_fix | 10 | 12:00 | 1.33 |
| 2018 | window_autumn | us_0830_release | 5 | 08:30 | 2.72 |
| 2018 | window_autumn | london_1600_fix | 5 | 12:00 | 1.28 |
| 2018 | window_spring | us_0830_release | 10 | 08:30 | 2.58 |
| 2018 | window_spring | london_1600_fix | 10 | 12:00 | 1.43 |
| 2019 | window_autumn | us_0830_release | 5 | 07:30 | 2.27 |
| 2019 | window_autumn | london_1600_fix | 5 | 11:00 | 1.21 |
| 2019 | window_spring | us_0830_release | 15 | 07:30 | 2.25 |
| 2019 | window_spring | london_1600_fix | 15 | 11:00 | 1.44 |
| 2020 | window_autumn | us_0830_release | 5 | 09:30 | 1.02 |
| 2020 | window_autumn | london_1600_fix | 5 | 11:00 | 1.14 |
| 2020 | window_spring | us_0830_release | 15 | 08:30 | 1.09 |
| 2020 | window_spring | london_1600_fix | 15 | 11:00 | 1.64 |
| 2021 | window_autumn | us_0830_release | 5 | 07:30 | 2.58 |
| 2021 | window_autumn | london_1600_fix | 5 | 11:00 | 1.11 |
| 2021 | window_spring | us_0830_release | 10 | 07:30 | 1.35 |
| 2021 | window_spring | london_1600_fix | 10 | 11:00 | 1.75 |
| 2022 | window_autumn | us_0830_release | 5 | 07:30 | 4.9 |
| 2022 | window_autumn | london_1600_fix | 5 | 10:00 | 1.37 |
| 2022 | window_spring | us_0830_release | 10 | 07:30 | 1.02 |
| 2022 | window_spring | london_1600_fix | 10 | 11:00 | 1.38 |
| 2023 | window_autumn | us_0830_release | 5 | 07:30 | 4.39 |
| 2023 | window_autumn | london_1600_fix | 5 | 10:00 | 1.02 |
| 2023 | window_spring | us_0830_release | 10 | 07:30 | 2.45 |
| 2023 | window_spring | london_1600_fix | 10 | 11:00 | 1.69 |
| 2024 | window_autumn | us_0830_release | 5 | 07:30 | 6.56 |
| 2024 | window_autumn | london_1600_fix | 5 | 10:00 | 1.35 |
| 2024 | window_spring | us_0830_release | 15 | 07:30 | 3.05 |
| 2024 | window_spring | london_1600_fix | 15 | 11:00 | 1.61 |
| 2025 | window_autumn | us_0830_release | 5 | 08:30 | 1.28 |
| 2025 | window_autumn | london_1600_fix | 5 | 10:00 | 1.2 |
| 2025 | window_spring | us_0830_release | 15 | 07:30 | 1.88 |
| 2025 | window_spring | london_1600_fix | 15 | 11:00 | 1.08 |
| 2026 | window_spring | us_0830_release | 15 | 07:30 | 1.14 |
| 2026 | window_spring | london_1600_fix | 15 | 11:00 | 1.19 |

## 5. Weekly opens by year and regime

| year | part | weeks | open_hours_seen | H1_fixed_utc-5_consistent_weeks | H2_america_new_york_consistent_weeks | H3_ny_offset_eu_dates_consistent_weeks |
|---|---|---|---|---|---|---|
| 2015 | both_standard | 17 | 17:00x17 | 17 | 17 | 17 |
| 2015 | both_summer | 30 | 17:00x30 | 0 | 30 | 30 |
| 2015 | window_autumn | 1 | 17:00x1 | 0 | 1 | 0 |
| 2015 | window_spring | 3 | 17:00x3 | 0 | 3 | 0 |
| 2016 | both_standard | 17 | 17:00x17 | 17 | 17 | 17 |
| 2016 | both_summer | 31 | 17:00x31 | 0 | 31 | 31 |
| 2016 | window_autumn | 1 | 17:00x1 | 0 | 1 | 0 |
| 2016 | window_spring | 2 | 17:00x2 | 0 | 2 | 0 |
| 2017 | both_standard | 16 | 17:00x16 | 16 | 16 | 16 |
| 2017 | both_summer | 31 | 17:00x31 | 0 | 31 | 31 |
| 2017 | window_autumn | 1 | 17:00x1 | 0 | 1 | 0 |
| 2017 | window_spring | 2 | 17:00x2 | 0 | 2 | 0 |
| 2018 | both_standard | 18 | 17:00x18 | 18 | 18 | 18 |
| 2018 | both_summer | 31 | 17:00x31 | 0 | 31 | 31 |
| 2018 | window_autumn | 1 | 17:00x1 | 0 | 1 | 0 |
| 2018 | window_spring | 2 | 17:00x2 | 0 | 2 | 0 |
| 2019 | both_standard | 18 | 17:00x18 | 18 | 18 | 18 |
| 2019 | both_summer | 30 | 17:00x29,23:00x1 | 0 | 29 | 29 |
| 2019 | window_autumn | 1 | 16:00x1 | 1 | 0 | 1 |
| 2019 | window_spring | 3 | 16:00x3 | 3 | 0 | 3 |
| 2020 | both_standard | 17 | 17:00x17 | 17 | 17 | 17 |
| 2020 | both_summer | 30 | 17:00x30 | 0 | 30 | 30 |
| 2020 | window_autumn | 1 | 16:00x1 | 1 | 0 | 1 |
| 2020 | window_spring | 3 | 16:00x3 | 3 | 0 | 3 |
| 2021 | both_standard | 17 | 17:00x17 | 17 | 17 | 17 |
| 2021 | both_summer | 31 | 17:00x31 | 0 | 31 | 31 |
| 2021 | window_autumn | 1 | 16:00x1 | 1 | 0 | 1 |
| 2021 | window_spring | 2 | 16:00x2 | 2 | 0 | 2 |
| 2022 | both_standard | 18 | 17:00x18 | 18 | 18 | 18 |
| 2022 | both_summer | 31 | 17:00x31 | 0 | 31 | 31 |
| 2022 | window_autumn | 1 | 16:00x1 | 1 | 0 | 1 |
| 2022 | window_spring | 2 | 16:00x2 | 2 | 0 | 2 |
| 2023 | both_standard | 18 | 17:00x16,18:00x2 | 16 | 16 | 16 |
| 2023 | both_summer | 30 | 17:00x21,18:00x8,19:00x1 | 0 | 21 | 21 |
| 2023 | window_autumn | 1 | 16:00x1 | 1 | 0 | 1 |
| 2023 | window_spring | 2 | 16:00x1,17:00x1 | 1 | 1 | 1 |
| 2024 | both_standard | 18 | 17:00x18 | 18 | 18 | 18 |
| 2024 | both_summer | 30 | 17:00x30 | 0 | 30 | 30 |
| 2024 | window_autumn | 1 | 17:00x1 | 0 | 1 | 0 |
| 2024 | window_spring | 3 | 16:00x3 | 3 | 0 | 3 |
| 2025 | both_standard | 18 | 17:00x18 | 18 | 18 | 18 |
| 2025 | both_summer | 30 | 17:00x30 | 0 | 30 | 30 |
| 2025 | window_autumn | 1 | 16:00x1 | 1 | 0 | 1 |
| 2025 | window_spring | 3 | 16:00x3 | 3 | 0 | 3 |
| 2026 | both_standard | 9 | 17:00x9 | 9 | 9 | 9 |
| 2026 | both_summer | 23 | 17:00x23 | 0 | 23 | 23 |
| 2026 | window_spring | 3 | 16:00x3 | 3 | 0 | 3 |

## 6. DST switch Sundays

| year | event | date | week_open | rows_17_to_22 | distinct_minutes_17_to_22 | duplicated_rows_on_day | long_gaps_on_day | txt_tick_gaps_ge_30min |
|---|---|---|---|---|---|---|---|---|
| 2015 | us_start | 2015-03-08 | 2015-03-08 17:00:00 | 300 | 300 | 0 |  |  |
| 2015 | eu_start | 2015-03-29 | 2015-03-29 17:00:00 | 292 | 292 | 0 |  |  |
| 2015 | eu_end | 2015-10-25 | 2015-10-25 17:00:00 | 300 | 300 | 0 |  |  |
| 2015 | us_end | 2015-11-01 | 2015-11-01 17:00:00 | 300 | 300 | 0 |  |  |
| 2016 | us_start | 2016-03-13 | 2016-03-13 17:00:00 | 286 | 286 | 0 |  |  |
| 2016 | eu_start | 2016-03-27 | 2016-03-27 17:00:00 | 290 | 290 | 0 |  |  |
| 2016 | eu_end | 2016-10-30 | 2016-10-30 17:00:00 | 298 | 298 | 0 |  |  |
| 2016 | us_end | 2016-11-06 | 2016-11-06 17:00:00 | 300 | 300 | 0 |  |  |
| 2017 | us_start | 2017-03-12 | 2017-03-12 17:00:00 | 294 | 294 | 0 |  |  |
| 2017 | eu_start | 2017-03-26 | 2017-03-26 17:00:00 | 299 | 299 | 0 |  |  |
| 2017 | eu_end | 2017-10-29 | 2017-10-29 17:00:00 | 292 | 292 | 0 |  |  |
| 2017 | us_end | 2017-11-05 | 2017-11-05 17:00:00 | 299 | 299 | 0 |  |  |
| 2018 | us_start | 2018-03-11 | 2018-03-11 17:00:00 | 290 | 290 | 0 |  |  |
| 2018 | eu_start | 2018-03-25 | 2018-03-25 17:00:00 | 292 | 292 | 0 |  |  |
| 2018 | eu_end | 2018-10-28 | 2018-10-28 17:00:00 | 296 | 296 | 0 |  |  |
| 2018 | us_end | 2018-11-04 | 2018-11-04 17:00:00 | 296 | 296 | 0 |  |  |
| 2019 | us_start | 2019-03-10 | 2019-03-10 16:00:00 | 300 | 300 | 0 |  |  |
| 2019 | eu_start | 2019-03-31 | 2019-03-31 17:00:00 | 239 | 239 | 0 | 18:59->20:00 (60 bars) | 18:59:56 3597s |
| 2019 | eu_end | 2019-10-27 | 2019-10-27 16:00:00 | 360 | 300 | 120 |  |  |
| 2019 | us_end | 2019-11-03 | 2019-11-03 17:00:00 | 299 | 299 | 0 |  |  |
| 2020 | us_start | 2020-03-08 | 2020-03-08 16:00:00 | 300 | 300 | 0 |  |  |
| 2020 | eu_start | 2020-03-29 | 2020-03-29 17:01:00 | 234 | 234 | 0 | 18:59->20:00 (60 bars) | 18:59:58 3595s |
| 2020 | eu_end | 2020-10-25 | 2020-10-25 16:00:00 | 360 | 300 | 120 |  |  |
| 2020 | us_end | 2020-11-01 | 2020-11-01 17:00:00 | 297 | 297 | 0 |  |  |
| 2021 | us_start | 2021-03-14 | 2021-03-14 16:00:00 | 299 | 299 | 0 |  |  |
| 2021 | eu_start | 2021-03-28 | 2021-03-28 17:00:00 | 225 | 225 | 0 | 18:59->20:00 (60 bars) | 18:59:58 3595s |
| 2021 | eu_end | 2021-10-31 | 2021-10-31 16:00:00 | 358 | 298 | 120 |  |  |
| 2021 | us_end | 2021-11-07 | 2021-11-07 17:00:00 | 295 | 295 | 0 |  |  |
| 2022 | us_start | 2022-03-13 | 2022-03-13 16:00:00 | 300 | 300 | 0 |  |  |
| 2022 | eu_start | 2022-03-27 | 2022-03-27 17:00:00 | 235 | 235 | 0 | 18:59->20:00 (60 bars) | 18:59:58 3596s |
| 2022 | eu_end | 2022-10-30 | 2022-10-30 16:00:00 | 360 | 300 | 120 |  |  |
| 2022 | us_end | 2022-11-06 | 2022-11-06 17:00:00 | 300 | 300 | 0 |  |  |
| 2023 | us_start | 2023-03-12 | 2023-03-12 16:00:00 | 180 | 180 | 0 | 16:59->19:00 (120 bars) | 16:59:37 7216s |
| 2023 | eu_start | 2023-03-26 | 2023-03-26 17:00:00 | 226 | 226 | 0 | 18:59->20:00 (60 bars) | 18:59:56 3597s |
| 2023 | eu_end | 2023-10-29 | 2023-10-29 16:04:00 | 357 | 297 | 120 |  |  |
| 2023 | us_end | 2023-11-05 | 2023-11-05 17:00:00 | 298 | 298 | 0 |  |  |
| 2024 | us_start | 2024-03-10 | 2024-03-10 16:00:00 | 300 | 300 | 0 |  |  |
| 2024 | eu_start | 2024-03-31 | 2024-03-31 17:00:00 | 239 | 239 | 0 | 18:59->20:00 (60 bars) | 18:59:57 3596s |
| 2024 | eu_end | 2024-10-27 | 2024-10-27 17:00:00 | 300 | 300 | 0 |  |  |
| 2024 | us_end | 2024-11-03 | 2024-11-03 17:00:00 | 299 | 299 | 0 |  |  |
| 2025 | us_start | 2025-03-09 | 2025-03-09 16:00:00 | 300 | 300 | 0 |  |  |
| 2025 | eu_start | 2025-03-30 | 2025-03-30 17:00:00 | 240 | 240 | 0 | 18:59->20:00 (60 bars) | 18:59:59 3594s |
| 2025 | eu_end | 2025-10-26 | 2025-10-26 16:00:00 | 359 | 299 | 120 |  |  |
| 2025 | us_end | 2025-11-02 | 2025-11-02 17:00:00 | 300 | 300 | 0 |  |  |
| 2026 | us_start | 2026-03-08 | 2026-03-08 16:00:00 | 300 | 300 | 0 |  |  |
| 2026 | eu_start | 2026-03-29 | 2026-03-29 17:00:00 | 226 | 226 | 0 | 18:59->20:00 (60 bars) | 18:59:57 3597s |

## 7. Duplicates

- Identical duplicate groups: 6 (720 rows), of which on a DST switch date: 6.

| source_file | date | weekday | timestamps | rows | first_timestamp | last_timestamp | block_line_ranges | all_values_identical | dst_switch_date |
|---|---|---|---|---|---|---|---|---|---|
| DAT_ASCII_EURUSD_M1_2019.csv | 2019-10-27 | Sunday | 60 | 120 | 2019-10-27 19:00:00 | 2019-10-27 19:59:00 | occurrence 1: lines 305959-306018; occurrence 2: lines 306019-306078 | True | eu_end |
| DAT_ASCII_EURUSD_M1_2020.csv | 2020-10-25 | Sunday | 60 | 120 | 2020-10-25 19:00:00 | 2020-10-25 19:59:00 | occurrence 1: lines 304281-304340; occurrence 2: lines 304341-304400 | True | eu_end |
| DAT_ASCII_EURUSD_M1_2021.csv | 2021-10-31 | Sunday | 60 | 120 | 2021-10-31 19:00:00 | 2021-10-31 19:59:00 | occurrence 1: lines 305232-305291; occurrence 2: lines 305292-305351 | True | eu_end |
| DAT_ASCII_EURUSD_M1_2022.csv | 2022-10-30 | Sunday | 60 | 120 | 2022-10-30 19:00:00 | 2022-10-30 19:59:00 | occurrence 1: lines 308463-308522; occurrence 2: lines 308523-308582 | True | eu_end |
| DAT_ASCII_EURUSD_M1_2023.csv | 2023-10-29 | Sunday | 60 | 120 | 2023-10-29 19:00:00 | 2023-10-29 19:59:00 | occurrence 1: lines 259274-259333; occurrence 2: lines 259334-259393 | True | eu_end |
| DAT_ASCII_EURUSD_M1_2025.csv | 2025-10-26 | Sunday | 60 | 120 | 2025-10-26 19:00:00 | 2025-10-26 19:59:00 | occurrence 1: lines 304585-304644; occurrence 2: lines 304645-304704 | True | eu_end |

- Conflicting duplicate rows: 8 (4 timestamps). No record is preferred.

| source_file | line_number | timestamp_string | occurrence | group_size | open | high | low | close | volume | dst_switch_date |
|---|---|---|---|---|---|---|---|---|---|---|
| DAT_ASCII_EURUSD_M1_202607.csv | 3906 | 20260705 173100 | 1 | 2 | [redacted] | [redacted] | [redacted] | [redacted] | 0 |  |
| DAT_ASCII_EURUSD_M1_202607.csv | 3908 | 20260705 173100 | 2 | 2 | [redacted] | [redacted] | [redacted] | [redacted] | 0 |  |
| DAT_ASCII_EURUSD_M1_202607.csv | 3907 | 20260705 173200 | 1 | 2 | [redacted] | [redacted] | [redacted] | [redacted] | 0 |  |
| DAT_ASCII_EURUSD_M1_202607.csv | 3909 | 20260705 173200 | 2 | 2 | [redacted] | [redacted] | [redacted] | [redacted] | 0 |  |
| DAT_ASCII_EURUSD_M1_202607.csv | 3911 | 20260705 173400 | 1 | 2 | [redacted] | [redacted] | [redacted] | [redacted] | 0 |  |
| DAT_ASCII_EURUSD_M1_202607.csv | 3913 | 20260705 173400 | 2 | 2 | [redacted] | [redacted] | [redacted] | [redacted] | 0 |  |
| DAT_ASCII_EURUSD_M1_202607.csv | 3912 | 20260705 173500 | 1 | 2 | [redacted] | [redacted] | [redacted] | [redacted] | 0 |  |
| DAT_ASCII_EURUSD_M1_202607.csv | 3914 | 20260705 173500 | 2 | 2 | [redacted] | [redacted] | [redacted] | [redacted] | 0 |  |

Context lines around the conflicting block (original order):

| source_file | line_number | raw_line | is_conflicting_duplicate |
|---|---|---|---|
| DAT_ASCII_EURUSD_M1_202607.csv | 3903 | 20260705 172500;[redacted];[redacted];[redacted];[redacted];0 | False |
| DAT_ASCII_EURUSD_M1_202607.csv | 3904 | 20260705 172600;[redacted];[redacted];[redacted];[redacted];0 | False |
| DAT_ASCII_EURUSD_M1_202607.csv | 3905 | 20260705 173000;[redacted];[redacted];[redacted];[redacted];0 | False |
| DAT_ASCII_EURUSD_M1_202607.csv | 3906 | 20260705 173100;[redacted];[redacted];[redacted];[redacted];0 | True |
| DAT_ASCII_EURUSD_M1_202607.csv | 3907 | 20260705 173200;[redacted];[redacted];[redacted];[redacted];0 | True |
| DAT_ASCII_EURUSD_M1_202607.csv | 3908 | 20260705 173100;[redacted];[redacted];[redacted];[redacted];0 | True |
| DAT_ASCII_EURUSD_M1_202607.csv | 3909 | 20260705 173200;[redacted];[redacted];[redacted];[redacted];0 | True |
| DAT_ASCII_EURUSD_M1_202607.csv | 3910 | 20260705 173300;[redacted];[redacted];[redacted];[redacted];0 | False |
| DAT_ASCII_EURUSD_M1_202607.csv | 3911 | 20260705 173400;[redacted];[redacted];[redacted];[redacted];0 | True |
| DAT_ASCII_EURUSD_M1_202607.csv | 3912 | 20260705 173500;[redacted];[redacted];[redacted];[redacted];0 | True |
| DAT_ASCII_EURUSD_M1_202607.csv | 3913 | 20260705 173400;[redacted];[redacted];[redacted];[redacted];0 | True |
| DAT_ASCII_EURUSD_M1_202607.csv | 3914 | 20260705 173500;[redacted];[redacted];[redacted];[redacted];0 | True |
| DAT_ASCII_EURUSD_M1_202607.csv | 3915 | 20260705 173600;[redacted];[redacted];[redacted];[redacted];0 | False |
| DAT_ASCII_EURUSD_M1_202607.csv | 3916 | 20260705 173700;[redacted];[redacted];[redacted];[redacted];0 | False |
| DAT_ASCII_EURUSD_M1_202607.csv | 3917 | 20260705 173800;[redacted];[redacted];[redacted];[redacted];0 | False |

- Out-of-order rows: 8

| source_file | line_number | kind | raw_line | previous_raw_line | dst_switch_date |
|---|---|---|---|---|---|
| DAT_ASCII_EURUSD_M1_2019.csv | 306019 | earlier_than_previous | 20191027 190000;[redacted];[redacted];[redacted];[redacted];0 | 20191027 195900;[redacted];[redacted];[redacted];[redacted];0 | eu_end |
| DAT_ASCII_EURUSD_M1_2020.csv | 304341 | earlier_than_previous | 20201025 190000;[redacted];[redacted];[redacted];[redacted];0 | 20201025 195900;[redacted];[redacted];[redacted];[redacted];0 | eu_end |
| DAT_ASCII_EURUSD_M1_2021.csv | 305292 | earlier_than_previous | 20211031 190000;[redacted];[redacted];[redacted];[redacted];0 | 20211031 195900;[redacted];[redacted];[redacted];[redacted];0 | eu_end |
| DAT_ASCII_EURUSD_M1_2022.csv | 308523 | earlier_than_previous | 20221030 190000;[redacted];[redacted];[redacted];[redacted];0 | 20221030 195900;[redacted];[redacted];[redacted];[redacted];0 | eu_end |
| DAT_ASCII_EURUSD_M1_2023.csv | 259334 | earlier_than_previous | 20231029 190000;[redacted];[redacted];[redacted];[redacted];0 | 20231029 195900;[redacted];[redacted];[redacted];[redacted];0 | eu_end |
| DAT_ASCII_EURUSD_M1_2025.csv | 304645 | earlier_than_previous | 20251026 190000;[redacted];[redacted];[redacted];[redacted];0 | 20251026 195900;[redacted];[redacted];[redacted];[redacted];0 | eu_end |
| DAT_ASCII_EURUSD_M1_202607.csv | 3908 | earlier_than_previous | 20260705 173100;[redacted];[redacted];[redacted];[redacted];0 | 20260705 173200;[redacted];[redacted];[redacted];[redacted];0 |  |
| DAT_ASCII_EURUSD_M1_202607.csv | 3913 | earlier_than_previous | 20260705 173400;[redacted];[redacted];[redacted];[redacted];0 | 20260705 173500;[redacted];[redacted];[redacted];[redacted];0 |  |

## 8. Gaps (all categories are hypotheses unless independently verified)

Gaps longer than the short-gap threshold, plus weekends. Precedence: weekend, then DST date, then holiday calendar, else unexplained. Holiday dates are plausible feed closures, not verified market closures.

| hypothesis_category | gaps | missing_bars |
|---|---|---|
| likely_weekend_or_market_closure | 600 | 1730473 |
| possible_dst_effect | 18 | 1440 |
| possible_holiday | 58 | 52725 |
| unexplained | 643 | 44446 |

Unexplained gaps in 2023: 634 (42546 missing bars). Largest unexplained gaps outside 2023:

| last_bar_before | first_bar_after | missing_bars | start_weekday |
|---|---|---|---|
| 2020-11-29 23:59:00 | 2020-11-30 19:00:00 | 1140 | Sunday |
| 2026-05-22 11:59:00 | 2026-05-22 15:00:00 | 180 | Friday |
| 2024-01-16 15:59:00 | 2024-01-16 19:00:00 | 180 | Tuesday |
| 2026-05-12 07:59:00 | 2026-05-12 10:00:00 | 120 | Tuesday |
| 2024-01-16 11:59:00 | 2024-01-16 13:00:00 | 60 | Tuesday |
| 2026-05-12 14:59:00 | 2026-05-12 16:00:00 | 60 | Tuesday |
| 2026-05-22 02:59:00 | 2026-05-22 04:00:00 | 60 | Friday |
| 2026-05-22 07:59:00 | 2026-05-22 09:00:00 | 60 | Friday |
| 2015-08-21 13:16:00 | 2015-08-21 13:57:00 | 40 | Friday |

## 9. Decision table

| question | evidence | status | next_verification_step |
|---|---|---|---|
| Is the raw clock fixed UTC-5 (EST, no DST)? | Documented: HistData FAQ says EST without DST. Observed: intraday anchor consistency 2015-2018 H1 2/6, H2 6/6, H3 4/6; 2019-2026 H1 4/6, H2 4/6, H3 6/6. | Contradicted by observed evidence | Ask HistData which clock the M1 ASCII files use; compare overlapping days with an independent UTC-stamped M1 source |
| What clock do 2015-2018 timestamps follow? | Intraday anchors 2015-2018: H1 2/6, H2 6/6, H3 4/6. Weekly opens 2015-2018 (17:00 NY convention): H1 68/204, H2 204/204, H3 191/204. | Only H2_america_new_york is consistent with all checks; hypothesis, not verified against a UTC source | Cross-check against an independent UTC-stamped source for several weeks in each regime |
| What clock do 2019-2026 timestamps follow? | Intraday anchors 2019-2026: H1 4/6, H2 4/6, H3 6/6. Weekly opens 2019-2026: H1 157/396, H2 358/396, H3 382/396. See dst_transitions.csv for the switch-Sunday hours. | Only H3_ny_offset_eu_dates is consistent with all checks; hypothesis, not verified against a UTC source | Same UTC cross-check; ask HistData whether their feed changed between 2018 and 2019 |
| When did the behaviour change? | US 08:30 anchor in US-summer/EU-standard windows by year: 2015 autumn: 08:30; 2015 spring: 08:30; 2016 autumn: 08:30; 2016 spring: 08:30; 2017 autumn: 08:30; 2017 spring: 08:30; 2018 autumn: 08:30; 2018 spring: 08:30; 2019 autumn: 07:30; 2019 spring: 07:30; 2020 autumn: 09:30; 2020 spring: 08:30; 2021 autumn: 07:30; 2021 spring: 07:30; 2022 autumn: 07:30; 2022 spring: 07:30; 2023 autumn: 07:30; 2023 spring: 07:30; 2024 autumn: 07:30; 2024 spring: 07:30; 2025 autumn: 08:30; 2025 spring: 07:30; 2026 spring: 07:30. | Last H2-like window: 2025 window_autumn; first H3-like window: 2019 window_spring; H2-like windows after the change: 2020 window_spring, 2025 window_autumn. Hypothesis, not verified | Inspect raw data and an external source around the bracketing windows |
| Why does autumn 2024 lack the October repeated hour? | Transition rows: eu_end 2024-10-27: open 2024-10-27 17:00:00, dup rows 0, gaps []; us_end 2024-11-03: open 2024-11-03 17:00:00, dup rows 0, gaps []. 2024 autumn window US 08:30 anchor: 07:30. | Unresolved | Compare 2024-10-27 to 2024-11-03 against an external UTC source; ask HistData |
| Is the 17:00 New York weekly open independently supported? | Documented only as broker/industry convention (e.g. FXCM rollover at 17:00 ET; brokers vary). Observed weekly opens consistent with 17:00 NY under each hypothesis: 2015-2018 H1 68/204, H2 204/204, H3 191/204; 2019-2026 H1 157/396, H2 358/396, H3 382/396. | Partially supported (convention); used only as corroboration, never alone | Not needed for the timezone decision if intraday anchors and a UTC cross-check agree |
| Which 2026-07-05 conflicting record is correct? | 4 timestamps x 2 variants, out of order (duplicates_conflicting.csv). | Unresolved; no record chosen | Compare with an independent source or a fresh HistData download of 2026-07 |
| Are the identical October repeated hours a DST artefact? | 6 identical groups; on an EU autumn switch Sunday: 6; time spans: 19:00-19:59. | Hypothesis: clock falling back on EU date (fits H3); not verified | Decide policy after timezone is resolved: identical copies carry no conflicting information |
| Is the March missing hour real missing data or a clock jump? | EU spring switch Sundays with a ~60-bar gap: 8/12 (2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026); TXT tick gaps on those days: 18:59:56 3597s, 18:59:58 3595s, 18:59:58 3595s, 18:59:58 3596s, 18:59:56 3597s, 18:59:57 3596s, 18:59:59 3594s, 18:59:57 3597s. | Hypothesis: clock jump on EU date (fits H3), not lost market time; not verified | UTC cross-check of those Sundays |
| What caused the Feb-Jul 2023 gaps? | 634 unexplained long gaps in 2023 (gaps_long.csv). | Unexplained (a source-feed outage is plausible); not verified | Compare against an independent source; check whether a newer HistData 2023 file differs |
| Are the remaining unexplained gaps real outages? | 643 unexplained long gaps in total. | Unexplained | Spot-check largest ones against an independent source |
