# Strategy: daily trend v1, train 2015-2021

Generated 2026-11-04T11:43:35Z by `src/strategies/daily_trend.py` (HEAD `cbca1fd`, uncommitted script changes: true). Data: `data/processed/eurusd_m1/v1/eurusd_m1_utc.parquet` through the split guard, train only (SHA-256 `1d342bb75300f250…`). Validation and test were not read.

## Rules (frozen before running)

- **v1a Donchian 20/10:** close above the last 20 days' high = long, below their low = short. Exit on a close through the opposite 10-day low or high.
- **v1b Donchian 55/20:** the same with 55 and 20.
- **v1c MA 50/200:** SMA 50 above SMA 200 = long, below = short. Reverses on a cross.
- **Timing:** signal at the daily close (17:00 New York), fill at the next day's open.
- **Cost:** `cost_for(entry)` at p75, once per trade.
- **Swap:** 0.5 pip per night on both sides, Wednesday x 3. This is an assumption, not a measured rate.

Where the rules are silent, I fixed these choices before running:

- Donchian windows exclude the signal day.
- A night is one 17:00 rollover: a trade pays for the weekdays from its entry day up to, but not including, its exit day.
- v1c takes its side as soon as both averages exist, without waiting for a first cross.
- A position still open on the last train day closes at that day's close.
- Flagged minutes are measured, not removed. No day is dropped.

## Things to know before reading the numbers

- **Cost is not ~1.0 pip here.** Every daily open sits in the rollover or weekly-open window, so `cost_for` returns 2.7 pips at the median entry (mean 2.79). The results use `cost_for`, as specified; a fixed 1.0 pip version is in the scenario table.
- **The engine's entry blocks are off.** They reject rollover and weekly-open entries, so they would reject every daily open. This strategy has its own daily loop.
- **Prices are bid only.** The open is the first bid after the rollover, when the spread is at its widest.
- **v1c starts late.** It needs 200 days, so its first possible fill is 2015-10-08.

## Daily bars

- **Bars:** 1,820 from 2015-01-01 to 2021-12-31. Weekdays: Mon 363, Tue 364, Wed 364, Thu 366, Fri 363.
- **Sunday:** with a 17:00 New York close, the Sunday session (from 17:00) is already the start of Monday's bar, so there is no short Sunday bar. Minutes that had to be moved from a weekend label: 0.
- **Short bars:** 9 bars have under 1,200 minutes (holidays, data gaps and the partial first day): 2015-01-01 (37), 2016-12-26 (472), 2017-01-02 (864), 2018-12-25 (578), 2019-05-27 (717), 2019-12-25 (518), 2020-11-30 (417), 2020-12-25 (536), 2021-05-31 (412). They still count as days.
- **Weekdays with no bar:** 2015-12-25, 2016-01-01, 2017-12-25, 2018-01-01, 2019-01-01, 2020-01-01, 2021-01-01. Swap is still charged for them.
- **Late opens:** 50 bars start after 17:00 New York, 7 of them by more than 30 minutes. Fills on bars more than 30 minutes late: v1a 1; v1b 0; v1c 0.
- **Flagged minutes** (gap_before, duplicate_identical, duplicate_conflict, low_quality_period, suspect_late_open, dst_transition_hour): 0.725% overall. Per bar: median 0.14%, p95 1.21%, max 33.3%. Bars above 10%: 29, mostly DST-switch Mondays, whose Sunday session is flagged. Per-day values: `daily_flags.csv`.
- **Flagged entries:** v1a 0 of 57; v1b 1 of 24; v1c 0 of 10 entry bars have over 10% flagged minutes.

## Results (after cost and swap)

| metric | v1a | v1b | v1c |
|---|---|---|---|
| trades | 57 | 24 | 10 |
| win rate | 0.298 | 0.333 | 0.400 |
| avg win (pips) | 165 | 262 | 408 |
| avg loss (pips) | -150 | -271 | -429 |
| expectancy (pips) | -56.305 | -93.558 | -94.330 |
| total (pips) | -3,209 | -2,245 | -943 |
| max drawdown, closed trades (pips) | 3,641 | 2,389 | 2,075 |
| max drawdown, marked to market (pips) | 4,083 | 2,845 | 2,372 |
| avg hold (trading days) | 21.789 | 44.875 | 162 |
| avg hold (calendar days) | 30.778 | 62.583 | 228 |
| total swap (pips) | 870 | 752 | 1,138 |
| mean cost per trade (pips) | 2.753 | 2.825 | 2.850 |
| daily Sharpe | -0.862 | -0.506 | -0.241 |
| t | -2.423 | -1.390 | -0.631 |
| one-sided p | 0.992 | 0.918 | 0.736 |
| BH q (3 trials) | 0.992 | 0.992 | 0.992 |

Sharpe and t use net pips per trade or day. The closed-trade drawdown sees only exits; the marked-to-market one also counts open losses, measured at each daily open.

## With and without swap (expectancy per trade, pips)

| variant | gross | cost_for, no swap | cost_for + swap (headline) | 1.0 pip, no swap | 1.0 pip + swap | total gross | total cost | total swap | trades |
|---|---|---|---|---|---|---|---|---|---|
| v1a | -38.298 | -41.051 | -56.305 | -39.298 | -54.553 | -2,183 | 157 | 870 | 57 |
| v1b | -59.379 | -62.204 | -93.558 | -60.379 | -91.733 | -1,425 | 67.800 | 752 | 24 |
| v1c | 22.320 | 19.470 | -94.330 | 21.320 | -92.480 | 223 | 28.500 | 1,138 | 10 |

## Random baselines (expectancy, pips)

| variant | baseline | swap | strategy | median | p5 | p95 | runs below strategy |
|---|---|---|---|---|---|---|---|
| v1a | random placement + direction | with swap | -56.305 | -18.060 | -67.733 | 32.033 | 104 |
| v1a | random placement + direction | no swap | -41.051 | -2.691 | -52.488 | 47.456 | 104 |
| v1a | own trades, random direction | with swap | -56.305 | -18.646 | -58.236 | 21.648 | 60 |
| v1a | own trades, random direction | no swap | -41.051 | -3.391 | -42.981 | 36.903 | 60 |
| v1b | random placement + direction | with swap | -93.558 | -34.633 | -142 | 69.782 | 165 |
| v1b | random placement + direction | no swap | -62.204 | -3.185 | -110 | 101 | 165 |
| v1b | own trades, random direction | with swap | -93.558 | -36.329 | -153 | 83.798 | 204 |
| v1b | own trades, random direction | no swap | -62.204 | -4.975 | -122 | 115 | 204 |
| v1c | random placement + direction | with swap | -94.330 | -112 | -398 | 149 | 538 |
| v1c | random placement + direction | no swap | 19.470 | 2.135 | -284 | 263 | 538 |
| v1c | own trades, random direction | with swap | -94.330 | -101 | -386 | 148 | 522 |
| v1c | own trades, random direction | no swap | 19.470 | 12.560 | -272 | 262 | 522 |

- **Random placement + direction:** 1000 runs (seed 20261110). Same trade count, same holding lengths in shuffled order, random start days without overlap after the warm-up, random direction. Costs and swap by the same rules.
- **Own trades, random direction:** 1000 runs (seed 20261111). Same entries and exits, direction chosen by coin flip. This isolates the choice of direction.

## Long and short (after cost and swap)

| variant | side | trades | win_rate | expectancy_pips | total_pips | t_stat |
|---|---|---|---|---|---|---|
| v1a | long | 28 | 0.286 | -47.529 | -1,331 | -1.419 |
| v1a | short | 29 | 0.310 | -64.779 | -1,879 | -1.977 |
| v1b | long | 11 | 0.455 | -86.491 | -951 | -0.631 |
| v1b | short | 13 | 0.231 | -99.538 | -1,294 | -1.882 |
| v1c | long | 5 | 0.400 | -70.020 | -350 | -0.267 |
| v1c | short | 5 | 0.400 | -119 | -593 | -0.669 |

## By year of exit

**v1a**

| year | trades | net_pips | expectancy_pips | win_rate | net_no_swap_pips |
|---|---|---|---|---|---|
| 2015 | 6 | -332 | -55.267 | 0.333 | -235 |
| 2016 | 9 | -1,169 | -130 | 0.111 | -1,066 |
| 2017 | 9 | -225 | -25.033 | 0.222 | -88.300 |
| 2018 | 6 | 138 | 23.017 | 0.333 | 256 |
| 2019 | 9 | -1,091 | -121 | 0.111 | -975 |
| 2020 | 9 | -660 | -73.344 | 0.333 | -529 |
| 2021 | 9 | 129 | 14.389 | 0.667 | 297 |

**v1b**

| year | trades | net_pips | expectancy_pips | win_rate | net_no_swap_pips |
|---|---|---|---|---|---|
| 2015 | 3 | -1,149 | -383 | 0.000 | -1,069 |
| 2016 | 1 | 57.500 | 57.500 | 1.000 | 110 |
| 2017 | 3 | 748 | 249 | 0.667 | 901 |
| 2018 | 3 | 155 | 51.600 | 0.667 | 278 |
| 2019 | 4 | -755 | -189 | 0.000 | -648 |
| 2020 | 4 | -874 | -219 | 0.250 | -767 |
| 2021 | 6 | -427 | -71.200 | 0.333 | -298 |

**v1c**

| year | trades | net_pips | expectancy_pips | win_rate | net_no_swap_pips |
|---|---|---|---|---|---|
| 2015 | 1 | -638 | -638 | 0.000 | -614 |
| 2016 | 2 | -1,027 | -514 | 0.000 | -861 |
| 2017 | 1 | -409 | -409 | 0.000 | -303 |
| 2018 | 1 | 422 | 422 | 1.000 | 614 |
| 2020 | 1 | 205 | 205 | 1.000 | 580 |
| 2021 | 4 | 504 | 126 | 0.500 | 780 |

## Exits

- **v1a:** signal 56, end_of_data 1. Largest winner 408 pips, largest loser -375 pips.
- **v1b:** signal 23, end_of_data 1. Largest winner 834 pips, largest loser -666 pips.
- **v1c:** signal 9, end_of_data 1. Largest winner 690 pips, largest loser -638 pips.

## Verdict

- **v1a:** 57 trades, expectancy -56.3 pips, t = -2.42, q = 0.992, above 104/1000 random placements and 60/1000 random-direction runs. Does not meet all checks.
- **v1b:** 24 trades, expectancy -93.6 pips, t = -1.39, q = 0.992, above 165/1000 random placements and 204/1000 random-direction runs. Does not meet all checks.
- **v1c:** 10 trades, expectancy -94.3 pips, t = -0.63, q = 0.992, above 538/1000 random placements and 522/1000 random-direction runs. Does not meet all checks.
- **v1a loses before costs:** gross -38.3 pips per trade. Cost and swap only add to it.
- **v1b loses before costs:** gross -59.4 pips per trade. Cost and swap only add to it.
- **Swap decides v1c:** gross 22.3 pips per trade, 19.5 after cost, -94.3 after swap. Before swap it is above 538/1000 random placements, so even then it is inside the random range.

No variant meets the train checks together (expectancy > 0, t > 2, q < 0.05, above both baselines' p95).

Trial log: 3 rows were added (v1a, v1b, v1c), for a total of 359. The swap-free and fixed-cost views are views of these 3 trials, not extra trials. The logged net includes `cost_for` and swap; the log has no swap column, so the swap rate is in `params`.

Trades (pips only, no price levels): `trades_v1a.csv`, `trades_v1b.csv`, `trades_v1c.csv`.
