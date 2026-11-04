# Databento batch jobs: trades 2020-2023

Generated 2026-11-04T09:39:21Z. **Status: complete**

Dataset `GLBX.MDP3`, symbols `6E.v.0`, stype_in `continuous`, split_duration `month`, one job per year. Files are in `data/raw/databento/6E_v0/trades/<year>/`; hashes and counts are in `data/raw/databento/6E_v0/manifest.json`. Files were only hashed and counted, not decoded into bars.

| year | job | records | expected | match | files | size (MB) | quoted ($) | cost_usd ($) | status |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 2020 | `GLBX-20261104-UR56FNYPWJ` | 15,998,996 | 15,998,996 | yes | 12 | 268.2 | 20.03 | 20.03 | verified |
| 2021 | `GLBX-20261104-XR9AXSJEXV` | 11,416,158 | 11,416,158 | yes | 12 | 191.9 | 14.29 | 14.29 | verified |
| 2022 | `GLBX-20261104-3KQFDFJU4Q` | 16,507,447 | 16,507,447 | yes | 12 | 282.3 | 20.66 | 20.66 | verified |
| 2023 | `GLBX-20261104-9X4RC3U54Y` | 14,315,581 | 14,315,581 | yes | 12 | 238.7 | 17.92 | 17.92 | verified |

Spent: $27.30 (portal reading by the owner) + $1.21 (trades 2019 tail) + these jobs = **$101.41** of the $110.00 cap. Jobs use cost_usd; a job without it uses its quote.

## Days that are not fully available

`metadata.get_dataset_condition`, 2015-01-01 to 2023-12-31: 14 of 2817 days. These conditions are for the whole dataset, not for 6E alone. `files` says what we hold for that day.

| date | condition | last modified | files |
|---|---|---|---|
| 2017-11-13 | degraded | 2026-09-03 | ohlcv-1m |
| 2018-10-21 | degraded | 2026-08-20 | ohlcv-1m |
| 2019-01-15 | degraded | 2026-08-22 | ohlcv-1m + trades |
| 2019-02-22 | degraded | 2026-08-30 | ohlcv-1m + trades |
| 2019-03-13 | degraded | 2026-08-24 | ohlcv-1m + trades |
| 2019-03-26 | degraded | 2026-08-23 | ohlcv-1m + trades |
| 2020-02-27 | degraded | 2026-08-30 | ohlcv-1m + trades |
| 2020-02-28 | degraded | 2026-09-01 | ohlcv-1m + trades |
| 2020-05-05 | degraded | 2026-08-23 | ohlcv-1m + trades |
| 2020-06-30 | degraded | 2026-08-23 | ohlcv-1m + trades |
| 2020-07-01 | degraded | 2026-08-29 | ohlcv-1m + trades |
| 2021-12-05 | degraded | 2026-09-01 | ohlcv-1m + trades |
| 2022-01-02 | degraded | 2026-08-31 | ohlcv-1m + trades |
| 2022-11-06 | degraded | 2026-08-31 | ohlcv-1m + trades |
