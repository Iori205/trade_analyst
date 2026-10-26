# Timezone stage: closed

Closed 2026-10-26 (UTC).

- **Policy:** C4-v1, approved by the project owner 2026-10-26.
  - HistData labels before 2018-12-16 are America/New_York local time.
  - Labels from 2018-12-16 are Europe/Zurich local time minus 6 h.
  - Any boundary from 2018-11-04 to 2019-03-10 gives identical UTC.
- **Evidence:** `reports/timezone_decision.md`. A frozen copy is `data/processed/eurusd_m1/v1/timezone_decision_snapshot.md` (SHA-256 `9040d065…9b8e6`). In brief:
  - 53/53 decisive FXCM days match C4.
  - The rivals each fail a whole regime cell at 0%.
  - FXCM's UTC claim is validated on 7 events.
- **Applied in:** `data/processed/eurusd_m1/v1/`.
  - 4,289,924 rows, equal to the input; nothing filled or removed; flags only.
  - Its manifest records the policy, input and script SHA-256 values, and `git_commit` `86cd46d72fae0204e99f13a3a11703c9fa11ef97`.
- **Untouched:** raw HistData, the legacy Parquet files, Dukascopy, FXCM `53.csv` and `data/reference/fxcm/v1/`. All SHA-256 values were verified after the stage.
- **Terms:** `docs/approvals/fxcm_batch1.md` points to `docs/approvals/fxcm_email_2026-10-23.txt` (SHA-256 `fea0f56c…98f0d`, not in git). FXCM's reply grants "personal use" with no year range stated.
- **Tests:** 97 passed.

**Carried forward, not blocking:**
- **2015–2017 and 2021–2023/2026** rely on internal evidence only.
- **2024-10-27 and the other late-open Sundays** are flagged `suspect_late_open`.
- **EU-switch-Sunday holes and repeats** are flagged `dst_transition_hour` / `duplicate_identical`.
- **The 2026-07-05 conflicts** are flagged `duplicate_conflict`.
- **Policies P1–P5** for derived features are still to be decided.

Any change to the timestamp rule requires a new dataset version (v2); v1 is not edited.
