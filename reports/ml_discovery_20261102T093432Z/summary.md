> **Superseded** by reports/ml_discovery_20261102T093844Z. The models and results are identical, but this version's BH-FDR used a two-sided p, which counted significantly losing variants as findings. The 48 trials in the trial log come from this run.

# ML discovery: triple-barrier labels + walk-forward, train split 2015-2021

Generated 2026-11-02T09:37:36Z by `src/research/ml_discovery.py` (HEAD `ddf7953`, uncommitted script changes: false). scikit-learn 1.5.2.

- **Data:** TRAIN split only (H1 bars and M1 path). Validation and test were not read. Labels whose horizon would end after 2021-12-31 were dropped.
- **Variants:** 48 = 24 labels (4 TP/SL × 3 horizons × long/short) × 2 models. All 48 were added to `reports/trials/trials.csv`.
- **Results below:** out-of-fold only (2018-2021), from an expanding-window walk-forward with an embargo of one horizon.
- **Trade rule:** trade when p·TP − (1−p)·SL − cost_for > 0, one position at a time, with the engine's entry rules. Cost = `cost_for` at p75 + 0.6 commission + 0.2 slippage.

## Top 3 variants (ranked by OOF t-stat)

| variant | trades | expectancy_pips | t_stat | p | q_bh | dsr | win_rate | years_positive | random_median | random_p95 | random_below |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hgb_short_tp2_sl1.5_h4 | 265 | 3.576 | 3.470 | 5.20e-04 | 0.019 | 0.431 | 0.555 | 4 | -0.880 | 0.617 | 100 |
| hgb_short_tp2_sl1.5_h8 | 935 | 1.055 | 1.725 | 0.084 | 0.223 | 1.33e-07 | 0.489 | 4 | -1.278 | -0.417 | 100 |
| tree_short_tp2_sl1_h8 | 67 | 7.434 | 1.481 | 0.139 | 0.293 | 0.359 | 0.463 | 2 | -1.903 | 1.640 | 100 |

Expectancy by year (pips per trade; number of trades in brackets):

| variant | 2018 | 2019 | 2020 | 2021 |
|---|---|---|---|---|
| hgb_short_tp2_sl1.5_h4 | 4.697 (96) | 0.965 (41) | 3.654 (76) | 3.452 (52) |
| hgb_short_tp2_sl1.5_h8 | 0.628 (298) | 0.202 (130) | 1.745 (254) | 1.302 (253) |
| tree_short_tp2_sl1_h8 | – (0) | -6.814 (10) | 8.640 (55) | 45.536 (2) |

## Multiple-testing correction

- **BH-FDR across all 48 variants:** 4 with q < 0.05: hgb_long_tp1_sl1_h4, hgb_long_tp1.5_sl1_h8, hgb_long_tp2_sl1.5_h8, hgb_short_tp2_sl1.5_h4.
- **Deflated Sharpe Ratio:** N = 48 trials, using the per-trade Sharpe of each variant. The best is 0.698. DSR > 0.95 would mean the result is unlikely to come from the best of 48 unskilled trials.
- **Matched random baseline:** same direction, barriers, horizon and entry rules, with random timing and the same number of trades per year, run 100 times. 20 variants beat at least 95 of the 100 random runs: tree_long_tp1.5_sl1_h24, hgb_long_tp1.5_sl1_h24, hgb_long_tp2_sl1_h4, tree_long_tp2_sl1_h24, hgb_long_tp2_sl1_h24, tree_long_tp2_sl1.5_h24, hgb_short_tp1_sl1_h4, hgb_short_tp1_sl1_h8, hgb_short_tp1_sl1_h24, hgb_short_tp1.5_sl1_h4, tree_short_tp1.5_sl1_h8, hgb_short_tp1.5_sl1_h8, hgb_short_tp1.5_sl1_h24, hgb_short_tp2_sl1_h4, tree_short_tp2_sl1_h8, hgb_short_tp2_sl1_h8, tree_short_tp2_sl1_h24, hgb_short_tp2_sl1_h24, hgb_short_tp2_sl1.5_h4, hgb_short_tp2_sl1.5_h8.

## Verdict

None of the top 3 passes all three checks (DSR > 0.95, beating at least 95 of 100 random runs, positive in all 4 OOF years). 4 of 48 variants are significant after BH-FDR. The search found no robust edge on train, so spending validation on any of these variants is not recommended.

## All variants

Full table: `variants.csv`. Chart: `charts/variants.png`.

| variant | trades | expectancy_pips | t_stat | p | q_bh | dsr | win_rate | years_positive | random_median | random_p95 | random_below |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hgb_short_tp2_sl1.5_h4 | 265 | 3.576 | 3.470 | 5.20e-04 | 0.019 | 0.431 | 0.555 | 4 | -0.880 | 0.617 | 100 |
| hgb_short_tp2_sl1.5_h8 | 935 | 1.055 | 1.725 | 0.084 | 0.223 | 1.33e-07 | 0.489 | 4 | -1.278 | -0.417 | 100 |
| tree_short_tp2_sl1_h8 | 67 | 7.434 | 1.481 | 0.139 | 0.293 | 0.359 | 0.463 | 2 | -1.903 | 1.640 | 100 |
| tree_short_tp1.5_sl1_h8 | 7 | 11.519 | 1.219 | 0.223 | 0.389 | 0.698 | 0.714 | 1 | -0.134 | 7.556 | 100 |
| hgb_short_tp2_sl1_h4 | 542 | 0.450 | 0.709 | 0.478 | 0.696 | 2.84e-06 | 0.400 | 2 | -0.968 | -0.010 | 99 |
| hgb_short_tp2_sl1_h8 | 1198 | 0.286 | 0.583 | 0.560 | 0.696 | 2.95e-13 | 0.379 | 3 | -1.437 | -0.766 | 100 |
| hgb_short_tp1.5_sl1_h4 | 779 | 0.268 | 0.576 | 0.564 | 0.696 | 6.70e-09 | 0.463 | 2 | -1.079 | -0.366 | 99 |
| tree_long_tp1.5_sl1_h8 | 18 | 0.697 | 0.077 | 0.938 | 0.947 | 0.197 | 0.444 | 1 | -0.260 | 8.332 | 57 |
| tree_short_tp1_sl1_h8 | 107 | -0.123 | -0.067 | 0.947 | 0.947 | 0.009 | 0.514 | 1 | -0.935 | 0.598 | 81 |
| tree_long_tp1.5_sl1_h24 | 824 | -0.229 | -0.295 | 0.768 | 0.812 | 1.09e-11 | 0.410 | 2 | -1.550 | -0.719 | 100 |
| hgb_short_tp1_sl1_h4 | 1023 | -0.123 | -0.335 | 0.737 | 0.802 | 3.38e-14 | 0.541 | 3 | -0.986 | -0.379 | 100 |
| tree_short_tp2_sl1_h24 | 908 | -0.227 | -0.381 | 0.703 | 0.788 | 6.60e-13 | 0.369 | 2 | -1.741 | -0.843 | 100 |
| hgb_long_tp2_sl1_h4 | 497 | -0.241 | -0.417 | 0.677 | 0.782 | 3.97e-08 | 0.378 | 1 | -1.222 | -0.270 | 95 |
| hgb_short_tp1.5_sl1_h8 | 1253 | -0.199 | -0.472 | 0.637 | 0.760 | 0.000 | 0.439 | 1 | -1.269 | -0.761 | 100 |
| hgb_short_tp2_sl1_h24 | 1682 | -0.319 | -0.619 | 0.536 | 0.696 | 0.000 | 0.353 | 1 | -2.085 | -1.518 | 100 |
| hgb_short_tp1_sl1_h8 | 1459 | -0.213 | -0.633 | 0.527 | 0.696 | 0.000 | 0.533 | 2 | -1.081 | -0.557 | 99 |
| tree_long_tp1_sl1_h8 | 64 | -1.818 | -0.680 | 0.496 | 0.696 | 0.008 | 0.438 | 1 | -0.865 | 1.708 | 23 |
| tree_short_tp1_sl1_h24 | 1002 | -0.392 | -0.886 | 0.376 | 0.579 | 6.66e-16 | 0.538 | 3 | -1.095 | -0.365 | 93 |
| tree_long_tp2_sl1_h24 | 737 | -0.781 | -0.946 | 0.344 | 0.553 | 2.88e-12 | 0.342 | 1 | -1.934 | -0.883 | 98 |
| tree_long_tp1_sl1_h24 | 978 | -0.792 | -1.197 | 0.231 | 0.389 | 1.11e-16 | 0.497 | 0 | -0.967 | -0.305 | 63 |
| hgb_short_tp2_sl1.5_h24 | 1351 | -0.846 | -1.261 | 0.207 | 0.383 | 0.000 | 0.439 | 0 | -1.434 | -0.674 | 90 |
| hgb_long_tp1.5_sl1_h24 | 2224 | -0.527 | -1.371 | 0.170 | 0.332 | 0.000 | 0.414 | 1 | -1.621 | -1.257 | 100 |
| tree_long_tp2_sl1.5_h24 | 812 | -1.178 | -1.466 | 0.143 | 0.293 | 4.72e-15 | 0.420 | 1 | -2.167 | -1.253 | 97 |
| hgb_short_tp1.5_sl1_h24 | 1871 | -0.648 | -1.516 | 0.130 | 0.293 | 0.000 | 0.416 | 1 | -1.480 | -0.936 | 99 |
| hgb_long_tp2_sl1_h24 | 1876 | -0.787 | -1.691 | 0.091 | 0.224 | 0.000 | 0.345 | 1 | -2.445 | -1.912 | 100 |
| tree_short_tp2_sl1.5_h24 | 1085 | -1.207 | -1.774 | 0.076 | 0.216 | 0.000 | 0.440 | 0 | -1.348 | -0.250 | 61 |
| hgb_long_tp1.5_sl1_h4 | 840 | -0.748 | -1.852 | 0.064 | 0.198 | 1.11e-16 | 0.420 | 0 | -1.191 | -0.420 | 82 |
| hgb_long_tp1_sl1_h24 | 2252 | -0.635 | -1.941 | 0.052 | 0.176 | 0.000 | 0.510 | 0 | -0.966 | -0.562 | 90 |
| tree_short_tp1.5_sl1_h24 | 1193 | -1.013 | -1.943 | 0.052 | 0.176 | 0.000 | 0.402 | 0 | -1.373 | -0.693 | 82 |
| hgb_short_tp1_sl1_h24 | 2213 | -0.698 | -2.171 | 0.030 | 0.123 | 0.000 | 0.519 | 1 | -1.100 | -0.774 | 98 |
| hgb_long_tp2_sl1_h8 | 1243 | -1.065 | -2.493 | 0.013 | 0.059 | 0.000 | 0.343 | 1 | -1.430 | -0.742 | 78 |
| hgb_long_tp2_sl1.5_h24 | 1572 | -1.470 | -2.531 | 0.011 | 0.059 | 0.000 | 0.423 | 0 | -1.976 | -1.339 | 92 |
| hgb_long_tp2_sl1.5_h4 | 326 | -1.765 | -2.588 | 0.010 | 0.059 | 4.50e-11 | 0.423 | 0 | -1.223 | -0.407 | 24 |
| hgb_long_tp1_sl1_h8 | 1356 | -0.931 | -2.602 | 0.009 | 0.059 | 0.000 | 0.501 | 0 | -0.942 | -0.465 | 51 |
| hgb_long_tp2_sl1.5_h8 | 987 | -1.541 | -2.966 | 0.003 | 0.028 | 0.000 | 0.414 | 1 | -1.288 | -0.640 | 32 |
| hgb_long_tp1_sl1_h4 | 814 | -1.161 | -2.999 | 0.003 | 0.028 | 0.000 | 0.500 | 0 | -0.977 | -0.436 | 33 |
| hgb_long_tp1.5_sl1_h8 | 1443 | -1.200 | -3.177 | 0.001 | 0.028 | 0.000 | 0.403 | 0 | -1.218 | -0.477 | 52 |
| tree_long_tp1_sl1_h4 | 0 | – | – | – | – | – | – | 0 | – | – | 0 |
| tree_long_tp1.5_sl1_h4 | 0 | – | – | – | – | – | – | 0 | – | – | 0 |
| tree_long_tp2_sl1_h4 | 0 | – | – | – | – | – | – | 0 | – | – | 0 |
| tree_long_tp2_sl1_h8 | 0 | – | – | – | – | – | – | 0 | – | – | 0 |
| tree_long_tp2_sl1.5_h4 | 0 | – | – | – | – | – | – | 0 | – | – | 0 |
| tree_long_tp2_sl1.5_h8 | 0 | – | – | – | – | – | – | 0 | – | – | 0 |
| tree_short_tp1_sl1_h4 | 0 | – | – | – | – | – | – | 0 | – | – | 0 |
| tree_short_tp1.5_sl1_h4 | 0 | – | – | – | – | – | – | 0 | – | – | 0 |
| tree_short_tp2_sl1_h4 | 0 | – | – | – | – | – | – | 0 | – | – | 0 |
| tree_short_tp2_sl1.5_h4 | 0 | – | – | – | – | – | – | 0 | – | – | 0 |
| tree_short_tp2_sl1.5_h8 | 0 | – | – | – | – | – | – | 0 | – | – | 0 |

## Feature importance (top 3 variants)

Permutation importance on each out-of-fold test year (drop in negative log-loss), averaged over the years. The top 8 per variant:

| variant | feature | importance |
|---|---|---|
| hgb_short_tp2_sl1.5_h4 | hour_utc | 0.100 |
| hgb_short_tp2_sl1.5_h4 | atr_pct_30d | 0.014 |
| hgb_short_tp2_sl1.5_h4 | ret_24h_atr | 0.004 |
| hgb_short_tp2_sl1.5_h4 | prev_low_dist_atr | 0.002 |
| hgb_short_tp2_sl1.5_h4 | ema50_h4_dist_atr | 0.002 |
| hgb_short_tp2_sl1.5_h4 | atr_pips | 0.002 |
| hgb_short_tp2_sl1.5_h4 | asia_low_dist_atr | 8.36e-04 |
| hgb_short_tp2_sl1.5_h4 | ret_1h_atr | 7.20e-04 |
| hgb_short_tp2_sl1.5_h8 | hour_utc | 0.071 |
| hgb_short_tp2_sl1.5_h8 | atr_pct_30d | 0.015 |
| hgb_short_tp2_sl1.5_h8 | ret_24h_atr | 0.009 |
| hgb_short_tp2_sl1.5_h8 | prev_low_dist_atr | 0.005 |
| hgb_short_tp2_sl1.5_h8 | ema50_h4_dist_atr | 0.002 |
| hgb_short_tp2_sl1.5_h8 | prev_high_dist_atr | 0.001 |
| hgb_short_tp2_sl1.5_h8 | ret_1h_atr | 9.62e-04 |
| hgb_short_tp2_sl1.5_h8 | atr_pips | 8.07e-04 |
| tree_short_tp2_sl1_h8 | hour_utc | 0.066 |
| tree_short_tp2_sl1_h8 | atr_pct_30d | 0.008 |
| tree_short_tp2_sl1_h8 | ret_24h_atr | 0.001 |
| tree_short_tp2_sl1_h8 | atr_pips | 3.20e-04 |
| tree_short_tp2_sl1_h8 | ema50_h4_dist_atr | 1.51e-04 |
| tree_short_tp2_sl1_h8 | asia_high_broken | 0.000 |
| tree_short_tp2_sl1_h8 | asia_high_dist_atr | 0.000 |
| tree_short_tp2_sl1_h8 | asia_low_broken | 0.000 |

## Decision-tree rules (depth 3, trained 2015-2020; the last fold)

**short_tp2_sl1.5_h4** (class 1 = TP first; weights = training samples per class)

```
|--- atr_pct_30d <= 0.313
|   |--- hour_utc <= 3.500
|   |   |--- ema50_h4_dist_atr <= -5.188
|   |   |   |--- weights: [225.000, 34.000] class: 0
|   |   |--- ema50_h4_dist_atr >  -5.188
|   |   |   |--- weights: [1222.000, 56.000] class: 0
|   |--- hour_utc >  3.500
|   |   |--- hour_utc <= 14.500
|   |   |   |--- weights: [6311.000, 3042.000] class: 0
|   |   |--- hour_utc >  14.500
|   |   |   |--- weights: [708.000, 94.000] class: 0
|--- atr_pct_30d >  0.313
|   |--- hour_utc <= 15.500
|   |   |--- hour_utc <= 4.500
|   |   |   |--- weights: [4860.000, 172.000] class: 0
|   |   |--- hour_utc >  4.500
|   |   |   |--- weights: [6137.000, 1864.000] class: 0
|   |--- hour_utc >  15.500
|   |   |--- hour_utc <= 17.500
|   |   |   |--- weights: [2663.000, 192.000] class: 0
|   |   |--- hour_utc >  17.500
|   |   |   |--- weights: [5172.000, 103.000] class: 0
```

**short_tp2_sl1.5_h8** (class 1 = TP first; weights = training samples per class)

```
|--- hour_utc <= 14.500
|   |--- hour_utc <= 3.500
|   |   |--- atr_pct_30d <= 0.551
|   |   |   |--- weights: [2301.000, 813.000] class: 0
|   |   |--- atr_pct_30d >  0.551
|   |   |   |--- weights: [2334.000, 387.000] class: 0
|   |--- hour_utc >  3.500
|   |   |--- ret_24h_atr <= 0.138
|   |   |   |--- weights: [3876.000, 2868.000] class: 0
|   |   |--- ret_24h_atr >  0.138
|   |   |   |--- weights: [6410.000, 3371.000] class: 0
|--- hour_utc >  14.500
|   |--- hour_utc <= 16.500
|   |   |--- hour_utc <= 15.500
|   |   |   |--- weights: [1011.000, 225.000] class: 0
|   |   |--- hour_utc >  15.500
|   |   |   |--- weights: [1097.000, 137.000] class: 0
|   |--- hour_utc >  16.500
|   |   |--- atr_pct_30d <= 0.261
|   |   |   |--- weights: [228.000, 58.000] class: 0
|   |   |--- atr_pct_30d >  0.261
|   |   |   |--- weights: [6165.000, 313.000] class: 0
```

**short_tp2_sl1_h8** (class 1 = TP first; weights = training samples per class)

```
|--- hour_utc <= 14.500
|   |--- hour_utc <= 3.500
|   |   |--- atr_pct_30d <= 0.561
|   |   |   |--- weights: [2462.000, 719.000] class: 0
|   |   |--- atr_pct_30d >  0.561
|   |   |   |--- weights: [2311.000, 343.000] class: 0
|   |--- hour_utc >  3.500
|   |   |--- ret_24h_atr <= 0.061
|   |   |   |--- weights: [4327.000, 2318.000] class: 0
|   |   |--- ret_24h_atr >  0.061
|   |   |   |--- weights: [7050.000, 2830.000] class: 0
|--- hour_utc >  14.500
|   |--- hour_utc <= 15.500
|   |   |--- ema50_h4_dist_atr <= 1.801
|   |   |   |--- weights: [700.000, 114.000] class: 0
|   |   |--- ema50_h4_dist_atr >  1.801
|   |   |   |--- weights: [331.000, 91.000] class: 0
|   |--- hour_utc >  15.500
|   |   |--- atr_pct_30d <= 0.226
|   |   |   |--- weights: [195.000, 52.000] class: 0
|   |   |--- atr_pct_30d >  0.226
|   |   |   |--- weights: [7340.000, 411.000] class: 0
```

## Method notes and limitations

- **Labels:** these use bid M1 high/low.
  - A barrier fills exactly at its level. A gap through the level, which would give a worse fill, is not modelled.
  - If both barriers are hit in the same minute, the outcome counts as SL.
  - A window with an M1 gap over 30 minutes (weekend, holiday) is not labelled.
- **Target:** y = TP hit first. Time exits count as y = 0 in the model, but the backtest uses their actual return.
- **Features:** computed only from bars that have closed. The H4 EMA uses H4 blocks that have finished.
- **Embargo:** training entries within one horizon before the test year are removed, so their label windows cannot overlap the test year.
- **Models:** fixed hyper-parameters, no tuning.
  - Tree: max_depth 3, min_samples_leaf 200.
  - HGB: 200 iterations, learning rate 0.05, 15 leaves, min_samples_leaf 100, L2 1.0, no early stopping, random_state 0.
- **Cost:** charged once per trade at entry.
- **Trial log:** it now has 351 rows. Selecting the best of these 48 variants for validation is itself a selection, and the DSR above accounts for that.