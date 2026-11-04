# 6E audit and order flow bars v1

Generated 20261104T102752Z. Local files only. Raw hashes matched the manifest before and after the build. Prices are given as pip differences only.

## Findings

1. **Side mapping differs from the task.** The task said buy = A, sell = B. The data and the vendor docs say the reverse, so the bars use buy = B, sell = A. 94.4% of upticks are B and 94.6% of downticks are A, and `delta_ratio` has a positive same-bar correlation with the return in every year (0.26 to 0.32). `databento_dbn` documents A as the sell aggressor and B as the buy aggressor. To follow the task literally, change `side_map` in `config/orderflow_6e_v1.yaml` and build v2; every delta flips sign.
2. **2019 merge: 24 rows removed, all in the join.** Merged count 12,938,193 equals the 12,938,193 Databento quoted. The 5-field key was applied only to the overlap. Across 2019-2023 130,853 rows repeat that key inside one file (25,667 in 2019); they are fills of one match event and were kept. Yearly volume equals ohlcv-1m exactly with them, so a global dedup would have lost real volume.
3. **Rolls fall on bar boundaries.** 36 rolls in 2015-2023, 20 in the trade years. `roll_inside_bar` is true on 0 bars, so a strict inside-the-bar flag would be empty. `roll_flag` is therefore also true on the first bar of a new contract, and `ret_log` is empty there. Jumps are the quarterly futures basis, not moves: median 45.5 pips, range 9.0 to 91.0.
4. **The last weekday before a roll is thin.** Volume on that day is a median 0.17 of normal in the trade years: liquidity has already moved to the next contract but `6E.v.0` has not. Those Friday bars hold a fraction of the market's flow. They are not flagged; `rolls.csv` lists the ratios.
5. **June 2023 roll.** 2023-06-16 14:14:00+00:00 to 2023-06-18 22:00:00+00:00: 3346 minutes. The old contract stopped mid Friday, so the rest of that Friday is missing from `6E.v.0`. The gap table counts this as a weekend.
6. **Spot check:** 2015 fails (r 0.3429, best lag 0). Best lag is 0 in every period, so this is not a clock error. 2015 has 1,015 1-minute moves of at least 0.5% in 6E with no spot move, and the ones inspected reverse the next minute. Without them r is 0.7313, still under 0.9, and Spearman is 0.8752, so the 2015 failure is only partly explained. All other years pass. 2015 is outside the bars.
7. **ohlcv-1m is bucketed on ts_recv.** Bars here use ts_event. Yearly volume agrees exactly, and on ts_recv no minute differs; 3,185 of 1,735,034 minutes differ on ts_event, by moving lots across a minute edge. 490,673 trades have ts_recv before ts_event; the yearly counts are in the table below. The largest step is 2,159 ms, so it can move a trade across a bar edge only by that much.
8. **Gaps.** `gaps_trades_2h_plus.csv` holds the long weekday gaps. Most match shortened holiday sessions. 2019-02-27 00:39 to 03:45 UTC is on no degraded list and is unexplained.
9. **Scope.** 12 of the 14 degraded days have trades; all 12 are flagged and kept. 2021-12-05, 2022-01-02 and 2022-11-06 are Sundays, so their low ratio is normal. The condition is for the whole dataset, not 6E alone. Trades hold no 2024 data, and the `low_quality_period` flag is a spot flag, so it was not applied to the 6E bars.

## Raw trades: order and side

| year | rows | expected | ts_event_order_breaks | ts_recv_order_breaks | key_repeats | A | B | N | N volume % | size_zero |
|---|---|---|---|---|---|---|---|---|---|---|
| 2019 | 12938193 | 12938193 | 0 | 0 | 25667 | 6472189 | 6437873 | 28131 | 0.298 | 0 |
| 2020 | 15998996 | 15998996 | 0 | 0 | 39089 | 8010962 | 7987259 | 775 | 0.024 | 0 |
| 2021 | 11416158 | 11416158 | 0 | 0 | 27512 | 5698882 | 5716798 | 478 | 0.015 | 0 |
| 2022 | 16507447 | 16507447 | 0 | 0 | 22855 | 8300508 | 8206663 | 276 | 0.009 | 0 |
| 2023 | 14315581 | 14315581 | 0 | 0 | 15730 | 7163798 | 7131310 | 20473 | 0.18 | 0 |

The N share rose from July 2023 and was also higher in January-August 2019; it stays under 0.31% of volume. Flags seen: {0: 70952854, 128: 1752, 4: 221769}.

## ohlcv-1m

3,114,056 rows, order breaks 0, duplicate timestamps 0. Minute steps of 5 minutes or more: {'5-29m': 1259, '30-59m': 19, '60-119m': 1809, '2h+ not weekend': 58, 'weekend': 458}.

## 2019 merge

```json
{
 "part_rows": 11971242,
 "tail_rows": 966975,
 "overlap_part_rows": 24,
 "overlap_tail_rows": 24,
 "removed": 24,
 "merged_rows": 12938193,
 "overlap_start_ns": 1574413200018310055,
 "overlap_end_ns": 1574413201927821361,
 "part_only_in_overlap": 0,
 "tail_only_in_overlap": 0
}
```

## Trades vs ohlcv-1m volume

| year | minutes | minutes_differ_ts_event | minutes_differ_ts_recv | volume_trades | volume_ohlcv | ts_recv_before_ts_event | min_recv_minus_event_ms |
|---|---|---|---|---|---|---|---|
| 2019 | 343507 | 385 | 0 | 41820827 | 41820827 | 0 | 0.2 |
| 2020 | 348851 | 1750 | 0 | 45066229 | 45066229 | 447107 | -2158.7 |
| 2021 | 345218 | 385 | 0 | 39680520 | 39680520 | 3 | -23.6 |
| 2022 | 350465 | 395 | 0 | 48950562 | 48950562 | 0 | 0.1 |
| 2023 | 346993 | 270 | 0 | 46044392 | 46044392 | 43563 | -126.3 |

## Side vs tick direction

| year | up: B share | down: A share |
|---|---|---|
| 2019 | 0.9609 | 0.9623 |
| 2020 | 0.9409 | 0.9421 |
| 2021 | 0.9627 | 0.9626 |
| 2022 | 0.9299 | 0.9321 |
| 2023 | 0.945 | 0.947 |

## delta_ratio vs same-bar return (Pearson r)

| year | M15 | H1 |
|---|---|---|
| 2019 | 0.308 | 0.2594 |
| 2020 | 0.3143 | 0.3029 |
| 2021 | 0.3242 | 0.2659 |
| 2022 | 0.2739 | 0.2577 |
| 2023 | 0.3003 | 0.2557 |

## Trades gaps

| year | 5-29m | 30-59m | 60-119m | 2h+ not weekend | weekend |
|---|---|---|---|---|---|
| 2019 | 75 | 4 | 198 | 9 | 51 |
| 2020 | 71 | 2 | 202 | 7 | 50 |
| 2021 | 102 | 3 | 201 | 7 | 50 |
| 2022 | 73 | 0 | 206 | 1 | 50 |
| 2023 | 141 | 5 | 206 | 0 | 51 |

## Degraded days with trades

| date | trades | volume | volume / month median day |
|---|---|---|---|
| 2019-01-15 | 78922 | 220708 | 1.44 |
| 2019-02-22 | 42441 | 135536 | 0.91 |
| 2019-03-13 | 46802 | 148420 | 1.0 |
| 2019-03-26 | 52741 | 159591 | 1.08 |
| 2020-02-27 | 92392 | 347019 | 1.9 |
| 2020-02-28 | 110513 | 387053 | 2.12 |
| 2020-05-05 | 63082 | 157978 | 1.25 |
| 2020-06-30 | 67589 | 189524 | 1.22 |
| 2020-07-01 | 60483 | 172068 | 0.95 |
| 2021-12-05 | 874 | 2143 | 0.02 |
| 2022-01-02 | 628 | 1860 | 0.01 |
| 2022-11-06 | 2035 | 5231 | 0.03 |

2017-11-13 and 2018-10-21 are before the trades start; they appear only in ohlcv-1m.

## Rolls

| old_last_bar_utc | new_first_bar_utc | old_id | new_id | minutes_apart | jump_pips | spot_move_pips | basis_est_pips | last_weekday_vol_ratio |
|---|---|---|---|---|---|---|---|---|
| 2015-03-15 23:50:00+00:00 | 2015-03-16 00:00:00+00:00 | 18005 | 175117 | 10.0 | 9.0 | 0.1 | 8.9 | 0.63 |
| 2015-06-14 23:58:00+00:00 | 2015-06-15 00:00:00+00:00 | 175117 | 175112 | 2.0 | 15.0 | -3.5 | 18.5 | 0.28 |
| 2015-09-13 23:54:00+00:00 | 2015-09-14 00:00:00+00:00 | 175112 | 175135 | 6.0 | 16.0 | -1.3 | 17.3 | 0.4 |
| 2015-12-13 23:59:00+00:00 | 2015-12-14 00:00:00+00:00 | 175135 | 175152 | 1.0 | 27.0 | 7.9 | 19.1 | 0.2 |
| 2016-03-13 23:48:00+00:00 | 2016-03-14 00:00:00+00:00 | 175152 | 175211 | 12.0 | 32.5 | 0.3 | 32.2 | 0.2 |
| 2016-06-12 23:49:00+00:00 | 2016-06-13 00:00:00+00:00 | 175211 | 175241 | 11.0 | 41.0 | 3.9 | 37.1 | 0.22 |
| 2016-09-18 23:44:00+00:00 | 2016-09-19 00:00:00+00:00 | 175241 | 175316 | 16.0 | 39.0 | -3.5 | 42.5 | 0.17 |
| 2016-12-18 23:53:00+00:00 | 2016-12-19 00:00:00+00:00 | 175316 | 175382 | 7.0 | 45.0 | -1.5 | 46.5 | 0.1 |
| 2017-03-12 23:58:00+00:00 | 2017-03-13 00:00:00+00:00 | 175382 | 175376 | 2.0 | 45.5 | -1.9 | 47.4 | 0.23 |
| 2017-06-18 23:54:00+00:00 | 2017-06-19 00:00:00+00:00 | 175376 | 175386 | 6.0 | 54.5 | 0.4 | 54.1 | 0.09 |
| 2017-09-17 23:58:00+00:00 | 2017-09-18 00:00:00+00:00 | 175386 | 173245 | 2.0 | 58.0 | -0.6 | 58.6 | 0.1 |
| 2017-12-17 23:53:00+00:00 | 2017-12-18 00:00:00+00:00 | 173245 | 173248 | 7.0 | 88.5 | 0.6 | 87.9 | 0.23 |
| 2018-03-18 23:52:00+00:00 | 2018-03-19 00:00:00+00:00 | 173248 | 173275 | 8.0 | 85.5 | -0.7 | 86.2 | 0.1 |
| 2018-06-17 23:49:00+00:00 | 2018-06-18 00:00:00+00:00 | 173275 | 173307 | 11.0 | 81.0 | 2.7 | 78.3 | 0.15 |
| 2018-09-16 23:52:00+00:00 | 2018-09-17 00:00:00+00:00 | 173307 | 192848 | 8.0 | 79.0 | -3.3 | 82.3 | 0.14 |
| 2018-12-16 23:58:00+00:00 | 2018-12-17 00:00:00+00:00 | 192848 | 1191 | 2.0 | 91.0 | 1.0 | 90.0 | 0.24 |
| 2019-03-17 23:54:00+00:00 | 2019-03-18 00:00:00+00:00 | 1191 | 5063 | 6.0 | 85.5 | -0.9 | 86.4 | 0.2 |
| 2019-06-16 23:22:00+00:00 | 2019-06-17 00:00:00+00:00 | 5063 | 20159 | 38.0 | 81.5 | 0.1 | 81.4 | 0.18 |
| 2019-09-15 23:27:00+00:00 | 2019-09-16 00:00:00+00:00 | 20159 | 178373 | 33.0 | 71.5 | -1.6 | 73.1 | 0.21 |
| 2019-12-15 23:34:00+00:00 | 2019-12-16 00:00:00+00:00 | 178373 | 56340 | 26.0 | 65.5 | -1.6 | 67.1 | 0.28 |
| 2020-03-15 23:58:00+00:00 | 2020-03-16 00:00:00+00:00 | 56340 | 71003 | 2.0 | 62.0 | 7.5 | 54.5 | 0.17 |
| 2020-06-14 23:48:00+00:00 | 2020-06-15 00:00:00+00:00 | 71003 | 109520 | 12.0 | 19.0 | -2.8 | 21.8 | 0.27 |
| 2020-09-13 23:36:00+00:00 | 2020-09-14 00:00:00+00:00 | 109520 | 98206 | 24.0 | 23.5 | 2.3 | 21.2 | 0.14 |
| 2020-12-13 23:21:00+00:00 | 2020-12-14 00:00:00+00:00 | 98206 | 3903 | 39.0 | 26.5 | -3.0 | 29.5 | 0.2 |
| 2021-03-14 23:59:00+00:00 | 2021-03-15 00:00:00+00:00 | 3903 | 80958 | 1.0 | 24.0 | 0.7 | 23.3 | 0.09 |
| 2021-06-13 23:43:00+00:00 | 2021-06-14 00:00:00+00:00 | 80958 | 244688 | 17.0 | 20.0 | -0.2 | 20.2 | 0.16 |
| 2021-09-12 23:57:00+00:00 | 2021-09-13 00:00:00+00:00 | 244688 | 86136 | 3.0 | 21.5 | 1.6 | 19.9 | 0.14 |
| 2021-12-12 23:29:00+00:00 | 2021-12-13 00:00:00+00:00 | 86136 | 28727 | 31.0 | 19.0 | -8.0 | 27.0 | 0.16 |
| 2022-03-13 23:59:00+00:00 | 2022-03-14 00:00:00+00:00 | 28727 | 11232 | 1.0 | 36.0 | 0.3 | 35.7 | 0.15 |
| 2022-06-12 23:59:00+00:00 | 2022-06-13 00:00:00+00:00 | 11232 | 44629 | 1.0 | 63.5 | 0.4 | 63.1 | 0.18 |
| 2022-09-18 23:46:00+00:00 | 2022-09-19 00:00:00+00:00 | 44629 | 191026 | 14.0 | 61.5 | -2.5 | 64.0 | 0.11 |
| 2022-12-18 23:48:00+00:00 | 2022-12-19 00:00:00+00:00 | 191026 | 270958 | 12.0 | 70.0 | 1.4 | 68.6 | 0.15 |
| 2023-03-12 23:57:00+00:00 | 2023-03-13 00:00:00+00:00 | 270958 | 11985 | 3.0 | 57.5 | -12.0 | 69.5 | 0.2 |
| 2023-06-16 14:14:00+00:00 | 2023-06-18 22:00:00+00:00 | 11985 | 172853 | 3346.0 | 50.0 | -18.2 | 68.2 | 0.01 |
| 2023-09-17 23:34:00+00:00 | 2023-09-18 00:00:00+00:00 | 172853 | 306787 | 26.0 | 45.5 | 3.3 | 42.2 | 0.12 |
| 2023-12-17 23:42:00+00:00 | 2023-12-18 00:00:00+00:00 | 306787 | 156627 | 18.0 | 43.5 | 1.5 | 42.0 | 0.19 |

basis_est = jump minus the spot move between the two bars.

## Spot vs 6E 1-minute returns

Spikes: |6E return| >= 0.5% with |spot return| < 0.1%. All lags are in `spot_corr_by_lag.csv`.

| period | pairs | r_lag0 | best_lag | r_best | spearman_lag0 | spikes | r_lag0_no_spikes |
|---|---|---|---|---|---|---|---|
| 2015 | 331573 | 0.3429 | 0 | 0.3429 | 0.8752 | 1015 | 0.7313 |
| 2016 | 331735 | 0.9646 | 0 | 0.9646 | 0.9171 | 0 | 0.9646 |
| 2017 | 339840 | 0.9619 | 0 | 0.9619 | 0.9164 | 0 | 0.9619 |
| 2018 | 344686 | 0.9664 | 0 | 0.9664 | 0.9306 | 0 | 0.9664 |
| 2019 | 334232 | 0.9515 | 0 | 0.9515 | 0.8833 | 0 | 0.9515 |
| 2020 | 342113 | 0.9696 | 0 | 0.9696 | 0.9316 | 0 | 0.9696 |
| 2021 | 334329 | 0.9573 | 0 | 0.9573 | 0.9109 | 0 | 0.9573 |
| 2022 | 345870 | 0.9773 | 0 | 0.9773 | 0.949 | 0 | 0.9773 |
| 2023 | 297269 | 0.9658 | 0 | 0.9658 | 0.9247 | 0 | 0.9658 |
| 2023 without low_quality_period | 170748 | 0.9681 | 0 | 0.9681 | 0.9273 | 0 | 0.9681 |

## Bars

| file | bars | trades | volume | roll_flag | roll_inside_bar | degraded_flag | ret_log_empty | first | last |
|---|---|---|---|---|---|---|---|---|---|
| M15/train | 70966 | 40353347 | 126567576 | 12 | 0 | 817 | 13 | 2019-01-01 23:00:00+00:00 | 2021-12-31 21:45:00+00:00 |
| M15/validation | 47379 | 30823028 | 94994954 | 8 | 0 | 8 | 9 | 2022-01-02 23:00:00+00:00 | 2023-12-29 21:45:00+00:00 |
| H1/train | 17753 | 40353347 | 126567576 | 12 | 0 | 205 | 13 | 2019-01-01 23:00:00+00:00 | 2021-12-31 21:00:00+00:00 |
| H1/validation | 11851 | 30823028 | 94994954 | 8 | 0 | 2 | 9 | 2022-01-02 23:00:00+00:00 | 2023-12-29 21:00:00+00:00 |

