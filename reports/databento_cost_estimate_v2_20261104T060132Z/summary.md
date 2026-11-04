# Databento cost estimate v2: 6E front-month continuous

Generated 2026-11-04T06:01:32Z by `src/data/databento_cost_estimate_v2.py` (HEAD `b558094`, databento 0.90.0). Only metadata calls were made. Nothing was downloaded and no data was bought.

Dataset `GLBX.MDP3`, stype_in `continuous`, symbol used: **`6E.v.0`**.

Symbol attempts:

- `6E.v.0`: worked (3,114,056 records)

## Estimates

| id | request | records | size (GB) | price ($) |
|---|---|---:|---:|---:|
| a | ohlcv-1m, 2015-2023 | 3,114,056 | 0.174 | 11.37 |
| b | trades, 2015-2023 | 150,904,514 | 7.243 | 188.89 |
| c2015 | trades, 2015 | 29,992,956 | 1.440 | 37.54 |
| c2016 | trades, 2016 | 14,472,583 | 0.695 | 18.12 |
| c2017 | trades, 2017 | 15,747,893 | 0.756 | 19.71 |
| c2018 | trades, 2018 | 19,514,707 | 0.937 | 24.43 |
| c2019 | trades, 2019 | 12,938,193 | 0.621 | 16.19 |
| c2020 | trades, 2020 | 15,998,996 | 0.768 | 20.03 |
| c2021 | trades, 2021 | 11,416,158 | 0.548 | 14.29 |
| c2022 | trades, 2022 | 16,507,447 | 0.792 | 20.66 |
| c2023 | trades, 2023 | 14,315,581 | 0.687 | 17.92 |

The nine yearly prices sum to $188.89; the full-range price is $188.89.

## Compared with `6E.FUT`

From `reports/databento_cost_estimate_20261104T055537Z/run.json`. Saving = 1 − new price / old price.

| request | 6E.FUT records | continuous records | 6E.FUT ($) | continuous ($) | saving |
|---|---:|---:|---:|---:|---:|
| ohlcv-1m, 2015-2023 | 4,356,126 | 3,114,056 | 15.90 | 11.37 | 28.5% |
| trades, 2015-2023 | 158,719,551 | 150,904,514 | 198.67 | 188.89 | 4.9% |
| trades, 2021 | 12,024,557 | 11,416,158 | 15.05 | 14.29 | 5.1% |

## Recommendation

Conditions: full ohlcv-1m 2015-2023; trades for 2022, 2023 and at least 3 train years; at least $15 left of $125, so at most $110 spent. Ranking, fixed before the prices were seen: most train years, then a block ending at 2021, then most trades.

**Buy:** ohlcv-1m 2015-2023 and trades for 2019, 2020, 2021, 2022, 2023. Total $100.46, $24.54 left, 3.591 GB.

15 of the possible train-year sets meet the conditions. Top 10:

| train years | price ($) | left ($) | trades | size (GB) |
|---|---:|---:|---:|---:|
| 2019, 2020, 2021 | 100.46 | 24.54 | 71,176,375 | 3.591 |
| 2018, 2020, 2021 | 108.69 | 16.31 | 77,752,889 | 3.907 |
| 2016, 2018, 2019 | 108.69 | 16.31 | 77,748,511 | 3.906 |
| 2017, 2018, 2021 | 108.38 | 16.62 | 77,501,786 | 3.894 |
| 2016, 2017, 2020 | 107.80 | 17.20 | 77,042,500 | 3.872 |
| 2016, 2018, 2021 | 106.78 | 18.22 | 76,226,476 | 3.833 |
| 2017, 2019, 2020 | 105.88 | 19.12 | 75,508,110 | 3.799 |
| 2018, 2019, 2021 | 104.86 | 20.14 | 74,692,086 | 3.760 |
| 2016, 2019, 2020 | 104.29 | 20.71 | 74,232,800 | 3.738 |
| 2017, 2020, 2021 | 103.98 | 21.02 | 73,986,075 | 3.726 |

4 train years do not fit: the cheapest such set costs $118.26, which leaves $6.74, under the $15 reserve.

## Notes

- The test period (2024 on) was not priced. Every range ends at 2024-01-01T00:00Z or earlier, exclusive.
- The credit of $125 is the figure from the task. The account balance was not checked.
- These are estimates from the metadata API, for this account, on the generation date.
