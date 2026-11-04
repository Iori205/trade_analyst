# Databento download batch 1

Generated 2026-11-04T06:50:21Z. **Status: stopped: trades_2019 connection broke after 32 minutes (IncompleteRead); retrying would pass the $102 cap, so no further request was made**

Dataset `GLBX.MDP3`, symbols `6E.v.0`, stype_in `continuous`. Files are in `data/raw/databento/6E_v0`; the manifest is `manifest.json` there. Files were only counted and hashed, not decoded into bars.

| file | records | expected | match | size (MB) | quoted ($) | SHA-256 |
|---|---:|---:|---:|---:|---:|---|
| ohlcv-1m/2015-2023.dbn.zst | 3,114,056 | 3,114,056 | yes | 42.0 | 11.37 | `8f0d6b9a17cc52bcd9bf9497ad1bf2ae9d99c0f00b87ca6ec59a8bb793b01b14` |

Requested in total, failed attempts included: $27.56 (cap $102.00). This is from quotes; the billed amount was not read from the account.

Attempts: 2. Not ok: 1.
## Not downloaded

trades 2019 is partial and unverified (`trades/2019.dbn.zst.part`, 232.6 MB, kept). trades 2020, 2021, 2022 and 2023 were not requested.

## Cap check on a retry

Ledger $27.56 (ohlcv-1m $11.37 + failed trades 2019 $16.19) + remaining five requests $89.09 = $116.65, over the $102.00 cap. The failed attempt counts in full because the amount billed for it is not known.

## Data quality warnings from the client

Databento marked some days degraded. The warning listed only the first few: 2017-11-13, 2018-10-21, 2019-01-15, 2019-02-22, 2019-03-13. The full list was not fetched.

## Partial trades 2019

The part file reads without error up to 11,971,242 of 12,938,193 records (92.5%), last ts_event 2019-11-22 09:00:01 UTC. It was only counted. It is unverified: no hash in the manifest.

Free quote for the missing tail, 2019-11-22T09:00Z to 2020-01-01: 966,975 records, $1.21. Ledger $27.56 + tail $1.21 + trades 2020-2023 $72.90 = $101.67. The tail request is not in the approved list, so it was not made.
