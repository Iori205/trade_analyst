# Databento batch 1: download approval

Written 2026-11-04T06:13:23Z by `src/data/databento_download.py`, before any paid request. Prices and record counts are fresh from `metadata.get_cost` and `metadata.get_record_count`.

Dataset `GLBX.MDP3`, symbols `6E.v.0`, stype_in `continuous`. End dates are exclusive.

| # | schema | start | end | records | price ($) | file |
|---:|---|---|---|---:|---:|---|
| 1 | ohlcv-1m | 2015-01-01 | 2024-01-01 | 3,114,056 | 11.37 | `data/raw/databento/6E_v0/ohlcv-1m/2015-2023.dbn.zst` |
| 2 | trades | 2019-01-01 | 2020-01-01 | 12,938,193 | 16.19 | `data/raw/databento/6E_v0/trades/2019.dbn.zst` |
| 3 | trades | 2020-01-01 | 2021-01-01 | 15,998,996 | 20.03 | `data/raw/databento/6E_v0/trades/2020.dbn.zst` |
| 4 | trades | 2021-01-01 | 2022-01-01 | 11,416,158 | 14.29 | `data/raw/databento/6E_v0/trades/2021.dbn.zst` |
| 5 | trades | 2022-01-01 | 2023-01-01 | 16,507,447 | 20.66 | `data/raw/databento/6E_v0/trades/2022.dbn.zst` |
| 6 | trades | 2023-01-01 | 2024-01-01 | 14,315,581 | 17.92 | `data/raw/databento/6E_v0/trades/2023.dbn.zst` |

**Total: $100.46** (task estimate $100.46). **Hard cap: $102.00.**

Requests outside this table are not allowed. The test period (2024 on) is not requested.

Status: approved by the owner 2026-11-04.

## Amendment 1 (2026-11-04, approved by the owner)

trades 2019 broke at 92.5% (`trades/2019.dbn.zst.part`, kept as is). The owner read $27.30 and 785.2 MB on the Databento portal, after that request.

Added request: `trades`, 2019-11-22T09:00:00Z to 2020-01-01, about $1.21, file `data/raw/databento/6E_v0/trades/2019_tail_from_20191122T0900Z.dbn.zst`. Overlap with the part file is removed in processing.

## Amendment 2 (2026-11-04, approved by the owner in `prompts/next.md`)

trades 2020, 2021, 2022 and 2023: one batch job per year, `split_duration="month"`, run by `src/data/databento_batch.py`, about $72.90. Hard cap $110, which includes the $27.30 the owner read on the portal. If a job's `cost_usd` passes the cap, the next job is not sent. Files go in `data/raw/databento/6E_v0/trades/<year>/`.
