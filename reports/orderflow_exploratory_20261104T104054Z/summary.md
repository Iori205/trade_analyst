# Order flow exploratory statistics (train 2019-2021)

Generated 20261104T104054Z. Inputs: order flow bars v1 (train files) and EURUSD spot bars v1 (train file). Validation and test were not read.

## Result

**Order flow has a small, real-looking link to the next return, and it is far too small to trade.** 15 of 276 tests have q < 0.05, and 15 of those 15 point the same way: after buying, spot falls slightly. Flow does not predict continuation.

- **Strongest by p-value:** `corr M15 h1 all delta_ratio`, r -0.0137, z -4.92, q 0.00024, gain 0.041 pips a trade. It has the same sign in 2019, 2020 and 2021.
- **Largest gain with q < 0.05:** `corr H1 h2 asia cum_delta`, 0.485 pips a trade, so -0.515 after the 1.0 pip cost. **No significant result covers the cost.**
- **Gains above 1 pip:** 13 tests, all with q >= 0.40 and at most 303 trades. They are noise until shown otherwise.
- **Quintiles:** the pattern is monotonic in 1 of 24 cells (M15 h1 all). The Q5-Q1 gap there is -0.22 pips.
- **Absorption and divergence:** none of the 66 tests has q < 0.05 (lowest q 0.39). The one significant condition is the control, continuation, and it too reverses.
- **Sessions:** Asia and NY hold the significant results; London has none (lowest q 0.58). Asia is mostly session cumulative delta fading.
- **Flow vs spot's own return:** 0 of 4 leading results fall under |z| 2 once spot's past return is removed; see the table in that section.

Caveats: direction and quintile cut points were chosen in sample, so the gains are upper estimates. Spot bars are bid only. These tests are not in `reports/trials/trials.csv`, which logs strategy runs. Stronger filters on the same data were not tried and would add to the test count. Validation was not used.

## Method

- Signal from closed bar t; return = close(t+h) - open(t+1) of spot, in pips; h = (1, 2, 4). Bars t to t+h must be clean spot bars at exact spacing.
- Left out: `roll_flag`, `degraded_flag`, `pre_roll_thin`. `pre_roll_thin` is computed here, not stored in bars v1. It runs from 00:00 UTC of the last weekday before the roll to the roll, so it also holds the Sunday evening session on the old contract.
- delta z and volume spike use the 20 bars before t. Cumulative delta resets at each Asia, London, NY and other block of a UTC day.
- Large delta: |z| >= 2.0 with z and delta on one side. Absorption: |spot bar return| <= 0.25 of the trailing 20-bar mean |return|. Divergence and continuation: at least 0.5 of it, against or along the delta. Continuation is a control.
- Sessions: Asia 00-07, London 07-12, NY 12-21 UTC by bar start, as in the earlier exploratory run. Bars from 21 to 24 UTC count only in `all`.
- `spike_signed` = volume spike x sign of delta. It was added because volume alone has no direction.
- Errors are clustered by UTC day. edge_pips = |mean gain of the rule|, with the direction chosen in sample. net_model uses the cost model at bar t+1, p75.
- Quintile cut points use the whole train sample, so they are in sample.

## Sample

| timeframe | flow_bars | roll_flag | degraded_flag | pre_roll_thin | left_out | matched_clean_spot | with_delta_ratio_and_fwd_1 | absorption | divergence | continuation | thin_volume_ratio |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M15 | 70966 | 12 | 817 | 1087 | 1916 | 68586 | 65235 | 364 | 657 | 4748 | 0.177 |
| H1 | 17753 | 12 | 205 | 277 | 494 | 16424 | 15073 | 122 | 330 | 971 | 0.174 |

`thin_volume_ratio` = mean volume of a `pre_roll_thin` bar over a kept bar.

## Tests

**276 tests** in one BH correction; 15 have q < 0.05.

| family | tests | significant | min_q |
|---|---|---|---|
| condition | 102 | 1 | 0.0281 |
| corr | 120 | 9 | 2.40e-04 |
| quintile | 30 | 1 | 0.0015 |
| spread | 24 | 4 | 3.48e-04 |

## Strongest results

| test_id | n | estimate | z | p | q_bh | edge_pips | net_flat_pips | net_model_pips |
|---|---|---|---|---|---|---|---|---|
| corr M15 h1 all delta_ratio | 65235 | -0.0137 | -4.92 | 8.69e-07 | 2.40e-04 | 0.0411 | -0.959 | -0.975 |
| spread M15 h1 all Q5-Q1 | 25800 | -0.22 | -4.71 | 2.52e-06 | 3.48e-04 | 0.11 | -0.89 | -0.915 |
| corr M15 h1 ny delta_ratio | 25987 | -0.0199 | -4.17 | 3.06e-05 | 0.00211 | 0.0911 | -0.909 | -0.928 |
| corr M15 h1 asia cum_delta | 19455 | -0.0287 | -3.76 | 1.69e-04 | 0.00935 | 0.0333 | -0.967 | -0.967 |
| corr H1 h1 asia cum_delta | 4428 | -0.0785 | -3.57 | 3.58e-04 | 0.0147 | 0.232 | -0.768 | -0.768 |
| corr H1 h2 asia cum_delta | 4231 | -0.0879 | -3.56 | 3.73e-04 | 0.0147 | 0.485 | -0.515 | -0.515 |
| spread M15 h2 all Q5-Q1 | 25110 | -0.248 | -3.45 | 5.66e-04 | 0.018 | 0.124 | -0.876 | -0.898 |
| corr M15 h2 all delta_ratio | 64022 | -0.0107 | -3.41 | 6.40e-04 | 0.018 | 0.056 | -0.944 | -0.958 |
| spread M15 h1 ny Q5-Q1 | 10284 | -0.307 | -3.41 | 6.53e-04 | 0.018 | 0.153 | -0.847 | -0.879 |
| corr M15 h2 asia cum_delta | 19073 | -0.0389 | -3.31 | 9.23e-04 | 0.0227 | 0.0457 | -0.954 | -0.954 |

### By year (mean pips of the rule, in its in-sample direction)

| test_id | 2019 pips | 2019 n | 2020 pips | 2020 n | 2021 pips | 2021 n |
|---|---|---|---|---|---|---|
| corr M15 h1 all delta_ratio | 0.0328 | 22430 | 0.0392 | 22117 | 0.0522 | 20463 |
| spread M15 h1 all Q5-Q1 | 0.0744 | 9238 | 0.118 | 8352 | 0.142 | 8210 |
| corr M15 h1 ny delta_ratio | 0.0637 | 8815 | 0.129 | 8713 | 0.0805 | 8405 |
| corr M15 h1 asia cum_delta | 0.0363 | 6693 | 0.0114 | 6669 | 0.0539 | 6073 |
| corr H1 h1 asia cum_delta | 0.253 | 1632 | 0.121 | 1598 | 0.351 | 1190 |
| corr H1 h2 asia cum_delta | 0.524 | 1611 | 0.197 | 1562 | 0.856 | 1050 |
| condition M15 h2 all continuation both | 0.335 | 1555 | 0.426 | 1590 | 0.397 | 1523 |

## Flow vs spot's own past return (diagnostic, not in the test count)

Both the feature and the forward return are regressed on the control, then correlated. `ret` is spot's return in bar t; `cum_ret` is spot's return so far in the session.

| test | control | n | r_feature | z_feature | r_spot_control | z_spot_control | r_after_control | z_after_control |
|---|---|---|---|---|---|---|---|---|
| M15 h1 all delta_ratio | ret | 65235 | -0.014 | -4.919 | -0.023 | -3.424 | -0.006 | -2.114 |
| M15 h1 ny delta_ratio | ret | 25987 | -0.020 | -4.169 | -0.031 | -2.653 | -0.011 | -2.082 |
| M15 h1 asia cum_delta | cum_ret | 19455 | -0.029 | -3.761 | -0.019 | -1.714 | -0.022 | -2.604 |
| H1 h2 asia cum_delta | cum_ret | 4231 | -0.088 | -3.558 | -0.035 | -1.081 | -0.082 | -3.190 |

## delta_ratio quintiles, all sessions

| timeframe | horizon | Q1 pips | Q2 pips | Q3 pips | Q4 pips | Q5 pips | Q1 t | Q2 t | Q3 t | Q4 t | Q5 t |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H1 | 1 | 0.164 | -0.296 | 0.155 | -0.172 | -0.0739 | 0.962 | -1.5 | 0.793 | -0.928 | -0.485 |
| H1 | 2 | 0.33 | -0.385 | 0.0184 | -0.247 | 0.0934 | 1.17 | -1.16 | 0.0582 | -0.803 | 0.374 |
| H1 | 4 | 0.0795 | 0.0844 | -0.13 | -0.569 | 0.179 | 0.177 | 0.153 | -0.24 | -1.01 | 0.379 |
| M15 | 1 | 0.0738 | 0.00931 | -0.0183 | -0.0286 | -0.146 | 2.19 | 0.19 | -0.37 | -0.607 | -4.31 |
| M15 | 2 | 0.092 | 0.0189 | -0.0899 | -0.0128 | -0.156 | 1.71 | 0.243 | -1.14 | -0.172 | -2.77 |
| M15 | 4 | 0.104 | 0.0516 | -0.16 | -0.0332 | -0.154 | 1.08 | 0.415 | -1.15 | -0.277 | -1.65 |

Monotonic in all five steps: 1 of 24 timeframe, horizon and session cells. All cells are in `quintiles.csv`.

## Absorption, divergence, continuation (all sessions)

| test_id | n | estimate | z | p | q_bh | edge_pips | net_flat_pips |
|---|---|---|---|---|---|---|---|
| condition M15 h1 all absorption both | 359 | -0.0407 | -0.121 | 0.903 | 0.982 | 0.0407 | -0.959 |
| condition M15 h1 all absorption buy | 181 | 0.4 | 0.839 | 0.402 | 0.923 | 0.4 | -0.6 |
| condition M15 h1 all absorption sell | 178 | -0.489 | -0.901 | 0.368 | 0.923 | 0.489 | -0.511 |
| condition M15 h1 all divergence both | 654 | 0.223 | 0.77 | 0.441 | 0.923 | 0.223 | -0.777 |
| condition M15 h1 all divergence buy | 340 | 0.316 | 0.787 | 0.431 | 0.923 | 0.316 | -0.684 |
| condition M15 h1 all divergence sell | 314 | 0.122 | 0.298 | 0.765 | 0.982 | 0.122 | -0.878 |
| condition M15 h1 all continuation both | 4708 | -0.235 | -2.89 | 0.00383 | 0.0587 | 0.235 | -0.765 |
| condition M15 h1 all continuation buy | 2353 | -0.232 | -1.99 | 0.0468 | 0.362 | 0.232 | -0.768 |
| condition M15 h1 all continuation sell | 2355 | -0.239 | -2.01 | 0.0445 | 0.361 | 0.239 | -0.761 |
| condition M15 h2 all absorption both | 357 | -0.0689 | -0.147 | 0.883 | 0.982 | 0.0689 | -0.931 |
| condition M15 h2 all absorption buy | 181 | 0.511 | 0.684 | 0.494 | 0.975 | 0.511 | -0.489 |
| condition M15 h2 all absorption sell | 176 | -0.665 | -1.02 | 0.307 | 0.897 | 0.665 | -0.335 |
| condition M15 h2 all divergence both | 653 | -0.0841 | -0.209 | 0.834 | 0.982 | 0.0841 | -0.916 |
| condition M15 h2 all divergence buy | 340 | 0.235 | 0.417 | 0.676 | 0.982 | 0.235 | -0.765 |
| condition M15 h2 all divergence sell | 313 | -0.43 | -0.731 | 0.465 | 0.958 | 0.43 | -0.57 |
| condition M15 h2 all continuation both | 4668 | -0.386 | -3.19 | 0.00142 | 0.0281 | 0.386 | -0.614 |
| condition M15 h2 all continuation buy | 2337 | -0.415 | -2.31 | 0.0211 | 0.232 | 0.415 | -0.585 |
| condition M15 h2 all continuation sell | 2331 | -0.358 | -2.02 | 0.0434 | 0.361 | 0.358 | -0.642 |
| condition M15 h4 all absorption both | 355 | 0.305 | 0.52 | 0.603 | 0.982 | 0.305 | -0.695 |
| condition M15 h4 all absorption buy | 180 | 0.355 | 0.4 | 0.689 | 0.982 | 0.355 | -0.645 |
| condition M15 h4 all absorption sell | 175 | 0.254 | 0.29 | 0.772 | 0.982 | 0.254 | -0.746 |
| condition M15 h4 all divergence both | 649 | 0.382 | 0.644 | 0.52 | 0.975 | 0.382 | -0.618 |
| condition M15 h4 all divergence buy | 339 | 0.873 | 1.07 | 0.286 | 0.897 | 0.873 | -0.127 |
| condition M15 h4 all divergence sell | 310 | -0.155 | -0.18 | 0.857 | 0.982 | 0.155 | -0.845 |
| condition M15 h4 all continuation both | 4613 | -0.237 | -1.43 | 0.152 | 0.696 | 0.237 | -0.763 |
| condition M15 h4 all continuation buy | 2312 | -0.277 | -1.01 | 0.313 | 0.897 | 0.277 | -0.723 |
| condition M15 h4 all continuation sell | 2301 | -0.198 | -0.77 | 0.442 | 0.923 | 0.198 | -0.802 |
| condition H1 h1 all absorption both | 121 | -1.14 | -1.12 | 0.261 | 0.89 | 1.14 | 0.143 |
| condition H1 h1 all absorption buy | 53 | 0.206 | 0.13 | 0.896 | 0.982 | 0.206 | -0.794 |
| condition H1 h1 all absorption sell | 68 | -2.19 | -1.67 | 0.0952 | 0.584 | 2.19 | 1.19 |
| condition H1 h1 all divergence both | 326 | 0.639 | 0.893 | 0.372 | 0.923 | 0.639 | -0.361 |
| condition H1 h1 all divergence buy | 152 | 0.571 | 0.484 | 0.629 | 0.982 | 0.571 | -0.429 |
| condition H1 h1 all divergence sell | 174 | 0.698 | 0.799 | 0.424 | 0.923 | 0.698 | -0.302 |
| condition H1 h1 all continuation both | 954 | -0.161 | -0.414 | 0.679 | 0.982 | 0.161 | -0.839 |
| condition H1 h1 all continuation buy | 433 | -0.377 | -0.635 | 0.525 | 0.975 | 0.377 | -0.623 |
| condition H1 h1 all continuation sell | 521 | 0.0177 | 0.0337 | 0.973 | 0.987 | 0.0177 | -0.982 |
| condition H1 h2 all absorption both | 119 | -0.582 | -0.373 | 0.709 | 0.982 | 0.582 | -0.418 |
| condition H1 h2 all absorption buy | 52 | -0.946 | -0.548 | 0.584 | 0.982 | 0.946 | -0.0538 |
| condition H1 h2 all absorption sell | 67 | -0.299 | -0.122 | 0.903 | 0.982 | 0.299 | -0.701 |
| condition H1 h2 all divergence both | 323 | 0.122 | 0.125 | 0.9 | 0.982 | 0.122 | -0.878 |
| condition H1 h2 all divergence buy | 152 | -0.0743 | -0.0508 | 0.959 | 0.982 | 0.0743 | -0.926 |
| condition H1 h2 all divergence sell | 171 | 0.297 | 0.22 | 0.826 | 0.982 | 0.297 | -0.703 |
| condition H1 h2 all continuation both | 936 | 0.423 | 0.749 | 0.454 | 0.942 | 0.423 | -0.577 |
| condition H1 h2 all continuation buy | 421 | 0.519 | 0.618 | 0.536 | 0.982 | 0.519 | -0.481 |
| condition H1 h2 all continuation sell | 515 | 0.344 | 0.426 | 0.67 | 0.982 | 0.344 | -0.656 |
| condition H1 h4 all absorption both | 111 | -2.77 | -1.15 | 0.249 | 0.875 | 2.77 | 1.77 |
| condition H1 h4 all absorption buy | 49 | -5.28 | -1.44 | 0.149 | 0.696 | 5.28 | 4.28 |
| condition H1 h4 all absorption sell | 62 | -0.784 | -0.249 | 0.804 | 0.982 | 0.784 | -0.216 |
| condition H1 h4 all divergence both | 303 | 1.29 | 0.913 | 0.361 | 0.923 | 1.29 | 0.289 |
| condition H1 h4 all divergence buy | 142 | 1.88 | 0.944 | 0.345 | 0.916 | 1.88 | 0.875 |
| condition H1 h4 all divergence sell | 161 | 0.773 | 0.372 | 0.71 | 0.982 | 0.773 | -0.227 |
| condition H1 h4 all continuation both | 881 | 0.677 | 0.843 | 0.399 | 0.923 | 0.677 | -0.323 |
| condition H1 h4 all continuation buy | 397 | 0.974 | 0.788 | 0.431 | 0.923 | 0.974 | -0.0264 |
| condition H1 h4 all continuation sell | 484 | 0.434 | 0.384 | 0.701 | 0.982 | 0.434 | -0.566 |

## By session

| session | family | tests | significant | min_q | max_edge_pips |
|---|---|---|---|---|---|
| asia | condition | 12 | 0 | 0.389 | 1.86 |
| asia | corr | 30 | 6 | 0.00935 | 0.814 |
| asia | spread | 6 | 1 | 0.0261 | 0.485 |
| london | condition | 18 | 0 | 0.665 | 6.91 |
| london | corr | 30 | 0 | 0.647 | 0.484 |
| london | spread | 6 | 0 | 0.58 | 0.24 |
| ny | condition | 18 | 0 | 0.056 | 2.45 |
| ny | corr | 30 | 1 | 0.00211 | 0.316 |
| ny | spread | 6 | 1 | 0.018 | 0.409 |

## All tests with q < 0.05

| test_id | n | estimate | z | p | q_bh | edge_pips | net_flat_pips | net_model_pips |
|---|---|---|---|---|---|---|---|---|
| corr M15 h1 all delta_ratio | 65235 | -0.0137 | -4.92 | 8.69e-07 | 2.40e-04 | 0.0411 | -0.959 | -0.975 |
| spread M15 h1 all Q5-Q1 | 25800 | -0.22 | -4.71 | 2.52e-06 | 3.48e-04 | 0.11 | -0.89 | -0.915 |
| quintile M15 h1 all Q5 | 12899 | -0.146 | -4.31 | 1.63e-05 | 0.0015 | – | – | – |
| corr M15 h1 ny delta_ratio | 25987 | -0.0199 | -4.17 | 3.06e-05 | 0.00211 | 0.0911 | -0.909 | -0.928 |
| corr M15 h1 asia cum_delta | 19455 | -0.0287 | -3.76 | 1.69e-04 | 0.00935 | 0.0333 | -0.967 | -0.967 |
| corr H1 h1 asia cum_delta | 4428 | -0.0785 | -3.57 | 3.58e-04 | 0.0147 | 0.232 | -0.768 | -0.768 |
| corr H1 h2 asia cum_delta | 4231 | -0.0879 | -3.56 | 3.73e-04 | 0.0147 | 0.485 | -0.515 | -0.515 |
| corr M15 h2 all delta_ratio | 64022 | -0.0107 | -3.41 | 6.40e-04 | 0.018 | 0.056 | -0.944 | -0.958 |
| spread M15 h2 all Q5-Q1 | 25110 | -0.248 | -3.45 | 5.66e-04 | 0.018 | 0.124 | -0.876 | -0.898 |
| spread M15 h1 ny Q5-Q1 | 10284 | -0.307 | -3.41 | 6.53e-04 | 0.018 | 0.153 | -0.847 | -0.879 |
| corr M15 h2 asia cum_delta | 19073 | -0.0389 | -3.31 | 9.23e-04 | 0.0227 | 0.0457 | -0.954 | -0.954 |
| corr M15 h4 asia cum_delta | 18486 | -0.0621 | -3.29 | 9.87e-04 | 0.0227 | 0.143 | -0.857 | -0.857 |
| spread M15 h1 asia Q5-Q1 | 7845 | -0.222 | -3.23 | 0.00123 | 0.0261 | 0.111 | -0.889 | -0.889 |
| condition M15 h2 all continuation both | 4668 | -0.386 | -3.19 | 0.00142 | 0.0281 | 0.386 | -0.614 | -0.619 |
| corr M15 h1 asia delta_ratio | 19741 | -0.0177 | -3 | 0.00271 | 0.0498 | 0.0312 | -0.969 | -0.969 |

