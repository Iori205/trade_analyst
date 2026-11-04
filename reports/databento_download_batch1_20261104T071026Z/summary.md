# Databento download batch 1

Generated 2026-11-04T07:10:26Z. **Status: partial. ohlcv-1m and the end of trades 2019 are done; trades 2020-2023 are not downloaded.**

Dataset `GLBX.MDP3`, symbols `6E.v.0`, stype_in `continuous`. Files are in `data/raw/databento/6E_v0`; the manifest is `manifest.json` there. Files were only counted and hashed, not decoded into bars.

| file | records | expected | match | size (MB) | quoted ($) | SHA-256 |
|---|---:|---:|---:|---:|---:|---|
| ohlcv-1m/2015-2023.dbn.zst | 3,114,056 | 3,114,056 | yes | 42.0 | 11.37 | `8f0d6b9a17cc52bcd9bf9497ad1bf2ae9d99c0f00b87ca6ec59a8bb793b01b14` |
| trades/2019_tail_from_20191122T0900Z.dbn.zst | 966,975 | 966,975 | yes | 18.4 | 1.21 | `3bad9a88054b866d3775cf3b1db4426879e8aa891080e47cc7099288f28d5699` |

Requested in total, failed attempts included: $28.77 (cap $102.00). This is from quotes; the billed amount was not read from the account.

Attempts: 3. Not ok: 1.
## trades 2019

Two files, kept apart. Overlap is removed in processing.

- `trades/2019.dbn.zst.part`: 11,971,242 of 12,938,193 records, interrupted, count not verified, SHA-256 `9bdf37209402c8db000d7a7ca0811e36b3d90dc6e5541f90db96ea34d6027730`. The reader warns that it ends in an incomplete record.
- `trades/2019_tail_from_20191122T0900Z.dbn.zst`: 966,975 records, count verified.

Together they hold 24 records more than the full-year count, which fits an overlap at the join.

## Spending

The ledger above counts the interrupted request at its full $16.19. The owner read $27.30 and 785.2 MB on the portal before the tail request. The first tail run timed out on its price check, before any paid request.

## Batch job: re-download charge

Databento docs, read 2026-11-04: files can be downloaded again at no extra charge for 30 days. Streaming is charged for every duplicate request.

- <https://databento.com/docs/faqs/streaming-vs-batch-download>: "Batch download lets you fetch the same data multiple times without additional charge."; "Download the same data multiple times over a 30 day period, for no additional charge."; "you will be charged each time for duplicate stream requests."
- <https://databento.com/docs/faqs/usage-pricing-and-data-credits>: "You're billed once for the request."; "Then, you can download the data as many times as you want over 30 days — with no charge."
- <https://databento.com/docs/api-historical/batch>: `split_duration` accepts `month`; `cost_usd` is `None` until the job is done processing.

Not covered by the docs: whether submitting the same job twice bills twice. Only one submission per year should be made.

## Remaining: trades 2020-2023

| year | records | price ($) |
|---:|---:|---:|
| 2020 | 15,998,996 | 20.03 |
| 2021 | 11,416,158 | 14.29 |
| 2022 | 16,507,447 | 20.66 |
| 2023 | 14,315,581 | 17.92 |

Ledger $28.77 + $72.90 = $101.67, under the $102.00 cap. Not submitted yet.
