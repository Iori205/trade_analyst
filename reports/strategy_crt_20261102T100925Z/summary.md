# Strategy: CRT (Candle Range Theory) v1, train 2015-2021

Generated 2026-11-02T10:09:26Z by `src/strategies/crt.py` (HEAD `b558094`, uncommitted script changes: false). Data: M15 and M1 from the train split only (M15 SHA-256 `6090cb8014ada01c…`). Validation and test were not read.

## Rules (frozen before running)

- **H4 blocks:** UTC 00/04/08/12/16/20, built from M15. C1 is the range candle; C2 is the next block.
  - Short: high2 > high1 and low1 < close2 < high1.
  - Long: low2 < low1 and low1 < close2 < high1.
  - If both sides are swept, skip.
- **Entry:** C3 open. SL = high2 (short) / low2 (long), with no buffer.
- **TP:** v1a = C1 midpoint; v1b = the opposite side of C1.
- **Exit:** at most 12 h. The M1 path decides which barrier is hit first; if both are hit in the same minute, it counts as SL.
- **No entry** in rollover, weekly-open or closed periods, or on a flagged bar.

Where the rules are silent, I fixed these choices before running:

- C1, C2 and C3 must be consecutive blocks.
- C3 open = the M15 bar that starts exactly at the block start.
- The entry price must lie strictly between SL and TP; otherwise the setup is skipped.
- An M1 gap over 30 minutes inside the window (weekend or holiday) closes the trade at the last close before the gap.
- One position at a time.
- Cost = `cost_for(entry)` at p75 + 0.6 commission + 0.2 slippage, once per trade.

## Setup funnel

| variant | setups | entry_bar_missing_or_flagged | blocked_rollover_weekly_open_closed | bad_geometry | eligible | trades |
|---|---|---|---|---|---|---|
| v1a | 3040 | 148 | 0 | 545 | 2347 | 2250 |
| v1b | 3040 | 148 | 0 | 0 | 2892 | 2485 |

Setups by side: short 1,550, long 1,490. Skipped because both sides were swept: 607.

## Results (after costs, pips)

| metric | v1a | v1b |
|---|---|---|
| trades | 2,250 | 2,485 |
| win_rate | 0.540 | 0.462 |
| avg_win_pips | 6.852 | 13.842 |
| avg_loss_pips | -10.832 | -13.639 |
| expectancy_pips | -1.291 | -0.944 |
| total_pips | -2,904 | -2,345 |
| max_drawdown_pips | 2,967 | 2,475 |
| sharpe_daily | -1.901 | -0.974 |
| t_stat | -5.224 | -2.707 |
| mean_cost_pips | 1.004 | 1.004 |
| one-sided p | 1.000 | 0.997 |
| control median | -1.172 | -1.091 |
| control p95 | -0.808 | -0.580 |
| control runs below | 298 | 663 |

## Long and short

**v1a**

| side | trades | win_rate | avg_win_pips | avg_loss_pips | expectancy_pips | total_pips | t_stat |
|---|---|---|---|---|---|---|---|
| long | 1104 | 0.550 | 6.944 | -10.200 | -0.774 | -854.050 | -2.239 |
| short | 1146 | 0.530 | 6.760 | -11.416 | -1.788 | -2,050 | -5.077 |

**v1b**

| side | trades | win_rate | avg_win_pips | avg_loss_pips | expectancy_pips | total_pips | t_stat |
|---|---|---|---|---|---|---|---|
| long | 1217 | 0.471 | 13.703 | -12.957 | -0.404 | -492.100 | -0.848 |
| short | 1268 | 0.453 | 13.979 | -14.273 | -1.461 | -1,853 | -2.882 |

## By year

**v1a**

| year | trades | net_pips | expectancy_pips | win_rate |
|---|---|---|---|---|
| 2015 | 315 | -724.050 | -2.299 | 0.552 |
| 2016 | 336 | -622.650 | -1.853 | 0.506 |
| 2017 | 317 | -351.000 | -1.107 | 0.549 |
| 2018 | 317 | -478.150 | -1.508 | 0.546 |
| 2019 | 325 | -278.300 | -0.856 | 0.535 |
| 2020 | 326 | -218.800 | -0.671 | 0.558 |
| 2021 | 314 | -230.700 | -0.735 | 0.532 |

**v1b**

| year | trades | net_pips | expectancy_pips | win_rate |
|---|---|---|---|---|
| 2015 | 350 | -557.100 | -1.592 | 0.477 |
| 2016 | 375 | -500.400 | -1.334 | 0.435 |
| 2017 | 358 | -178.500 | -0.499 | 0.475 |
| 2018 | 334 | -409.300 | -1.225 | 0.449 |
| 2019 | 354 | -115.400 | -0.326 | 0.455 |
| 2020 | 373 | -363.400 | -0.974 | 0.501 |
| 2021 | 341 | -220.800 | -0.648 | 0.440 |

## Outcomes and distances

- **v1a:** tp 1248, sl 845, time 79, gap_exit 78. Median TP distance 7.4 pips, median SL distance 11.9 pips.
- **v1b:** sl 1139, tp 889, time 336, gap_exit 121. Median TP distance 18.7 pips, median SL distance 14.2 pips.

## Control

- **Setup:** 1000 runs (seed 20261106). Same entry times, same TP and SL distances in pips, random direction for each trade.
- **What it measures:** whether CRT's choice of direction beats a coin flip with the same trade geometry and the same costs.
- **Overlap:** control trades may overlap, because their exits differ from the strategy's.

Charts: `charts/control.png` and `charts/equity.png`. Trades (pips only, no price levels): `trades_v1a.csv` and `trades_v1b.csv`.

## Verdict

- **v1a:** expectancy -1.29 pips, t = -5.22, one-sided p = 1, control p95 -0.81. Does not meet expectancy > 0, t > 2 and above the control p95 together.
- **v1b:** expectancy -0.94 pips, t = -2.71, one-sided p = 0.997, control p95 -0.58. Does not meet expectancy > 0, t > 2 and above the control p95 together.

CRT v1 shows no edge on train after costs, so it is not a candidate for validation.

Trial log: 2 rows were added (v1a and v1b), for a total of 356.
