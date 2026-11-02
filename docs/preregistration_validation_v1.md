# Pre-registration: validation v1 (one-time test on 2022-2023)

Written 2026-11-02, before any validation-period data (bars, M1 rows or labels) was read. This file is not
edited after its SHA-256 is recorded in `reports/trials/trials.csv`. The test is run once. If it fails,
nothing is re-tuned or re-run on validation.

## Frozen code and inputs

All at commit `c05f08dd3272a3ebd5ad200204d8bf0c077b7c83` (clean for these files):

| file | SHA-256 |
|---|---|
| src/research/ml_discovery.py | `77f32dc300f327667933418e0890d44b8d130a5677eec3abb720ae04f7241d10` |
| src/backtest/engine.py | `5d295ff8d4682138975842807ad559b6fe3f837907c62e1642f92c089be5cef4` |
| src/backtest/baselines.py | `544bffd473596b78f693fe61947eb199d4e43634a9baaf78bd84f9ae0e8fc79d` |
| src/data/cost_model.py | `16e908d3936f964b43de2cbf88f8c5f383b8d01dfb309f6604ef40ca62c68187` |
| src/data/splits.py | `e3735ba208f23b0ca68c2a6b17c8f0d436124ec528ae9ba30570739f584b4723` |
| config/cost_model_v1.yaml | `e1085e9e5b297e32e9ac8d7a68f8f21e0790912ced56999a12d8e5059fabfdd8` |
| config/splits.yaml | `ffa90d0916238475dabe379074ba00148f72ab800f9e9314d5c1168ea1097701` |
| data/processed/cost_model/v1/hour_of_week.csv | `f5c3b42bd5f3ad67b065b0fe47bb44dbe0e30d013929adc86c15e48b2bae9605` |
| data/processed/cost_model/v1/segments.csv | `f72e312a102b1a1459d516e85629b4e8d583fd5fea59b78f97cfe5f98c2221d3` |
| data/processed/cost_model/v1/model.json | `e23091712530417b832dad4dedd69cd08df170d6aaac29cc75545be65194819e` |
| data/processed/eurusd_bars/v1/eurusd_h1_train.parquet | `b7035d03eb13b589343268ae5a893258dfae73e8781d18e77f21c4b96a06fabc` |
| data/processed/eurusd_m1/v1/eurusd_m1_utc.parquet | `1d342bb75300f250df423c48235df3b541dd5982f5b007a55c87e11b61eded5b` |

The runner `src/research/validation_v1.py` is written after this file. It implements only what is stated
here, by calling the frozen functions above. It checks the SHA-256 values above before reading
validation, and refuses to run if any differs.

## Data

- **Validation split:** UTC 2022-01-01 to 2023-12-31 (`config/splits.yaml`). Validation H1 bars come from `eurusd_h1_validation.parquet`; the M1 path comes from `read_m1_split(..., "validation")`.
- **Excluded period:** following the split config, M1 rows flagged `low_quality_period` (UTC 2023-02-01 to 2023-07-31) are excluded. Bars there do not exist.
- **Censoring:** a label whose window has an M1 gap over 30 minutes, or ends after 2023-12-31, is dropped. This is the frozen censoring rule.
- **Test split:** not touched.
- **History for features:** validation rows may use train bars before them (ATR, 24 h return, H4 EMA50, 30-day ATR percentile, previous day). This is past data, not look-ahead.
- **Cost:** `cost_for(entry_time)` at p75 + 0.6 commission + 0.2 slippage, as in the frozen config.

## Candidate A: `hgb_short_tp2_sl1.5_h4`

- **Label, features, model:** exactly as in `ml_discovery.py`.
  - Short; TP = 2 × ATR(14, H1); SL = 1.5 × ATR; horizon 4 h; barriers checked on the M1 bid path; same-minute hit = SL.
  - The 18 features in `FEATURES`.
  - `HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=100, l2_regularization=1.0, early_stopping=False, random_state=0)`.
- **Training:** fitted ONCE on all valid train labels with an entry time from 2015-01-01 up to 2022-01-01 minus 4 h (embargo = horizon). Then it predicts every validation candidate.
- **Trading rule:** enter when p × TP − (1 − p) × SL − cost_for(entry) > 0.
  - One position at a time; the next entry may start at or after the previous exit.
  - Engine entry rules: the entry bar must directly follow the signal bar, be clean, and not fall in a rollover, weekly-open or market-closed period.
  - P&L = label return (TP, −SL, or the time-exit return) − cost.
- **Success criteria (ALL must hold):**
  1. Expectancy after costs > 0.
  2. Per-trade t-stat > 2, with one-sided p < 0.025 (normal approximation; Bonferroni α = 0.05 / 2).
  3. **Control:** 1000 runs (seed 20261105) of random short trades.
     - Entries come from the same validation candidates with a valid label and an entry hour of 04 to 13 UTC inclusive.
     - Same TP/SL/horizon labels and exits, one position at a time.
     - Same number of trades as candidate A in each year (2022 and 2023). A year is capped at the trades the pool allows.
     - Passes if A's expectancy is above the 95th percentile of the 1000 control expectancies.
  4. Expectancy ≥ 0 in 2022 and in 2023 separately. A year with no trades counts as not met.

## Candidate B: Monday 13:00 UTC long, exit 14:00 (unchanged)

- **Strategy:** `monday_13()` from `src/backtest/baselines.py`, run with `run_backtest(..., "H1", split="validation")`.
  - Signal at the close of the Monday 12:00 H1 bar; entry at the 13:00 open; time exit at the 14:00 open.
  - Engine entry rules; cost = `cost_for` at p75.
- **Success criteria (both must hold):**
  1. Expectancy after costs > 0.
  2. Per-trade t-stat > 2, with one-sided p < 0.025.

## Multiple testing

- **Correction:** two candidates, Bonferroni with α = 0.025 each (one-sided).
- **No selection:** the two are evaluated independently. Nothing else is tested on validation in this run.

## Run protocol

1. Record this file's SHA-256 in the trial log (strategy `preregistration_validation_v1`).
2. Run `src/research/validation_v1.py` once.
   - It checks this file's SHA-256 against the logged value and the frozen SHA-256 values above.
   - It creates `reports/validation_v1.lock` (exclusive create) before it reads validation, and refuses to run if the lock exists.
3. Write the report (`reports/validation_v1_<timestamp>/summary.md`):
   - PASS or FAIL for each criterion;
   - results by year;
   - the control distribution;
   - the distribution of entry hours.
4. Log both candidates' validation results in the trial log.
5. If anything fails, report it as failed. No parameter is changed and nothing is re-run on validation.
