# Databento cost estimate: CME 6E futures

Generated 2026-11-04T05:55:37Z by `src/data/databento_cost_estimate.py` (HEAD `b558094`, databento 0.90.0). Only metadata calls were made. Nothing was downloaded and no data was bought.

Dataset `GLBX.MDP3`, symbols `6E.FUT`, stype_in `parent`. The credit of $125 is the figure from the task. The balance on the account was not checked.

## Estimates

| id | request | UTC range (end exclusive) | records | size (GB) | price ($) | within credit |
|---|---|---|---:|---:|---:|---:|
| a | ohlcv-1m, 2015-2023 | 2015-01-01 to 2024-01-01 | 4,356,126 | 0.244 | 15.90 | yes |
| b | trades, 2015-2023 | 2015-01-01 to 2024-01-01 | 158,719,551 | 7.619 | 198.67 | no |
| c | trades, 2021 | 2021-01-01 to 2022-01-01 | 12,024,557 | 0.577 | 15.05 | yes |
| d | tbbo, 2021 | 2021-01-01 to 2022-01-01 | 12,024,557 | 0.962 | 25.09 | yes |

Size is the billable uncompressed DBN size (1 GB = 10^9 bytes).

## Combinations against $125

b+c is left out because c is contained in b.

| combination | price ($) | size (GB) | fits | credit left ($) |
|---|---:|---:|---:|---:|
| c | 15.05 | 0.577 | yes | 109.95 |
| a | 15.90 | 0.244 | yes | 109.10 |
| d | 25.09 | 0.962 | yes | 99.91 |
| a+c | 30.95 | 0.821 | yes | 94.05 |
| c+d | 40.14 | 1.539 | yes | 84.86 |
| a+d | 40.99 | 1.206 | yes | 84.01 |
| a+c+d | 56.04 | 1.783 | yes | 68.96 |
| b | 198.67 | 7.619 | no | -73.67 |
| a+b | 214.57 | 7.862 | no | -89.57 |
| b+d | 223.75 | 8.581 | no | -98.75 |
| a+b+d | 239.66 | 8.824 | no | -114.66 |

## Dataset range

`GLBX.MDP3`: 2010-06-06T00:00:00.000000000Z to 2026-11-03T21:55:20.885819000Z.

| schema | start | end |
|---|---|---|
| ohlcv-1m | 2010-06-06T00:00:00.000000000Z | 2026-11-03T21:55:20.885819000Z |
| tbbo | 2010-06-06T00:00:00.000000000Z | 2026-11-03T21:55:20.885819000Z |
| trades | 2010-06-06T00:00:00.000000000Z | 2026-11-03T21:55:20.885819000Z |

## Notes

- The test period (2024 on) was not priced. Every requested range ends at 2024-01-01T00:00Z, exclusive.
- The parent symbol covers all 6E instruments: every expiry and calendar spreads, not one continuous front-month series. Records for one continuous contract would be fewer.
- `databento` is in `.venv` but not pinned in `requirements.txt`.
