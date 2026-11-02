# Backtest baselines (engine v1), train split 2015-2021

Generated 2026-11-02T08:54:40Z by `src/backtest/baselines.py` (HEAD `0bc8fda`, uncommitted script changes: true). Data: `data/processed/eurusd_bars/v1/eurusd_h1_train.parquet` (SHA-256 `b7035d03eb13b589…`). Only the train split was read.

## Engine rules

- **Timing:** a signal sees bars up to and including the bar that just closed. Fills happen at the **next bar's open**.
- **Position:** one at a time, 1 lot, long or short. Exit is by a time limit or by the signal.
- **Entries are skipped when the entry bar:**
  - is not directly after the signal bar (weekend or data gap),
  - has `any_gap` or `any_flag`,
  - or `cost_for` marks it as rollover, weekly open or market closed.
- **Exits:** never blocked.
- **Cost:** `cost_for(entry_time)` once per round trip, spread at p75 + 0.6 commission + 0.2 slippage. The commission and slippage are broker assumptions.
- **Prices:** HistData bid; P&L in pips, 1 lot ≈ 10 USD per pip.
- **Trial log:** every run is appended to `reports/trials/trials.csv`. This report added 102 rows (100 random + 2).

## Results (after costs)

| metric | random (median of 100) | ma_crossover | monday_13_long |
|---|---|---|---|
| trades | 2,067 | 962 | 360 |
| win_rate | 0.471 | 0.379 | 0.536 |
| avg_win_pips | 16.007 | 63.815 | 11.133 |
| avg_loss_pips | -15.824 | -40.113 | -9.286 |
| expectancy_pips | -0.846 | -0.681 | 1.661 |
| total_pips | -1,744 | -655 | 598 |
| max_drawdown_pips | 2,481 | 4,429 | 172 |
| sharpe_daily | -0.579 | -0.109 | 0.801 |
| t_stat | -1.568 | -0.286 | 2.165 |
| mean_cost_pips | 1.006 | 1.011 | 1.000 |

## a) Random baseline

- **Setup:** 100 runs, seeds 20261102..20261201, entry probability 0.0625 per flat H1 bar, hold 4 h.
- **Activity:** about 1.13 trades per weekday.
- **Expectancy distribution:** p5 -1.666, median -0.846, p95 -0.146 pips per trade.
- **Cost:** mean cost 1.006 pips. Mean gross per trade 0.147 pips, i.e. about 0, as it should be.
- **Conclusion:** random entries lose roughly the cost on every trade. Any strategy has to clear this distribution, not zero.

Chart: `charts/random_expectancy.png`. Every run is in `random_runs.csv`.

## b) MA crossover 20/50 (H1)

Always in the market and reverses on a cross. When the entry bar is blocked, the strategy waits flat for the next allowed bar. Best year 2020: 1,631 pips. Total without that year: -2,286 pips.

Expectancy -0.681 pips per trade, t = -0.29. Higher than 62 of the 100 random runs.

By year (exit year):

| year | trades | net_pips | expectancy_pips | win_rate |
|---|---|---|---|---|
| 2015 | 132 | 1,084 | 8.213 | 0.432 |
| 2016 | 139 | -2,454 | -17.656 | 0.317 |
| 2017 | 140 | -1,242 | -8.872 | 0.343 |
| 2018 | 137 | 325 | 2.375 | 0.387 |
| 2019 | 147 | -155 | -1.055 | 0.381 |
| 2020 | 119 | 1,631 | 13.705 | 0.395 |
| 2021 | 148 | 156 | 1.051 | 0.405 |

Exit reasons: signal 961, end_of_data 1.

## c) Monday 13:00 UTC long, exit 14:00

**Not truly pre-registered:** it comes from the exploratory analysis of the same train data (mean Mon 13 +2.7 pips, q = 0.017). The train result below is therefore in-sample and biased upward by selection. Validation 2022-2023 is the real test, and it should be run once with these parameters fixed. Best year 2015: 415 pips, 69% of the 598 total. Total without that year: 183 pips.

Expectancy 1.661 pips per trade, t = 2.17. Higher than 100 of the 100 random runs.

By year (exit year):

| year | trades | net_pips | expectancy_pips | win_rate |
|---|---|---|---|---|
| 2015 | 52 | 415 | 7.973 | 0.673 |
| 2016 | 51 | -32.600 | -0.639 | 0.471 |
| 2017 | 51 | 5.900 | 0.116 | 0.490 |
| 2018 | 52 | -41.200 | -0.792 | 0.500 |
| 2019 | 52 | 1.500 | 0.029 | 0.500 |
| 2020 | 51 | 113 | 2.206 | 0.529 |
| 2021 | 51 | 137 | 2.688 | 0.588 |

Exit reasons: time 360.

Equity curves: `charts/equity.png`. Trade lists, with pips only and no price levels: `trades_ma_crossover.csv` and `trades_monday_13_long.csv`.

## Limitations

- **Cost model:** the spread is FXCM's, from 10 sample weeks. Commission and slippage are assumptions.
- **Exit cost:** cost is charged at entry only. An exit in a wide-spread period (e.g. rollover) costs more in reality.
- **Prices:** bid prices only. A short's exit in reality is at the ask; the round-trip spread in the cost stands in for that.
- **Execution:** fills are exact at the bar open, with no partial fills and no swap or financing charges.
- **Trial count:** 102 rows are now in the trial log. Any later selection among strategies must account for every trial in it.
