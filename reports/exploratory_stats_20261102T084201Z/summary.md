# Exploratory statistics: EURUSD train split (2015-2021)

Generated 2026-11-02T08:42:04Z by `src/research/exploratory_stats.py` (HEAD `15b1f14`, uncommitted script changes: true).

- **Data:** TRAIN split only. Validation and test were not read: bars came through the guarded `read_bars(..., "train")`, and their range was checked.
- **Bars used:** M15 167,805 of 174,125, H1 39,885 of 43,534. Bars with `any_gap` or `any_flag` were dropped.
- **Return:** close - open of a bar, in pips, from HistData **bid** prices.
- **Cost:** `cost_for` at p75, i.e. FXCM spread + 0.6 commission + 0.2 slippage. These are broker assumptions.
- **Tests:** 321 in total (autocorr 64, big_moves 6, hour_weekday 240, month_end 3, sessions 8). One Benjamini-Hochberg correction covers all of them, at q < 0.05.

Ratios:

- **move/cost** = median |relevant return| / median cost. This is the ratio the task asked for. It measures how far price moves, not whether the direction can be predicted. On H1 almost every cell is above 2, so this criterion alone filters very little.
- **edge/cost** = |expected gain of the simple rule the finding implies| / cost. For example: the mean return for an hour cell; the mean of sign(previous) × next for an autocorrelation or a session pair; the mean forward return after a big move. This stricter ratio is shown alongside.

## a) Significant after FDR

| test_id | n | estimate | unit | p | q_bh | move_pips | edge_pips | cost_pips | move_cost | edge_cost | near_rollover_hour |
|---|---|---|---|---|---|---|---|---|---|---|---|
| p_up Wed 22 | 238 | 0.693 | probability | 2.47e-09 | 7.93e-07 | 3.3 | 1.42 | 1.2 | 2.75 | 1.18 | yes |
| M15 lag1 all | 164189 | -0.0263 | rho | 1.38e-05 | 0.00221 | 2.5 | 0.127 | 1 | 2.5 | 0.127 | no |
| mean Wed 22 | 239 | 1.42 | pips | 5.27e-05 | 0.00423 | 3.3 | 1.42 | 1.2 | 2.75 | 1.18 | yes |
| abs move month-end vs other | 82 | 8.05 | pips | 5.00e-05 | 0.00423 | 19.8 | – | 1 | 19.8 | – | no |
| p_up Mon 22 | 196 | 0.638 | probability | 1.15e-04 | 0.00635 | 2.4 | 0.992 | 1.2 | 2 | 0.827 | yes |
| p_up Fri 21 | 108 | 0.315 | probability | 1.19e-04 | 0.00635 | 4.55 | 2.53 | 1 | 4.55 | 2.53 | yes |
| p_up Tue 02 | 334 | 0.599 | probability | 3.05e-04 | 0.014 | 3.7 | 1.16 | 1 | 3.7 | 1.16 | no |
| mean Fri 21 | 108 | -2.53 | pips | 3.63e-04 | 0.0146 | 4.55 | 2.53 | 1 | 4.55 | 2.53 | yes |
| mean Mon 13 | 360 | 2.69 | pips | 4.70e-04 | 0.0167 | 8.2 | 2.69 | 1 | 8.2 | 2.69 | no |
| p_up Tue 22 | 197 | 0.619 | probability | 8.12e-04 | 0.0261 | 2.55 | 1.16 | 1.1 | 2.32 | 1.05 | yes |
| p_up Thu 22 | 221 | 0.611 | probability | 9.80e-04 | 0.0286 | 2.8 | 0.777 | 1.1 | 2.55 | 0.707 | yes |
| M15 lag1 ny | 64247 | -0.0303 | rho | 0.0011 | 0.0293 | 3 | 0.148 | 1 | 3 | 0.148 | no |
| p_up Fri 19 | 339 | 0.587 | probability | 0.00135 | 0.0334 | 4 | 1.3 | 1 | 4 | 1.3 | no |

## b) move/cost > 2 (305 of 321 tests)

Count per family: autocorr 56/64, big_moves 6/6, hour_weekday 232/240, month_end 3/3, sessions 8/8.
Only 8 tests have edge/cost > 2: mean Mon 13, p_up Mon 13, mean Fri 21, p_up Fri 21, after up +24h, after down +24h, signed month-end vs 0, signed month-end vs other.

## c) In both a) and b): the most interesting

| test_id | n | estimate | unit | p | q_bh | move_pips | edge_pips | cost_pips | move_cost | edge_cost | near_rollover_hour |
|---|---|---|---|---|---|---|---|---|---|---|---|
| p_up Wed 22 | 238 | 0.693 | probability | 2.47e-09 | 7.93e-07 | 3.3 | 1.42 | 1.2 | 2.75 | 1.18 | yes |
| M15 lag1 all | 164189 | -0.0263 | rho | 1.38e-05 | 0.00221 | 2.5 | 0.127 | 1 | 2.5 | 0.127 | no |
| mean Wed 22 | 239 | 1.42 | pips | 5.27e-05 | 0.00423 | 3.3 | 1.42 | 1.2 | 2.75 | 1.18 | yes |
| abs move month-end vs other | 82 | 8.05 | pips | 5.00e-05 | 0.00423 | 19.8 | – | 1 | 19.8 | – | no |
| p_up Fri 21 | 108 | 0.315 | probability | 1.19e-04 | 0.00635 | 4.55 | 2.53 | 1 | 4.55 | 2.53 | yes |
| p_up Tue 02 | 334 | 0.599 | probability | 3.05e-04 | 0.014 | 3.7 | 1.16 | 1 | 3.7 | 1.16 | no |
| mean Fri 21 | 108 | -2.53 | pips | 3.63e-04 | 0.0146 | 4.55 | 2.53 | 1 | 4.55 | 2.53 | yes |
| mean Mon 13 | 360 | 2.69 | pips | 4.70e-04 | 0.0167 | 8.2 | 2.69 | 1 | 8.2 | 2.69 | no |
| p_up Tue 22 | 197 | 0.619 | probability | 8.12e-04 | 0.0261 | 2.55 | 1.16 | 1.1 | 2.32 | 1.05 | yes |
| p_up Thu 22 | 221 | 0.611 | probability | 9.80e-04 | 0.0286 | 2.8 | 0.777 | 1.1 | 2.55 | 0.707 | yes |
| M15 lag1 ny | 64247 | -0.0303 | rho | 0.0011 | 0.0293 | 3 | 0.148 | 1 | 3 | 0.148 | no |
| p_up Fri 19 | 339 | 0.587 | probability | 0.00135 | 0.0334 | 4 | 1.3 | 1 | 4 | 1.3 | no |

Significant **and** edge/cost > 2 (stricter): 3. p_up Fri 21, mean Fri 21, mean Mon 13.

### How to read these

- **Hours next to rollover (20-22 UTC) and Friday 21 UTC:** these are bid prices. HistData has no ask, but the FXCM reference weeks (`bid_mid_check.csv`) show the effect.
  - Around rollover the spread first widens, then narrows. When it narrows (22 UTC) the bid rises faster than the mid; when it widens (Friday before the close) the bid falls faster.
  - So part of the significant mean return in these cells is spread, not price.
  - These cells also lose many bars to `any_gap` or `any_flag`. The bars that survive are the cleaner hours, which is a selection effect.
- **Month-end |move|:** volatility in the London 15:00-17:00 (4pm fix) window is much higher on the last weekday of the month. This is a size effect, not a direction. The signed tests tell whether a direction exists.
- **Autocorrelation:** the significant coefficients are small. On M15, lag 1 is about -0.03, with edge/cost well below 1. Statistically real but economically small, and possibly bid-ask bounce or microstructure.
- **Generalisation:** every finding is from 2015-2021 only. Validation (2022-2023) should check them before anything is built on them. Nothing was tested on test data.

## Bid vs mid around rollover (FXCM reference weeks, pips per H1 bar)

| days | hour_utc | n | bid_ret | mid_ret | bid_minus_mid | spread_change |
|---|---|---|---|---|---|---|
| all weekdays | 20 | 50 | -2.84 | -2.4 | -0.45 | 0.89 |
| all weekdays | 21 | 50 | 0.33 | 0.34 | -0.01 | 0.01 |
| all weekdays | 22 | 50 | 1.84 | 1.24 | 0.6 | -1.2 |
| all weekdays | 23 | 50 | 1.18 | 1.1 | 0.08 | -0.16 |
| Friday | 20 | 10 | -2.62 | -1.88 | -0.74 | 1.48 |
| Friday | 21 | 2 | -3.4 | -2.6 | -0.8 | 1.6 |

## 1. Hour × weekday (H1)

Full table: `hour_weekday.csv`. Charts: `charts/hour_weekday_mean.png` and `charts/hour_weekday_move_cost.png`.

| weekday_name | hour_utc | n | mean_pips | p_up | std_pips | median_abs_pips | cost_pips | move_cost | edge_cost | p_mean | p_up_test |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Wed | 22 | 239 | 1.42 | 0.693 | 5.42 | 3.3 | 1.2 | 2.75 | 1.18 | 5.27e-05 | 2.47e-09 |
| Fri | 21 | 108 | -2.53 | 0.315 | 7.37 | 4.55 | 1 | 4.55 | 2.53 | 3.63e-04 | 1.19e-04 |
| Mon | 13 | 360 | 2.69 | 0.569 | 14.6 | 8.2 | 1 | 8.2 | 2.69 | 4.70e-04 | 0.00841 |
| Fri | 11 | 360 | -1.77 | 0.442 | 11 | 6.2 | 1 | 6.2 | 1.77 | 0.00225 | 0.0269 |
| Tue | 2 | 337 | 1.16 | 0.599 | 7.16 | 3.7 | 1 | 3.7 | 1.16 | 0.00301 | 3.05e-04 |
| Tue | 22 | 202 | 1.16 | 0.619 | 5.6 | 2.55 | 1.1 | 2.32 | 1.05 | 0.00327 | 8.12e-04 |
| Mon | 22 | 197 | 0.992 | 0.638 | 5.03 | 2.4 | 1.2 | 2 | 0.827 | 0.00565 | 1.15e-04 |
| Mon | 1 | 319 | 1.28 | 0.57 | 8.4 | 4.8 | 1 | 4.8 | 1.28 | 0.00649 | 0.0133 |
| Mon | 5 | 322 | 1.05 | 0.55 | 7.3 | 3.7 | 1 | 3.7 | 1.05 | 0.0101 | 0.0736 |
| Mon | 20 | 306 | -0.962 | 0.423 | 6.59 | 3.4 | 1 | 3.4 | 0.962 | 0.0106 | 0.00712 |

## 2. Autocorrelation (lag 1-8)

Full table: `autocorr.csv`. Chart: `charts/autocorr.png`. Rows with p < 0.05 before correction:

| timeframe | lag | session | n | rho | p | edge_pips | cost_pips |
|---|---|---|---|---|---|---|---|
| M15 | 1 | all | 164189 | -0.0263 | 1.38e-05 | -0.127 | 1 |
| M15 | 1 | asia | 47944 | -0.0338 | 0.0218 | -0.139 | 1 |
| M15 | 1 | ny | 64247 | -0.0303 | 0.0011 | -0.148 | 1 |

## 3. After big moves (H1, |return| > p95 = 23.5 pips)

Chart: `charts/big_moves.png`. Standard errors are clustered by day.

| horizon_h | direction | n | clusters | mean_fwd_pips | continuation_pips | p | p_continue | median_abs_fwd_pips | cost_pips |
|---|---|---|---|---|---|---|---|---|---|
| 1 | up | 972 | 641 | 0.0142 | 0.0142 | 0.984 | 0.483 | 10.3 | 1 |
| 1 | down | 1001 | 650 | -0.729 | 0.729 | 0.214 | 0.5 | 10.4 | 1 |
| 4 | up | 926 | 622 | -0.825 | -0.825 | 0.553 | 0.47 | 19.1 | 1 |
| 4 | down | 963 | 636 | -1.08 | 1.08 | 0.451 | 0.52 | 18.7 | 1 |
| 24 | up | 775 | 506 | -4.52 | -4.52 | 0.235 | 0.494 | 45.6 | 1 |
| 24 | down | 758 | 503 | -7.57 | 7.57 | 0.0462 | 0.533 | 39.3 | 1 |

## 4. Sessions (Asia 00-07, London 07-12, NY 12-21 UTC)

Chart: `charts/sessions.png`. A session counts only if all of its H1 bars are clean.

| pair | n | corr | se | p_corr | p_same_sign | p_sign_test | edge_pips | median_abs_next_pips | cost_pips |
|---|---|---|---|---|---|---|---|---|---|
| asia->london | 1210 | -0.0694 | 0.0427 | 0.104 | 0.498 | 0.885 | -0.472 | 17.9 | 1 |
| london->ny | 1508 | 0.0098 | 0.0299 | 0.743 | 0.504 | 0.757 | -0.0351 | 22.4 | 1 |
| asia->ny | 1095 | -0.00753 | 0.0478 | 0.875 | 0.507 | 0.627 | 0.614 | 22.6 | 1 |
| ny->next asia | 1517 | -0.0327 | 0.026 | 0.21 | 0.492 | 0.536 | -0.123 | 10.7 | 1 |

## 5. Month-end London 4pm fix (London 15:00-17:00 local, converted to UTC with London DST)

Chart: `charts/month_end.png`. Permutation tests use 20,000 permutations with a fixed seed.

| group | n | mean_abs_pips | median_abs_pips | mean_pips | std_pips | p_up |
|---|---|---|---|---|---|---|
| month_end | 82 | 23.3 | 19.8 | -4.28 | 30.9 | 0.451 |
| other_weekdays | 1721 | 15.3 | 11.5 | -0.0548 | 21.1 | 0.487 |

| test_id | n | estimate | p | q_bh | move_cost | edge_cost |
|---|---|---|---|---|---|---|
| abs move month-end vs other | 82 | 8.05 | 5.00e-05 | 0.00423 | 19.8 | – |
| signed month-end vs 0 | 82 | -4.28 | 0.212 | 0.625 | 19.8 | 4.28 |
| signed month-end vs other | 82 | -4.22 | 0.0818 | 0.486 | 19.8 | 4.28 |

## Method notes

- **Means and P(up):** normal approximation. Every cell has at least 30 bars.
- **Correlations:** a heteroskedasticity-robust z, sum(xy) / sqrt(sum(x²y²)).
- **Forward returns:** day-clustered standard errors, because the windows of triggers on the same day overlap.
- **Big-move forward returns:** these use the close of the bar k hours later. The bars in between are not required to be clean.
- **Cost:** for a cell or test, the median `cost_for` at the trade's entry time.
- **Sunday bars:** these have their own column in the hour × weekday table. Sessions and month-end use Mon-Fri only.
- **Charts:** `charts/pvalues.png` shows all p-values against the BH line.
