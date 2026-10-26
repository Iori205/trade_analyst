# EURUSD M1 raw data audit

Generated (UTC): 2026-10-22 10:32:51

All timestamps below are **naive source-clock values**. Source timezone: **UNVERIFIED** (vendor documentation: EST, no DST (UTC-5)). No record was modified, dropped or converted.

Source files hashed before and after the audit: 42; unchanged: **YES**

## 1. Inventory

| period | rows | malformed_rows | price_decimals | csv_bytes | txt_bytes | first_timestamp | last_timestamp |
|---|---|---|---|---|---|---|---|
| 2015 | 372210 | 0 | 6 | 20099340 | 85671 | 20150101 130000 | 20151231 165800 |
| 2016 | 372679 | 0 | 6 | 20124666 | 95143 | 20160103 170000 | 20161230 165800 |
| 2017 | 371635 | 0 | 6 | 20068290 | 117602 | 20170102 020000 | 20171229 165700 |
| 2018 | 372607 | 0 | 6 | 20120778 | 120118 | 20180101 170000 | 20181231 165900 |
| 2019 | 372530 | 0 | 6 | 20116620 | 29266 | 20190101 170200 | 20191231 165900 |
| 2020 | 372335 | 0 | 6 | 20106090 | 108218 | 20200101 170000 | 20201231 165800 |
| 2021 | 369502 | 0 | 6 | 19953108 | 341751 | 20210103 170000 | 20211231 165800 |
| 2022 | 372865 | 0 | 6 | 20134710 | 114213 | 20220102 170300 | 20221230 165800 |
| 2023 | 322638 | 0 | 6 | 17422452 | 167328 | 20230101 170400 | 20231229 165800 |
| 2024 | 372379 | 0 | 6 | 20108466 | 184031 | 20240101 170000 | 20241231 165800 |
| 2025 | 372084 | 0 | 6 | 20092536 | 108302 | 20250101 170000 | 20251231 165700 |
| 202601 | 30149 | 0 | 6 | 1628046 | 8480 | 20260101 170400 | 20260130 165800 |
| 202602 | 28703 | 0 | 6 | 1549962 | 6984 | 20260201 170000 | 20260227 165800 |
| 202603 | 31979 | 0 | 6 | 1726866 | 6432 | 20260301 170000 | 20260331 235800 |
| 202604 | 31531 | 0 | 6 | 1702674 | 12937 | 20260401 000000 | 20260430 235800 |
| 202605 | 29545 | 0 | 6 | 1595430 | 13255 | 20260501 000000 | 20260531 235800 |
| 202606 | 31520 | 0 | 6 | 1702080 | 14270 | 20260601 000000 | 20260630 235800 |
| 202607 | 32537 | 0 | 6 | 1756998 | 14216 | 20260701 000000 | 20260731 165800 |
| 202608 | 30496 | 0 | 6 | 1646784 | 16793 | 20260802 170000 | 20260831 235800 |

Raw rows: 4,289,924. Distinct timestamps: 4,289,560. Rows with volume == 0: 4,289,924 of 4,289,924.

## 2. Per-file checks

| source_file | rows | first_timestamp | last_timestamp | min_timestamp | max_timestamp | rows_outside_named_period | monotonic_increasing | duplicate_timestamp_rows | nonzero_volume_rows | nonzero_second_rows |
|---|---|---|---|---|---|---|---|---|---|---|
| DAT_ASCII_EURUSD_M1_2015.csv | 372210 | 2015-01-01 13:00:00 | 2015-12-31 16:58:00 | 2015-01-01 13:00:00 | 2015-12-31 16:58:00 | 0 | True | 0 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_2016.csv | 372679 | 2016-01-03 17:00:00 | 2016-12-30 16:58:00 | 2016-01-03 17:00:00 | 2016-12-30 16:58:00 | 0 | True | 0 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_2017.csv | 371635 | 2017-01-02 02:00:00 | 2017-12-29 16:57:00 | 2017-01-02 02:00:00 | 2017-12-29 16:57:00 | 0 | True | 0 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_2018.csv | 372607 | 2018-01-01 17:00:00 | 2018-12-31 16:59:00 | 2018-01-01 17:00:00 | 2018-12-31 16:59:00 | 0 | True | 0 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_2019.csv | 372530 | 2019-01-01 17:02:00 | 2019-12-31 16:59:00 | 2019-01-01 17:02:00 | 2019-12-31 16:59:00 | 0 | False | 60 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_2020.csv | 372335 | 2020-01-01 17:00:00 | 2020-12-31 16:58:00 | 2020-01-01 17:00:00 | 2020-12-31 16:58:00 | 0 | False | 60 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_2021.csv | 369502 | 2021-01-03 17:00:00 | 2021-12-31 16:58:00 | 2021-01-03 17:00:00 | 2021-12-31 16:58:00 | 0 | False | 60 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_2022.csv | 372865 | 2022-01-02 17:03:00 | 2022-12-30 16:58:00 | 2022-01-02 17:03:00 | 2022-12-30 16:58:00 | 0 | False | 60 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_2023.csv | 322638 | 2023-01-01 17:04:00 | 2023-12-29 16:58:00 | 2023-01-01 17:04:00 | 2023-12-29 16:58:00 | 0 | False | 60 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_2024.csv | 372379 | 2024-01-01 17:00:00 | 2024-12-31 16:58:00 | 2024-01-01 17:00:00 | 2024-12-31 16:58:00 | 0 | True | 0 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_2025.csv | 372084 | 2025-01-01 17:00:00 | 2025-12-31 16:57:00 | 2025-01-01 17:00:00 | 2025-12-31 16:57:00 | 0 | False | 60 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_202601.csv | 30149 | 2026-01-01 17:04:00 | 2026-01-30 16:58:00 | 2026-01-01 17:04:00 | 2026-01-30 16:58:00 | 0 | True | 0 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_202602.csv | 28703 | 2026-02-01 17:00:00 | 2026-02-27 16:58:00 | 2026-02-01 17:00:00 | 2026-02-27 16:58:00 | 0 | True | 0 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_202603.csv | 31979 | 2026-03-01 17:00:00 | 2026-03-31 23:58:00 | 2026-03-01 17:00:00 | 2026-03-31 23:58:00 | 0 | True | 0 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_202604.csv | 31531 | 2026-04-01 00:00:00 | 2026-04-30 23:58:00 | 2026-04-01 00:00:00 | 2026-04-30 23:58:00 | 0 | True | 0 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_202605.csv | 29545 | 2026-05-01 00:00:00 | 2026-05-31 23:58:00 | 2026-05-01 00:00:00 | 2026-05-31 23:58:00 | 0 | True | 0 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_202606.csv | 31520 | 2026-06-01 00:00:00 | 2026-06-30 23:58:00 | 2026-06-01 00:00:00 | 2026-06-30 23:58:00 | 0 | True | 0 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_202607.csv | 32537 | 2026-07-01 00:00:00 | 2026-07-31 16:58:00 | 2026-07-01 00:00:00 | 2026-07-31 16:58:00 | 0 | False | 4 | 0 | 0 |
| DAT_ASCII_EURUSD_M1_202608.csv | 30496 | 2026-08-02 17:00:00 | 2026-08-31 23:58:00 | 2026-08-02 17:00:00 | 2026-08-31 23:58:00 | 0 | True | 0 | 0 | 0 |

File range overlaps:

none

## 3. Ordering

Rows not later than the previous row in the same file: 8

| source_file | source_row | timestamp | previous_timestamp |
|---|---|---|---|
| DAT_ASCII_EURUSD_M1_2019.csv | 306018 | 2019-10-27 19:00:00 | 2019-10-27 19:59:00 |
| DAT_ASCII_EURUSD_M1_2020.csv | 304340 | 2020-10-25 19:00:00 | 2020-10-25 19:59:00 |
| DAT_ASCII_EURUSD_M1_2021.csv | 305291 | 2021-10-31 19:00:00 | 2021-10-31 19:59:00 |
| DAT_ASCII_EURUSD_M1_2022.csv | 308522 | 2022-10-30 19:00:00 | 2022-10-30 19:59:00 |
| DAT_ASCII_EURUSD_M1_2023.csv | 259333 | 2023-10-29 19:00:00 | 2023-10-29 19:59:00 |
| DAT_ASCII_EURUSD_M1_2025.csv | 304644 | 2025-10-26 19:00:00 | 2025-10-26 19:59:00 |
| DAT_ASCII_EURUSD_M1_202607.csv | 3907 | 2026-07-05 17:31:00 | 2026-07-05 17:32:00 |
| DAT_ASCII_EURUSD_M1_202607.csv | 3912 | 2026-07-05 17:34:00 | 2026-07-05 17:35:00 |

## 4. Duplicate timestamps

Rows involved: 728. Timestamps: 364. Conflicting timestamps: 4.

| source_file | date | weekday | status | timestamps | rows | first | last | files |
|---|---|---|---|---|---|---|---|---|
| DAT_ASCII_EURUSD_M1_2019.csv | 2019-10-27 | Sunday | identical | 60 | 120 | 2019-10-27 19:00:00 | 2019-10-27 19:59:00 | 1 |
| DAT_ASCII_EURUSD_M1_2020.csv | 2020-10-25 | Sunday | identical | 60 | 120 | 2020-10-25 19:00:00 | 2020-10-25 19:59:00 | 1 |
| DAT_ASCII_EURUSD_M1_2021.csv | 2021-10-31 | Sunday | identical | 60 | 120 | 2021-10-31 19:00:00 | 2021-10-31 19:59:00 | 1 |
| DAT_ASCII_EURUSD_M1_2022.csv | 2022-10-30 | Sunday | identical | 60 | 120 | 2022-10-30 19:00:00 | 2022-10-30 19:59:00 | 1 |
| DAT_ASCII_EURUSD_M1_2023.csv | 2023-10-29 | Sunday | identical | 60 | 120 | 2023-10-29 19:00:00 | 2023-10-29 19:59:00 | 1 |
| DAT_ASCII_EURUSD_M1_2025.csv | 2025-10-26 | Sunday | identical | 60 | 120 | 2025-10-26 19:00:00 | 2025-10-26 19:59:00 | 1 |
| DAT_ASCII_EURUSD_M1_202607.csv | 2026-07-05 | Sunday | conflicting | 4 | 8 | 2026-07-05 17:31:00 | 2026-07-05 17:35:00 | 1 |

## 5. OHLC validity

Rows failing at least one check: 0

| check | rows |
|---|---|
| missing_price | 0 |
| non_positive_price | 0 |
| high_below_low | 0 |
| high_below_open_or_close | 0 |
| low_above_open_or_close | 0 |

## 6. Gaps (source clock)

Weekend = Fri/Sat to Sun/Mon within 56h; short = up to 30 missing bars.

| year | n_holiday_candidate | n_intraweek_long | n_intraweek_short | n_weekend | missing_holiday_candidate | missing_intraweek_long | missing_intraweek_short | missing_weekend |
|---|---|---|---|---|---|---|---|---|
| 2015 | 2 | 1 | 530 | 51 | 4684 | 40 | 585 | 146880 |
| 2016 | 2 | 0 | 626 | 51 | 5281 | 0 | 718 | 146922 |
| 2017 | 2 | 0 | 715 | 50 | 7741 | 0 | 783 | 144000 |
| 2018 | 2 | 0 | 797 | 52 | 5164 | 0 | 951 | 149760 |
| 2019 | 3 | 2 | 204 | 52 | 2341 | 420 | 233 | 150136 |
| 2020 | 2 | 2 | 1029 | 51 | 5166 | 1200 | 1494 | 146904 |
| 2021 | 1 | 2 | 2871 | 51 | 4321 | 1260 | 3668 | 146909 |
| 2022 | 0 | 1 | 1058 | 52 | 0 | 60 | 1481 | 149814 |
| 2023 | 1 | 680 | 1139 | 51 | 845 | 50230 | 1860 | 148647 |
| 2024 | 2 | 4 | 1544 | 52 | 5165 | 360 | 2182 | 149834 |
| 2025 | 2 | 1 | 911 | 52 | 2287 | 60 | 1434 | 149794 |
| 2026 | 1 | 6 | 792 | 35 | 1446 | 540 | 1026 | 100873 |

Largest non-weekend, non-short gaps (top 25):

| last_bar_before | first_bar_after | duration | missing_bars | category |
|---|---|---|---|---|
| 2015-12-24 13:59:00 | 2015-12-27 17:07:00 | 3 days 03:08:00 | 4507 | holiday_candidate |
| 2017-12-29 16:57:00 | 2018-01-01 17:00:00 | 3 days 00:03:00 | 4322 | holiday_candidate |
| 2020-12-31 16:58:00 | 2021-01-03 17:00:00 | 3 days 00:02:00 | 4321 | holiday_candidate |
| 2023-12-29 16:58:00 | 2024-01-01 17:00:00 | 3 days 00:02:00 | 4321 | holiday_candidate |
| 2015-12-31 16:58:00 | 2016-01-03 17:00:00 | 3 days 00:02:00 | 4321 | holiday_candidate |
| 2017-12-22 16:59:00 | 2017-12-25 17:00:00 | 3 days 00:01:00 | 4320 | holiday_candidate |
| 2023-04-06 19:59:00 | 2023-04-09 17:04:00 | 2 days 21:05:00 | 4144 | intraweek_long |
| 2020-12-25 02:59:00 | 2020-12-27 17:06:00 | 2 days 14:07:00 | 3726 | holiday_candidate |
| 2016-12-30 16:58:00 | 2017-01-02 02:00:00 | 2 days 09:02:00 | 3421 | holiday_candidate |
| 2025-12-31 16:57:00 | 2026-01-01 17:04:00 | 1 days 00:07:00 | 1446 | holiday_candidate |
| 2018-12-31 16:59:00 | 2019-01-01 17:02:00 | 1 days 00:03:00 | 1442 | holiday_candidate |
| 2024-12-31 16:58:00 | 2025-01-01 17:00:00 | 1 days 00:02:00 | 1441 | holiday_candidate |
| 2019-12-31 16:59:00 | 2020-01-01 17:00:00 | 1 days 00:01:00 | 1440 | holiday_candidate |
| 2021-05-30 23:59:00 | 2021-05-31 20:00:00 | 0 days 20:01:00 | 1200 | intraweek_long |
| 2020-11-29 23:59:00 | 2020-11-30 19:00:00 | 0 days 19:01:00 | 1140 | intraweek_long |
| 2016-12-26 01:59:00 | 2016-12-26 18:00:00 | 0 days 16:01:00 | 960 | holiday_candidate |
| 2025-12-25 02:57:00 | 2025-12-25 17:04:00 | 0 days 14:07:00 | 846 | holiday_candidate |
| 2023-12-25 02:58:00 | 2023-12-25 17:04:00 | 0 days 14:06:00 | 845 | holiday_candidate |
| 2024-12-25 02:59:00 | 2024-12-25 17:04:00 | 0 days 14:05:00 | 844 | holiday_candidate |
| 2018-12-25 02:58:00 | 2018-12-25 17:01:00 | 0 days 14:03:00 | 842 | holiday_candidate |
| 2019-12-25 02:59:00 | 2019-12-25 17:00:00 | 0 days 14:01:00 | 840 | holiday_candidate |
| 2019-05-26 23:59:00 | 2019-05-27 06:00:00 | 0 days 06:01:00 | 360 | intraweek_long |
| 2026-05-22 11:59:00 | 2026-05-22 15:00:00 | 0 days 03:01:00 | 180 | intraweek_long |
| 2024-01-16 15:59:00 | 2024-01-16 19:00:00 | 0 days 03:01:00 | 180 | intraweek_long |
| 2023-03-23 14:59:00 | 2023-03-23 18:00:00 | 0 days 03:01:00 | 180 | intraweek_long |

Intraweek missing bars by month:

| month | intraweek_long | intraweek_short |
|---|---|---|
| 2015-01 | 0 | 44 |
| 2015-02 | 0 | 48 |
| 2015-03 | 0 | 27 |
| 2015-04 | 0 | 41 |
| 2015-05 | 0 | 51 |
| 2015-06 | 0 | 61 |
| 2015-07 | 0 | 53 |
| 2015-08 | 40 | 63 |
| 2015-09 | 0 | 72 |
| 2015-10 | 0 | 60 |
| 2015-11 | 0 | 22 |
| 2015-12 | 0 | 43 |
| 2016-01 | 0 | 15 |
| 2016-02 | 0 | 8 |
| 2016-03 | 0 | 94 |
| 2016-04 | 0 | 34 |
| 2016-05 | 0 | 69 |
| 2016-06 | 0 | 22 |
| 2016-07 | 0 | 85 |
| 2016-08 | 0 | 96 |
| 2016-09 | 0 | 114 |
| 2016-10 | 0 | 87 |
| 2016-11 | 0 | 25 |
| 2016-12 | 0 | 69 |
| 2017-01 | 0 | 59 |
| 2017-02 | 0 | 20 |
| 2017-03 | 0 | 39 |
| 2017-04 | 0 | 58 |
| 2017-05 | 0 | 65 |
| 2017-06 | 0 | 65 |
| 2017-07 | 0 | 47 |
| 2017-08 | 0 | 45 |
| 2017-09 | 0 | 85 |
| 2017-10 | 0 | 114 |
| 2017-11 | 0 | 98 |
| 2017-12 | 0 | 88 |
| 2018-01 | 0 | 33 |
| 2018-02 | 0 | 49 |
| 2018-03 | 0 | 109 |
| 2018-04 | 0 | 167 |
| 2018-05 | 0 | 114 |
| 2018-06 | 0 | 47 |
| 2018-07 | 0 | 80 |
| 2018-08 | 0 | 88 |
| 2018-09 | 0 | 80 |
| 2018-10 | 0 | 58 |
| 2018-11 | 0 | 81 |
| 2018-12 | 0 | 45 |
| 2019-01 | 0 | 12 |
| 2019-02 | 0 | 8 |
| 2019-03 | 60 | 6 |
| 2019-04 | 0 | 14 |
| 2019-05 | 360 | 10 |
| 2019-06 | 0 | 11 |
| 2019-07 | 0 | 17 |
| 2019-08 | 0 | 11 |
| 2019-09 | 0 | 39 |
| 2019-10 | 0 | 22 |
| 2019-11 | 0 | 30 |
| 2019-12 | 0 | 53 |
| 2020-01 | 0 | 27 |
| 2020-02 | 0 | 95 |
| 2020-03 | 60 | 28 |
| 2020-04 | 0 | 60 |
| 2020-05 | 0 | 72 |
| 2020-06 | 0 | 94 |
| 2020-07 | 0 | 146 |
| 2020-08 | 0 | 183 |
| 2020-09 | 0 | 261 |
| 2020-10 | 0 | 166 |
| 2020-11 | 1140 | 125 |
| 2020-12 | 0 | 237 |
| 2021-01 | 0 | 146 |
| 2021-02 | 0 | 187 |
| 2021-03 | 60 | 191 |
| 2021-04 | 0 | 417 |
| 2021-05 | 1200 | 352 |
| 2021-06 | 0 | 367 |
| 2021-07 | 0 | 269 |
| 2021-08 | 0 | 584 |
| 2021-09 | 0 | 406 |
| 2021-10 | 0 | 354 |
| 2021-11 | 0 | 152 |
| 2021-12 | 0 | 243 |
| 2022-01 | 0 | 185 |
| 2022-02 | 0 | 111 |
| 2022-03 | 60 | 85 |
| 2022-04 | 0 | 108 |
| 2022-05 | 0 | 161 |
| 2022-06 | 0 | 144 |
| 2022-07 | 0 | 104 |
| 2022-08 | 0 | 77 |
| 2022-09 | 0 | 77 |
| 2022-10 | 0 | 155 |
| 2022-11 | 0 | 83 |
| 2022-12 | 0 | 191 |
| 2023-01 | 60 | 214 |
| 2023-02 | 2940 | 129 |
| 2023-03 | 9306 | 188 |
| 2023-04 | 11647 | 100 |
| 2023-05 | 9300 | 166 |
| 2023-06 | 8880 | 127 |
| 2023-07 | 8043 | 85 |
| 2023-08 | 0 | 128 |
| 2023-09 | 54 | 232 |
| 2023-10 | 0 | 90 |
| 2023-11 | 0 | 119 |
| 2023-12 | 0 | 282 |
| 2024-01 | 300 | 93 |
| 2024-02 | 0 | 98 |
| 2024-03 | 60 | 154 |
| 2024-04 | 0 | 167 |
| 2024-05 | 0 | 280 |
| 2024-06 | 0 | 266 |
| 2024-07 | 0 | 277 |
| 2024-08 | 0 | 104 |
| 2024-09 | 0 | 169 |
| 2024-10 | 0 | 109 |
| 2024-11 | 0 | 44 |
| 2024-12 | 0 | 421 |
| 2025-01 | 0 | 72 |
| 2025-02 | 0 | 67 |
| 2025-03 | 60 | 72 |
| 2025-04 | 0 | 63 |
| 2025-05 | 0 | 40 |
| 2025-06 | 0 | 70 |
| 2025-07 | 0 | 74 |
| 2025-08 | 0 | 102 |
| 2025-09 | 0 | 138 |
| 2025-10 | 0 | 108 |
| 2025-11 | 0 | 127 |
| 2025-12 | 0 | 501 |
| 2026-01 | 0 | 85 |
| 2026-02 | 0 | 92 |
| 2026-03 | 60 | 60 |
| 2026-04 | 0 | 149 |
| 2026-05 | 480 | 155 |
| 2026-06 | 0 | 156 |
| 2026-07 | 0 | 166 |
| 2026-08 | 0 | 163 |

Distinct bars per month:

| month | bars |
|---|---|
| 2015-01 | 30259 |
| 2015-02 | 28752 |
| 2015-03 | 32073 |
| 2015-04 | 31639 |
| 2015-05 | 30189 |
| 2015-06 | 31619 |
| 2015-07 | 32647 |
| 2015-08 | 30557 |
| 2015-09 | 31608 |
| 2015-10 | 31200 |
| 2015-11 | 30638 |
| 2015-12 | 31029 |
| 2016-01 | 29205 |
| 2016-02 | 30232 |
| 2016-03 | 33026 |
| 2016-04 | 29786 |
| 2016-05 | 32031 |
| 2016-06 | 31658 |
| 2016-07 | 30155 |
| 2016-08 | 33024 |
| 2016-09 | 31146 |
| 2016-10 | 30573 |
| 2016-11 | 31644 |
| 2016-12 | 30199 |
| 2017-01 | 31501 |
| 2017-02 | 28780 |
| 2017-03 | 32661 |
| 2017-04 | 29162 |
| 2017-05 | 33055 |
| 2017-06 | 31195 |
| 2017-07 | 30613 |
| 2017-08 | 33075 |
| 2017-09 | 29735 |
| 2017-10 | 31986 |
| 2017-11 | 31582 |
| 2017-12 | 28290 |
| 2018-01 | 32067 |
| 2018-02 | 28751 |
| 2018-03 | 31151 |
| 2018-04 | 30493 |
| 2018-05 | 33006 |
| 2018-06 | 29773 |
| 2018-07 | 32020 |
| 2018-08 | 32612 |
| 2018-09 | 29140 |
| 2018-10 | 33062 |
| 2018-11 | 31179 |
| 2018-12 | 29353 |
| 2019-01 | 32086 |
| 2019-02 | 28792 |
| 2019-03 | 30169 |
| 2019-04 | 31666 |
| 2019-05 | 31970 |
| 2019-06 | 29208 |
| 2019-07 | 33103 |
| 2019-08 | 31247 |
| 2019-09 | 30616 |
| 2019-10 | 33158 |
| 2019-11 | 29730 |
| 2019-12 | 30725 |
| 2020-01 | 31653 |
| 2020-02 | 28705 |
| 2020-03 | 32005 |
| 2020-04 | 31614 |
| 2020-05 | 30166 |
| 2020-06 | 31585 |
| 2020-07 | 32550 |
| 2020-08 | 30473 |
| 2020-09 | 31419 |
| 2020-10 | 31094 |
| 2020-11 | 29395 |
| 2020-12 | 31616 |
| 2021-01 | 29074 |
| 2021-02 | 28613 |
| 2021-03 | 32869 |
| 2021-04 | 30843 |
| 2021-05 | 29108 |
| 2021-06 | 31310 |
| 2021-07 | 30984 |
| 2021-08 | 31508 |
| 2021-09 | 31274 |
| 2021-10 | 29946 |
| 2021-11 | 31468 |
| 2021-12 | 32445 |
| 2022-01 | 30472 |
| 2022-02 | 28689 |
| 2022-03 | 32975 |
| 2022-04 | 29708 |
| 2022-05 | 31930 |
| 2022-06 | 31528 |
| 2022-07 | 30124 |
| 2022-08 | 33036 |
| 2022-09 | 31178 |
| 2022-10 | 30561 |
| 2022-11 | 31537 |
| 2022-12 | 31067 |
| 2023-01 | 31822 |
| 2023-02 | 25671 |
| 2023-03 | 22906 |
| 2023-04 | 20173 |
| 2023-05 | 23354 |
| 2023-06 | 21833 |
| 2023-07 | 22104 |
| 2023-08 | 32987 |
| 2023-09 | 29534 |
| 2023-10 | 32062 |
| 2023-11 | 31501 |
| 2023-12 | 28631 |
| 2024-01 | 31703 |
| 2024-02 | 30142 |
| 2024-03 | 30026 |
| 2024-04 | 31509 |
| 2024-05 | 32420 |
| 2024-06 | 28954 |
| 2024-07 | 32843 |
| 2024-08 | 31156 |
| 2024-09 | 30488 |
| 2024-10 | 33008 |
| 2024-11 | 29716 |
| 2024-12 | 30414 |
| 2025-01 | 31604 |
| 2025-02 | 28731 |
| 2025-03 | 30527 |
| 2025-04 | 31613 |
| 2025-05 | 31216 |
| 2025-06 | 30587 |
| 2025-07 | 33040 |
| 2025-08 | 30138 |
| 2025-09 | 31542 |
| 2025-10 | 32592 |
| 2025-11 | 29087 |
| 2025-12 | 31347 |
| 2026-01 | 30149 |
| 2026-02 | 28703 |
| 2026-03 | 31979 |
| 2026-04 | 31531 |
| 2026-05 | 29545 |
| 2026-06 | 31520 |
| 2026-07 | 32533 |
| 2026-08 | 30496 |

## 7. Timezone evidence (observations, no conclusion drawn by the code)

If the source clock were a fixed UTC offset while the market opens and closes on New York local time, weekly open/close hours would shift by one hour between US standard and daylight time. If they don't shift, the clock follows a DST-observing zone, or the market convention differs.

Weekly open hour by month:

| month | 16 | 17 | 18 | 19 | 23 |
|---|---|---|---|---|---|
| 1 | 0 | 50 | 0 | 0 | 0 |
| 2 | 0 | 48 | 0 | 0 | 0 |
| 3 | 20 | 33 | 1 | 0 | 0 |
| 4 | 0 | 48 | 2 | 0 | 0 |
| 5 | 0 | 50 | 3 | 0 | 1 |
| 6 | 0 | 49 | 1 | 1 | 0 |
| 7 | 0 | 51 | 2 | 0 | 0 |
| 8 | 0 | 53 | 0 | 0 | 0 |
| 9 | 0 | 47 | 0 | 0 | 0 |
| 10 | 6 | 43 | 0 | 0 | 0 |
| 11 | 0 | 47 | 0 | 0 | 0 |
| 12 | 0 | 43 | 1 | 0 | 0 |

Weekly close hour by month:

| month | 13 | 14 | 15 | 16 |
|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 50 |
| 2 | 0 | 0 | 1 | 47 |
| 3 | 0 | 1 | 22 | 31 |
| 4 | 0 | 0 | 1 | 49 |
| 5 | 0 | 1 | 1 | 52 |
| 6 | 0 | 1 | 2 | 48 |
| 7 | 1 | 0 | 2 | 50 |
| 8 | 0 | 0 | 0 | 53 |
| 9 | 0 | 0 | 0 | 47 |
| 10 | 0 | 0 | 0 | 49 |
| 11 | 0 | 0 | 7 | 40 |
| 12 | 0 | 0 | 0 | 44 |

## 8. HistData TXT status reports (tick-level gaps, not bar gaps)

| file | header_ok | file_ref_matches_csv | reported_gaps | reported_gap_seconds_total | largest_gap_seconds | largest_gap_start | max_tick_interval_ms | unparsed_lines |
|---|---|---|---|---|---|---|---|---|
| DAT_ASCII_EURUSD_M1_2015.txt | True | True | 1423 | 109253 | 2435 | 2015-08-21 13:16:36 | 2435190 | 1 |
| DAT_ASCII_EURUSD_M1_2016.txt | True | True | 1580 | 122550 | 617 | 2016-12-25 18:01:48 | 617500 | 1 |
| DAT_ASCII_EURUSD_M1_2017.txt | True | True | 1954 | 146672 | 352 | 2017-08-20 17:24:13 | 352954 | 1 |
| DAT_ASCII_EURUSD_M1_2018.txt | True | True | 1995 | 157584 | 594 | 2018-04-01 17:42:03 | 594000 | 1 |
| DAT_ASCII_EURUSD_M1_2019.txt | True | True | 484 | 45485 | 3597 | 2019-03-31 18:59:56 | 3597519 | 1 |
| DAT_ASCII_EURUSD_M1_2020.txt | True | True | 1791 | 185712 | 3595 | 2020-03-29 18:59:58 | 3595547 | 1 |
| DAT_ASCII_EURUSD_M1_2021.txt | True | True | 5670 | 522700 | 3595 | 2021-03-28 18:59:58 | 3595272 | 1 |
| DAT_ASCII_EURUSD_M1_2022.txt | True | True | 1891 | 190529 | 3596 | 2022-03-27 18:59:58 | 3596081 | 1 |
| DAT_ASCII_EURUSD_M1_2023.txt | True | True | 2753 | 2960429 | 7216 | 2023-03-12 16:59:37 | 7216883 | 1 |
| DAT_ASCII_EURUSD_M1_2024.txt | True | True | 3051 | 303216 | 3597 | 2024-01-16 11:59:59 | 3597641 | 1 |
| DAT_ASCII_EURUSD_M1_2025.txt | True | True | 1794 | 184326 | 3594 | 2025-03-30 18:59:59 | 3594775 | 1 |
| DAT_ASCII_EURUSD_M1_202601.txt | True | True | 138 | 12139 | 233 | 2026-01-15 17:00:00 | 233396 | 1 |
| DAT_ASCII_EURUSD_M1_202602.txt | True | True | 113 | 11133 | 293 | 2026-02-18 17:26:00 | 293083 | 1 |
| DAT_ASCII_EURUSD_M1_202603.txt | True | True | 104 | 12844 | 3597 | 2026-03-29 18:59:57 | 3597111 | 1 |
| DAT_ASCII_EURUSD_M1_202604.txt | True | True | 212 | 19584 | 1054 | 2026-04-15 17:42:19 | 1054562 | 1 |
| DAT_ASCII_EURUSD_M1_202605.txt | True | True | 217 | 38107 | 7195 | 2026-05-12 07:59:59 | 7195019 | 1 |
| DAT_ASCII_EURUSD_M1_202606.txt | True | True | 234 | 21528 | 363 | 2026-06-28 17:20:45 | 363000 | 1 |
| DAT_ASCII_EURUSD_M1_202607.txt | True | True | 233 | 22036 | 367 | 2026-07-19 17:49:00 | 367000 | 1 |
| DAT_ASCII_EURUSD_M1_202608.txt | True | True | 276 | 24903 | 287 | 2026-08-20 18:04:01 | 287000 | 1 |

## 9. Existing Parquet files (unverified derived data)

Reference = raw rows, stable-sorted, first occurrence per timestamp kept; higher timeframes = left-labelled, left-closed bins on the naive source clock. This tests how the Parquet files may have been built and is not a cleaning decision.

**1m** schema: `{"path": "eurusd_1m.parquet", "rows": 4289560, "columns": ["open", "high", "low", "close"], "dtypes": {"open": "float64", "high": "float64", "low": "float64", "close": "float64"}, "index_name": "timestamp", "index_dtype": "datetime64[ns]", "index_tz": "None", "first": "2015-01-01 13:00:00", "last": "2026-08-31 23:58:00", "duplicate_index": 0, "monotonic_increasing": true}`

**1m** vs raw reference: `{"rows_expected": 4289560, "rows_actual": 4289560, "common_index": 4289560, "only_in_expected": 0, "only_in_actual": 0, "value_mismatch_rows": 0, "max_abs_diff": 0.0, "sample_mismatch_timestamps": []}`

**15m** schema: `{"path": "eurusd_15m.parquet", "rows": 287078, "columns": ["open", "high", "low", "close"], "dtypes": {"open": "float64", "high": "float64", "low": "float64", "close": "float64"}, "index_name": "timestamp", "index_dtype": "datetime64[ns]", "index_tz": "None", "first": "2015-01-01 13:00:00", "last": "2026-08-31 23:45:00", "duplicate_index": 0, "monotonic_increasing": true}`

**15m** vs raw reference: `{"rows_expected": 287078, "rows_actual": 287078, "common_index": 287078, "only_in_expected": 0, "only_in_actual": 0, "value_mismatch_rows": 0, "max_abs_diff": 0.0, "sample_mismatch_timestamps": []}`

**1h** schema: `{"path": "eurusd_1h.parquet", "rows": 71775, "columns": ["open", "high", "low", "close"], "dtypes": {"open": "float64", "high": "float64", "low": "float64", "close": "float64"}, "index_name": "timestamp", "index_dtype": "datetime64[ns]", "index_tz": "None", "first": "2015-01-01 13:00:00", "last": "2026-08-31 23:00:00", "duplicate_index": 0, "monotonic_increasing": true}`

**1h** vs raw reference: `{"rows_expected": 71775, "rows_actual": 71775, "common_index": 71775, "only_in_expected": 0, "only_in_actual": 0, "value_mismatch_rows": 0, "max_abs_diff": 0.0, "sample_mismatch_timestamps": []}`

**4h** schema: `{"path": "eurusd_4h.parquet", "rows": 18726, "columns": ["open", "high", "low", "close"], "dtypes": {"open": "float64", "high": "float64", "low": "float64", "close": "float64"}, "index_name": "timestamp", "index_dtype": "datetime64[ns]", "index_tz": "None", "first": "2015-01-01 12:00:00", "last": "2026-08-31 20:00:00", "duplicate_index": 0, "monotonic_increasing": true}`

**4h** vs raw reference: `{"rows_expected": 18726, "rows_actual": 18726, "common_index": 18726, "only_in_expected": 0, "only_in_actual": 0, "value_mismatch_rows": 0, "max_abs_diff": 0.0, "sample_mismatch_timestamps": []}`

Conflicting duplicate timestamps: which raw occurrence the 1m Parquet holds:

| timestamp | variants | parquet_matches |
|---|---|---|
| 2026-07-05 17:31:00 | 2 | occurrence_1_of_2 (row 3905) |
| 2026-07-05 17:32:00 | 2 | occurrence_1_of_2 (row 3906) |
| 2026-07-05 17:34:00 | 2 | occurrence_1_of_2 (row 3910) |
| 2026-07-05 17:35:00 | 2 | occurrence_1_of_2 (row 3911) |

## 10. Source file hashes

| path | sha256 | unchanged |
|---|---|---|
| data/HISTDATA_COM_ASCII_EURUSD_M12015/DAT_ASCII_EURUSD_M1_2015.csv | 6f3d88318899cf49797017466b88eb033ed0bd1e5d3c380eb197d669e6feab00 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12016/DAT_ASCII_EURUSD_M1_2016.csv | 9f1567957a0203f44c7e995a96fc0a7eca2bc0d0d2a4dee0a2c153a133aee2e6 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12017/DAT_ASCII_EURUSD_M1_2017.csv | d5d095207bcdbfc77b899e4ab69c2fd31cee09791a9ff4c74f9c066fb49a6ac4 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12018/DAT_ASCII_EURUSD_M1_2018.csv | f32278dfac1cd7d0098144e31247435db197ef6ff491ab144b93d4cff3e985b0 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12019/DAT_ASCII_EURUSD_M1_2019.csv | f9248bea5fd065c468859024f5e80f0a54c175fb65b7a919a9deeef20f15989d | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12020/DAT_ASCII_EURUSD_M1_2020.csv | 5230a240dd76344a50c90980fc7594dd29751e602eb778c8c3710626cf9cd662 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12021/DAT_ASCII_EURUSD_M1_2021.csv | 6e342873e2c7d6aafe820a01577ccd2d4b243f96badd9b4b3a95f6cfb80593f8 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12022/DAT_ASCII_EURUSD_M1_2022.csv | 6d807a638acf1caea389f3a708541b4abcac767472da54042cdcc2468a81d0b8 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12023/DAT_ASCII_EURUSD_M1_2023.csv | 7f4bb88af747a61dce9ba21dd99f4585f3163e66a06d3f0df4c2343ecb1e9687 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12024/DAT_ASCII_EURUSD_M1_2024.csv | 0f2412690abe983064f665f3273bd24553e2f4f7bfe96a606b30f65fd74b231d | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12025/DAT_ASCII_EURUSD_M1_2025.csv | d476f9b73a5210e5dd0a7a2f1b2e6da28fbc6ee9b124b05a04c892bd8731d984 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202601/DAT_ASCII_EURUSD_M1_202601.csv | d753e62185a66ffea6bf8cd77c2f8a184894ae7a0f13915adf3481a2dcf2fff7 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202602/DAT_ASCII_EURUSD_M1_202602.csv | 323f0b1d6110a1021bbddcaa87fc3768d3bed3545385ecc1418c2c6c99dd21a5 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202603/DAT_ASCII_EURUSD_M1_202603.csv | 708e4dbacf88e39b4cdea67f71b586ec5182f2773b3522d53de766bf81193199 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202604/DAT_ASCII_EURUSD_M1_202604.csv | 2ef0a65591f2f026c7bcecd625bc0997cfea789f44477e983efbc4005fdb7135 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202605/DAT_ASCII_EURUSD_M1_202605.csv | 1c8342d5bc9f5386017445b213448239969acdcc292e2c3399dae0c25bc0306b | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202606/DAT_ASCII_EURUSD_M1_202606.csv | 02cd20ec11290f99d4be60fba9e23620aa71931cd74e3401314ee977eab5ef31 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202607/DAT_ASCII_EURUSD_M1_202607.csv | 5276412ab2a456155a71348a6dd2e61650ba26ea9605a87ad4f1319232df6ffa | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202608/DAT_ASCII_EURUSD_M1_202608.csv | 3060c51484d3f6882fb4c2fd468673e827a07657cd3708ee31bae08f83226991 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12015/DAT_ASCII_EURUSD_M1_2015.txt | d3b2e8eb11007274f10e39f81e8991335d1d66cc9bc7281f171a5f5bd1f3e705 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12016/DAT_ASCII_EURUSD_M1_2016.txt | 496463a0c83a33b54308c030bc04a4a74e8e9e2ecc47efe513909ca394ca26f6 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12017/DAT_ASCII_EURUSD_M1_2017.txt | 46885b89eb1a6e36edbf342c88c3d4c574851c5591ed2d960516f785786ffaf6 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12018/DAT_ASCII_EURUSD_M1_2018.txt | d762a5fce34fa3e9f16a7c9e6616cc0e9e23500fcab97275ab1ea6d2958ba8bf | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12019/DAT_ASCII_EURUSD_M1_2019.txt | f0046214f0916b85e526d67775ff4362486f32cd35b02a46bb05e3f389026d5d | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12020/DAT_ASCII_EURUSD_M1_2020.txt | 806bbe1b59085c117f57dcca39f54c5ab142d90793120f76d635d93b8cb726d0 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12021/DAT_ASCII_EURUSD_M1_2021.txt | 4e8a51018795c2cf68bee288d2b051f5c7ddc2de84e4c5d9071c73f68423df40 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12022/DAT_ASCII_EURUSD_M1_2022.txt | f52bed823c21dd768be969fd6a0368681f3a2db16e1b868a06375d00c2b31278 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12023/DAT_ASCII_EURUSD_M1_2023.txt | 49c6ee4f13495d5c53655329f27607efc5a74b1dde931465c604de7dd387deed | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12024/DAT_ASCII_EURUSD_M1_2024.txt | 81a82c6cadf4069e7be4c68530dec73c7672b2a934a8e6c3f6487c43b8b72758 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M12025/DAT_ASCII_EURUSD_M1_2025.txt | 2be04e837f414f29a074cc171641b5b4c3c638b4770f6d1bfcd49ab335b3887b | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202601/DAT_ASCII_EURUSD_M1_202601.txt | a4c8ee98ac6c31bdd980155951e8c55911d632eccbce87b69eaad0a49fbe14d6 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202602/DAT_ASCII_EURUSD_M1_202602.txt | eb9b5504168810adc1447de884326bb49af1103d665e15e6b42c76f4f8093d4c | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202603/DAT_ASCII_EURUSD_M1_202603.txt | 2985b11729ed82c3b70fd4f0393eb3080c2f6c77aa9f3266eae412015cef91e8 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202604/DAT_ASCII_EURUSD_M1_202604.txt | 7c03095db17f6d050eabcaa0c63093baf78eaf618df0fab2a2da9f54f403083b | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202605/DAT_ASCII_EURUSD_M1_202605.txt | 364d0070fa115c172e288533c7a2455bd7e6a956c6e5a0ffe6aaeeecfa72e3c2 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202606/DAT_ASCII_EURUSD_M1_202606.txt | f740269f96f328fe95ddfb2e89447a580014a6ebd2dfd9bf56a60547ba553876 | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202607/DAT_ASCII_EURUSD_M1_202607.txt | 4114ff11d4b8ea027d3268f182abe5901a454508afeeb08fbc2e11c98b745f7d | True |
| data/HISTDATA_COM_ASCII_EURUSD_M1202608/DAT_ASCII_EURUSD_M1_202608.txt | 96f6ca517c2ff0d612496aed7352e126b47f6a72075a14b2dc7e09f038ab1a53 | True |
| eurusd_1m.parquet | f16ffc90a3373f2f1370887e74fbb59e0bd479b08ebe78cc69a80306cd82ebd3 | True |
| eurusd_15m.parquet | c3ef3d9d515f524f03f1f843df86577c2f66066ff41509ddc926a69441d7b0a9 | True |
| eurusd_1h.parquet | ca2a56dd637ae3a510d21428389ca4f352e974df13c13bb59fbb4e76b5d424c8 | True |
| eurusd_4h.parquet | f632f31a27b43c2a50fea5df4f70b759626f8dfa743d15b673bcc53c6dcda3e2 | True |
