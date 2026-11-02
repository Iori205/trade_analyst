# Strategy: Sweep + MSS v1 (M15), train 2015-2021

Generated 2026-11-02T09:12:34Z by `src/strategies/sweep_mss.py` (HEAD `648a8c7`, uncommitted script changes: true). Data: M15 train bars, SHA-256 `6090cb8014ada01c…`. Validation and test were not read.

## Rules (frozen before running; not changed after seeing results)

- **Trend:** H4 bars built from M15. Long only when the last closed H4 close is above EMA50, short only when it is below.
- **Asia range:** the day's 00:00-07:00 UTC high and low.
- **Sweep:** an M15 bar starting 12:00-17:00 UTC.
  - Long: the low goes below the Asia low and the bar closes back above it.
  - Short: the high goes above the Asia high and the bar closes back below it.
- **MSS:** within the next 8 M15 bars, a close beyond the last swing before the sweep: above the swing high for a long, below the swing low for a short. A swing is a 2-bar fractal.
- **Entry:** open of the bar after the MSS bar. At most 1 trade per day.
- **Exit:** after 4 h or at 20:45 UTC, whichever comes first. No stop, no target.

Where the rules are silent, I made these choices before running (also in the module docstring):

- **EMA50:** standard EMA seeded with the first H4 close. The trend counts only after 50 closed H4 bars.
- **Sweep window:** a bar start in [12:00, 17:00) UTC.
- **Side:** taken from the trend at the sweep bar.
- **Swing:** the latest fractal confirmed no later than the sweep bar.
- **Repeated sweeps:** a newer sweep on the same day replaces an armed one.
- **Daily limit:** a signal uses up the day's one trade even if the engine then skips the entry.

Engine (`src/backtest/engine.py`): next-bar-open fills. Entries are skipped on `any_gap`/`any_flag` bars, after gaps, and in rollover or weekly-open times. Cost = `cost_for(entry_time)` at p75 + 0.6 commission + 0.2 slippage. Prices are HistData bid. One field was added to the engine, `exit_clock_utc`, for the 20:45 exit. Earlier baseline results are unchanged; this was checked.

## Signal funnel

- **Days:** 1,806 days with a defined trend and bars in the 12:00-18:45 UTC window.
- **Sweeps:** 1,352 on the trend side; 0 of them had no prior swing.
- **MSS:** 368 signals.
- **Trades:** 366. 2 entries were skipped by the engine (flagged entry bar, gap, or rollover).

## Results (after costs, pips)

| metric | all | long | short |
|---|---|---|---|
| trades | 366 | 183 | 183 |
| win_rate | 0.429 | 0.432 | 0.426 |
| avg_win_pips | 20.598 | 22.100 | 19.077 |
| avg_loss_pips | -19.361 | -18.357 | -20.355 |
| expectancy_pips | -2.220 | -0.892 | -3.548 |
| total_pips | -812 | -163 | -649 |
| max_drawdown_pips | 1,345 | 577 | 909 |
| sharpe_daily | -0.520 | -0.148 | -0.586 |
| t_stat | -1.402 | -0.398 | -1.585 |
| mean_cost_pips | 1.000 | 1.000 | 1.000 |

- **Exit reasons:** time 366.
- **Holding time:** median 16 M15 bars.
- **Before costs:** mean gross -1.220 pips per trade.
- **Largest single trade:** +210.8 pips (short, 2015-01-22, the day the ECB announced QE). Expectancy without it: -2.804 pips.

## By year

| year | trades | net_pips | expectancy_pips | win_rate |
|---|---|---|---|---|
| 2015 | 55 | 304 | 5.522 | 0.455 |
| 2016 | 63 | -171 | -2.708 | 0.413 |
| 2017 | 53 | -171 | -3.221 | 0.396 |
| 2018 | 37 | -245 | -6.619 | 0.432 |
| 2019 | 53 | -13.700 | -0.258 | 0.491 |
| 2020 | 50 | -46.000 | -0.920 | 0.500 |
| 2021 | 55 | -470 | -8.551 | 0.327 |

Net pips by year and side:

| year | long | short |
|---|---|---|
| 2015 | 178 | 126 |
| 2016 | 21.400 | -192 |
| 2017 | -155 | -15.400 |
| 2018 | -34.800 | -210 |
| 2019 | -21.900 | 8.200 |
| 2020 | 38.400 | -84.400 |
| 2021 | -189 | -282 |

## Against random baselines

There are two matched baselines with 100 seeded runs each. Both use the same M15 data, the same signal window (signal bar 12:00-18:45 UTC), at most 1 trade per day, the same trend warm-up, the same exits and the same engine rules. The per-bar entry probability is set so the number of trades is close to the strategy's.

- **random side:** random direction.
- **random, trend side:** direction = H4 trend. This shows what sweep + MSS adds on top of the trend filter.

| baseline | runs | median trades | expectancy p5 | expectancy median | expectancy p95 | runs below sweep+MSS |
|---|---|---|---|---|---|---|
| random side | 100 | 364 | -2.871 | -1.030 | 0.958 | 19 |
| random, trend side | 100 | 364 | -4.058 | -1.934 | 0.356 | 40 |

For reference, the H1 random baseline (`reports/backtest_baselines_20261102T085428Z`) had a median expectancy of -0.846 pips.

Charts: `charts/random_comparison.png` and `charts/equity.png`. Trade list (pips only): `trades.csv`. Every random run is in `random_side.csv` and `random_trend.csv`.

## How to read this

- **Rules:** the parameters were fixed in the prompt before any run and were not changed. This is the strategy's only logged train run. Two earlier runs, with logging off, checked only runtime and trade counts; no performance numbers were looked at.
- **Trial log:** 201 rows were added to `reports/trials/trials.csv` (1 strategy + 200 random), for a total of 303 rows.
- **Verdict on train:** expectancy is negative, and only part of the random distributions is below it. Sweep + MSS adds no measurable edge over random entries or over the trend filter alone. Spending validation 2022-2023 on this frozen v1 is not recommended; the validation data is better kept for candidates that clear the random baseline on train.
- **Limitations:** the cost is charged at entry only; there is no stop, so the risk on a single trade is open-ended; and prices are bid only.
