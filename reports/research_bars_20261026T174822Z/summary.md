# Research bars v1: M15 and H1 by split

Built 2026-10-26T17:47:50Z by `src/data/bars.py` at commit `2aadfb07972763ed87a4ebd12471a1a2bdd20288` (clean tree for the builder and config: git_dirty = false).

- Input: `data/processed/eurusd_m1/v1/eurusd_m1_utc.parquet`, SHA-256 `1d342bb75300f250df423c48235df3b541dd5982f5b007a55c87e11b61eded5b`, 4,289,924 rows (checked against its SHA256SUMS.txt; unchanged after the build).
- Timestamp policy: C4 (C4-v1), era boundary 2018-12-16.
- Splits: `config/splits.yaml` (SHA-256 `ffa90d0916238475dabe379074ba00148f72ab800f9e9314d5c1168ea1097701`).
- Output: `data/processed/eurusd_bars/v1/` (gitignored), one Parquet file per timeframe and split, plus manifest.json and SHA256SUMS.txt.

## Splits (UTC)

| split | range | M1 rows used | M1 rows excluded |
|---|---|---:|---:|
| train | 2015-01-01 .. 2021-12-31 | 2,603,498 | 0 |
| validation | 2022-01-01 .. 2023-12-31 | 559,403 | 136,100 (low_quality_period) |
| test (locked) | 2024-01-01 .. 2026-08-31 | 990,684 | 0 |

239 M1 rows (2026-09-01 UTC) fall outside every split and are not in any bar file.

## Bars

| timeframe | split | bars | M1 minutes | m1_count < expected | any_flag | bars with duplicate_conflict |
|---|---|---:|---:|---:|---:|---:|
| M15 | train | 174,125 | 2,603,318 | 2.92% | 3.47% | 0 |
| M15 | validation | 37,460 | 559,283 | 3.32% | 3.85% | 0 |
| M15 | test | 66,349 | 990,620 | 3.82% | 4.32% | 1 |
| H1 | train | 43,534 | 2,603,318 | 7.72% | 8.31% | 0 |
| H1 | validation | 9,366 | 559,283 | 8.10% | 8.64% | 0 |
| H1 | test | 16,589 | 990,620 | 9.82% | 10.44% | 1 |

"M1 minutes" counts distinct UTC minutes, so identical duplicate copies are counted once. The test row has only counts. It was read once, with an explicit `--unlock-test`, to build the files. No test-period values were analysed.

## Rules

- Each bar is labelled by its UTC start and covers [start, start + 15 min) or [start, start + 60 min). Split boundaries fall on UTC midnight, so no bar crosses two splits.
- Missing minutes are not filled. An interval with no M1 minute has no bar. `expected_minutes` is the bar length (15 or 60), and `any_gap` = `m1_count < expected_minutes`. Partial bars at the weekly open, the daily rollover and holidays are kept as they are.
- Duplicates: one copy is used from each `duplicate_identical` group. A `duplicate_conflict` minute uses its first copy (by source_file, source_line). The bar keeps the `duplicate_conflict` flag. All 4 conflicting minutes (2026-07-05 21:31-21:35 UTC) are in the test split.
- Flags: each of `gap_before`, `duplicate_identical`, `duplicate_conflict`, `low_quality_period`, `suspect_late_open`, `dst_transition_hour` is an OR over the bar's M1 rows. `any_flag` is the OR of all of them.
- Guard: `src/data/splits.py` raises `TestSetLockedError` for any read whose range touches the test split, including an unbounded read. The only exception is an explicit `unlock_test=True`. `read_bars(..., "test", ...)` has the same guard.
- Reproducibility: a second build to a scratch directory gave the same SHA-256 for all 6 Parquet files. Only manifest.json differs, because it records the creation time.

## Output files

| file | rows | SHA-256 |
|---|---:|---|
| eurusd_m15_train.parquet | 174,125 | `6090cb8014ada01c8adf71c54ee999d1f9a5ae019f8d6272329279b1d11ac3ba` |
| eurusd_m15_validation.parquet | 37,460 | `458aaff32413070791fd5dbb5f99444d85e40b9524819c3a4f37f414f00fb425` |
| eurusd_m15_test.parquet | 66,349 | `fec530d3b79a7dc3f62e852f3e42d088e0eab70bd515cd773e4c249c82de8415` |
| eurusd_h1_train.parquet | 43,534 | `b7035d03eb13b589343268ae5a893258dfae73e8781d18e77f21c4b96a06fabc` |
| eurusd_h1_validation.parquet | 9,366 | `6677684e7d8cfdfdfc1e6d864c8dcdc2a61da4586776c2625948b316c5174c00` |
| eurusd_h1_test.parquet | 16,589 | `a7334b664f3d9c0a9ee44ae279003bff15e55313b436ceafe3f882ca857b089e` |
