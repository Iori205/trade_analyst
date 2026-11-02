# Validation v1 (2022-2023): one-time pre-registered test

Run 2026-11-02T09:52:52Z by `src/research/validation_v1.py` (SHA-256 `1c05b5bc2479ecd3…`), HEAD `c05f08d`.

- **Pre-registration:** `docs/preregistration_validation_v1.md`, SHA-256 `2864f5cf028d0368437948de0f9d7c4396e862b6e5ce1719e82c8322bc8f2e7f`. It matched the trial log before the run, and all 12 frozen file hashes matched.
- **Lock:** `reports/validation_v1.lock` was created before validation was read. This script refuses to run a second time.
- **Test split:** not read.
- **Validation data:** bars and the M1 path for UTC 2022-01-01 to 2023-12-31, excluding `low_quality_period` (2023-02-01 to 2023-07-31), as the split config defines.
  - Validation H1 file SHA-256 `6677684e7d8cfdfd…`.

## Result

- **Candidate A** (`short_tp2_sl1.5_h4`): **FAILED**
- **Candidate B** (Monday 13:00 UTC long): **FAILED**

Multiple testing: Bonferroni over the 2 candidates, one-sided α = 0.025 each.

## Candidate A

| criterion | result |
|---|---|
| 1. expectancy > 0 | **FAILED** |
| 2. t > 2 and one-sided p < 0.025 | **FAILED** |
| 3. above control p95 | **FAILED** |
| 4. expectancy >= 0 in 2022 and 2023 | **FAILED** |

- **Trades:** 91.
- **Expectancy after costs:** -1.133 pips; t = -0.541, one-sided p = 0.706.
- **Control:** p95 2.850, median -0.792 pips; 437 of 1000 control runs are below A.
- **Model:** fitted once on 37,682 train labels (TP-first rate 0.172).
  - Validation candidates: 8,380 eligible, 8,152 with a valid label.
  - Predicted p on validation: p5/p50/p95 = 0.013, 0.138, 0.404.

By year:

| year | trades | expectancy_pips | total_pips | win_rate |
|---|---|---|---|---|
| 2022 | 64 | -2.988 | -191.257 | 0.406 |
| 2023 | 27 | 3.265 | 88.161 | 0.556 |

Outcomes: sl 46, tp 34, time 11.

Entry hours (UTC): 04h 3, 05h 8, 06h 16, 07h 12, 08h 11, 09h 6, 10h 19, 11h 5, 12h 5, 13h 4, 14h 2.

Control pool (valid labels, entry 04-13 UTC): 2022 2,545, 2023 1,249. Control trades per run: median 91.

Charts: `charts/control_distribution.png` and `charts/entry_hours_a.png`. Trades: `trades_a.csv`. Control runs: `control_a.csv`.

## Candidate B

| criterion | result |
|---|---|
| 1. expectancy > 0 | **FAILED** |
| 2. t > 2 and one-sided p < 0.025 | **FAILED** |

- **Trades:** 76.
- **Expectancy after costs:** -3.234 pips; t = -1.889, one-sided p = 0.971.
- **Entry hour:** always 13:00 UTC, Monday.

By year:

| year | trades | expectancy_pips | total_pips | win_rate |
|---|---|---|---|---|
| 2022 | 51 | -2.880 | -146.900 | 0.471 |
| 2023 | 25 | -3.956 | -98.900 | 0.280 |

Trades: `trades_b.csv`.

## What this means

Neither candidate met its pre-registered criteria on 2022-2023, so neither edge from train is confirmed. As pre-registered, no parameters are changed and nothing is re-run on validation. Any new idea needs a new hypothesis developed on train only. Validation is no longer clean for these two hypotheses.

## Trial log

Both candidates' validation results were added to `reports/trials/trials.csv` (split `validation`). Validation v1 is now used up for these two hypotheses. Following the pre-registration, nothing is re-tuned or re-run on it.
