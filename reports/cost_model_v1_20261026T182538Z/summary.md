# Spread / cost model v1

Built 2026-10-26T18:23:56Z by `src/data/cost_model.py` from `config/cost_model_v1.yaml` (SHA-256 `d7328127749ebf8a…`). Output: `data/processed/cost_model/v1/` (gitignored). The git tree was not committed at build time (HEAD `1eaeddd`, git_dirty = true), so the script SHA-256 values in the manifest are the reference.

- **Source:** 10 FXCM weeks from `data/reference/fxcm/v1/`; all SHA-256 values were checked before and after the build. 71,746 minutes in total, 63,523 with a positive spread used in the statistics.
- **Spread:** `ask_close − bid_close` of each M1 bar, in pips (1 pip = 0.0001), at the UTC bar label.
- **Reproducibility:** a second build gave identical SHA-256 values for every output except `manifest.json`, which holds the build time.

## 1. Minute spreads: anomalies (counted, not removed)

| week | normal | extreme (> 5 pips) | zero | negative | zero + negative |
|---|---:|---:|---:|---:|---:|
| 2018/12.csv.gz | 6,391 | 1 | 566 | 214 | 10.9% |
| 2018/43.csv.gz | 6,864 | 2 | 259 | 60 | 4.4% |
| 2018/44.csv.gz | 6,650 | 4 | 447 | 83 | 7.4% |
| 2018/45.csv.gz | 6,516 | 4 | 566 | 107 | 9.4% |
| 2019/11.csv.gz | 6,588 | 1 | 459 | 112 | 8.0% |
| 2019/29.csv.gz | 5,874 | 18 | 1,108 | 167 | 17.8% |
| 2019/44.csv.gz | 5,461 | 0 | 1,374 | 341 | 23.9% |
| 2020/3.csv.gz | 4,807 | 0 | 2,021 | 335 | 32.9% |
| 2024/11.csv.gz | 7,162 | 17 | 1 | 3 | 0.1% |
| 2025/28.csv.gz | 7,104 | 59 | 0 | 0 | 0.0% |
| all | 63,417 | 106 | 6,801 | 1,422 | 11.5% |

- Zero and negative spreads are kept in `spread_minutes.parquet` but are not used in the statistics, because a cost cannot be ≤ 0.
- Extreme spreads are kept in the statistics. Most fall in the rollover and weekly-open windows, where they are real.
- The 2024 and 2025 weeks have almost no zero or negative spreads, while 2018 to 2020 have 4–33%. This looks like a change in how FXCM produces the bars, not in the market. Excluding them pushes the 2018–2020 medians up, so the model is on the conservative side.

## 2. Segments (New York clock, so they follow DST)

| segment | regime | minutes | weeks | measured median / p75 / p90 | model value | fallback |
|---|---|---:|---:|---|---|---|
| weekly_open_first_hour | all | 525 | 10 | 1.5 / 2.4 / 4.1 | 1.5 / 2.4 / 4.1 | – |
| weekly_open_first_hour | summer | 410 | 8 | 1.65 / 2.7 / 4.61 | 1.65 / 2.7 / 4.61 | – |
| weekly_open_first_hour | winter | 115 | 2 | 1.2 / 1.5 / 2.22 | 1.5 / 2.4 / 4.1 | segment_all |
| weekly_open_rest | all | 1015 | 10 | 0.2 / 0.3 / 0.4 | 0.2 / 0.3 / 0.4 | – |
| weekly_open_rest | summer | 914 | 8 | 0.2 / 0.3 / 0.5 | 0.2 / 0.3 / 0.5 | – |
| weekly_open_rest | winter | 101 | 2 | 0.2 / 0.2 / 0.3 | 0.2 / 0.3 / 0.4 | segment_all |
| rollover | all | 2529 | 10 | 0.9 / 1.9 / 3 | 0.9 / 1.9 / 3 | – |
| rollover | summer | 2020 | 8 | 0.9 / 2 / 3.2 | 0.9 / 2 / 3.2 | – |
| rollover | winter | 509 | 2 | 1 / 1.6 / 2.22 | 0.9 / 1.9 / 3 | segment_all |

- **rollover:** Mon–Fri 16:55–18:00 New York. That is 20:55–22:00 UTC in summer and 21:55–23:00 UTC in winter.
- **weekly_open_first_hour:** Sunday 17:00–18:00 New York.
- **weekly_open_rest:** the rest of the UTC Sunday.
- **Lookup:** it uses the `all` rows. The summer and winter rows are descriptive, and a thin regime row shows its pooled value.
- **Market closed:** the lookup returns the all-hours fallback, i.e. Saturday, Friday from 17:00 New York, and Sunday before 17:00 New York.

## 3. Regular hours: UTC weekday × hour (median / p75 / p90, pips)

`*` = fallback, i.e. fewer than 120 positive-spread minutes or fewer than 3 weeks. The all-hours values 0.2 / 0.2 / 0.3 are used there (59,454 regular minutes, 10 weeks). The "rollover" mark means that hour touches the rollover window in that regime. Those minutes are modelled in the rollover segment, not in this cell.

| UTC hour | Mon | Tue | Wed | Thu | Fri |
|---|---|---|---|---|---|
| 00 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 01 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 02 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 03 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 04 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 05 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 06 | 0.1 / 0.2 / 0.3 | 0.2 / 0.2 / 0.29 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 07 | 0.2 / 0.2 / 0.2 | 0.2 / 0.2 / 0.2 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 08 | 0.1 / 0.2 / 0.3 | 0.1 / 0.2 / 0.3 | 0.2 / 0.2 / 0.2 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 09 | 0.1 / 0.2 / 0.2 | 0.1 / 0.2 / 0.2 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.1 / 0.2 / 0.3 |
| 10 | 0.2 / 0.2 / 0.2 | 0.1 / 0.2 / 0.3 | 0.1 / 0.2 / 0.2 | 0.2 / 0.2 / 0.3 | 0.1 / 0.2 / 0.3 |
| 11 | 0.2 / 0.2 / 0.2 | 0.1 / 0.2 / 0.22 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 12 | 0.2 / 0.2 / 0.2 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 13 | 0.1 / 0.2 / 0.2 | 0.2 / 0.2 / 0.3 | 0.1 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 14 | 0.1 / 0.2 / 0.2 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 15 | 0.2 / 0.2 / 0.2 | 0.2 / 0.2 / 0.3 | 0.1 / 0.2 / 0.2 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 16 | 0.1 / 0.2 / 0.2 | 0.1 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 17 | 0.1 / 0.2 / 0.2 | 0.1 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 18 | 0.1 / 0.2 / 0.2 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 19 | 0.2 / 0.2 / 0.2 | 0.2 / 0.2 / 0.2 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 |
| 20 (rollover: summer) | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.2 / 0.3 | 0.2 / 0.3 / 0.5 |
| 21 (rollover: summer, winter) | 0.2 / 0.2 / 0.3* | 0.2 / 0.2 / 0.3* | 0.2 / 0.2 / 0.3* | 0.2 / 0.2 / 0.3* | 0.2 / 0.2 / 0.3* |
| 22 (rollover: winter) | 0.3 / 0.4 / 0.5 | 0.3 / 0.3 / 0.4 | 0.3 / 0.4 / 0.5 | 0.3 / 0.3 / 0.4 | 0.2 / 0.2 / 0.3* |
| 23 | 0.2 / 0.3 / 0.3 | 0.2 / 0.3 / 0.3 | 0.2 / 0.3 / 0.3 | 0.2 / 0.3 / 0.3 | 0.2 / 0.2 / 0.3* |

Fallback cells (7): Mon 21:00 (83 min, 2 weeks), Tue 21:00 (79 min, 2 weeks), Wed 21:00 (80 min, 2 weeks), Thu 21:00 (93 min, 2 weeks), Fri 21:00 (101 min, 2 weeks), Fri 22:00 (0 min, 0 weeks), Fri 23:00 (0 min, 0 weeks).
- The 21 UTC cells Mon–Fri are thin because in summer that hour is rollover. Only the 2 winter weeks' regular minutes remain.
- Fri 22–23 UTC is after the close in both regimes.

## 4. Cheapest and most expensive hours

Ranking: regular cells with their own data, sorted by median, then p75, p90 and mean. The values are quantised to 0.1 pip, so many cells tie on the median and the mean decides.

**Cheapest:**

| cell (UTC) | median | p75 | p90 | mean | minutes | weeks |
|---|---:|---:|---:|---:|---:|---:|
| Mon 09:00 | 0.1 | 0.2 | 0.2 | 0.154 | 518 | 10 |
| Mon 17:00 | 0.1 | 0.2 | 0.2 | 0.155 | 525 | 10 |
| Mon 18:00 | 0.1 | 0.2 | 0.2 | 0.156 | 520 | 10 |
| Wed 10:00 | 0.1 | 0.2 | 0.2 | 0.157 | 527 | 10 |
| Wed 15:00 | 0.1 | 0.2 | 0.2 | 0.157 | 511 | 10 |

**Most expensive regular cells:**

| cell (UTC) | median | p75 | p90 | mean | minutes | weeks |
|---|---:|---:|---:|---:|---:|---:|
| Mon 22:00 | 0.3 | 0.4 | 0.5 | 0.319 | 464 | 8 |
| Wed 22:00 | 0.3 | 0.4 | 0.5 | 0.298 | 466 | 8 |
| Tue 22:00 | 0.3 | 0.3 | 0.4 | 0.280 | 454 | 8 |
| Thu 22:00 | 0.3 | 0.3 | 0.4 | 0.273 | 464 | 8 |
| Fri 20:00 | 0.2 | 0.3 | 0.5 | 0.280 | 526 | 10 |

- The most expensive times overall are the special segments, not regular cells: weekly_open_first_hour (median 1.5, p90 4.1) and rollover (median 0.9, p90 3).
- 22 UTC Mon–Thu is the most expensive regular hour. In summer it is 18:00–18:59 New York, the hour right after rollover.

## 5. Winter vs summer

- **Test:** an exact permutation test over week labels on regular hours. The statistic is the median over cells of winter − summer cell means.
- **Sample:** 2 winter weeks (2018/45.csv.gz, 2020/3.csv.gz) and 8 summer weeks.
- **Result:** statistic = -0.0362 pips, p = 0.2667 over 45 permutations. The smallest p this sample can give is 0.0222.
- **Decision:** not material (needs p ≤ 0.05 and |effect| ≥ 0.1 pips), so the hour table is pooled across regimes.
- **Where the real difference is:** the UTC hour of the rollover moves with DST. Anchoring rollover and the weekly open to New York time absorbs this.
- **Regime rows in §2:**
  - Winter rollover is similar to summer: measured median 1 vs 0.9.
  - The winter weekly-open first hour is lower (1.2 vs 1.65), but it comes from only 2 weeks.

## 6. Comparison with the fxcm_audit_53 spread_by_hour result

- **What that file is:** `data/fxcm/53.csv`, the week of 2019-12-29 to 2020-01-03 (Christmas and New Year, winter). It gives hour-of-day medians over all minutes, including zero and negative spreads.
- **How it was used:** only for comparison, not in the model.

| UTC hour | 53: minutes | 53: median | this sample, all minutes | this sample, positive only |
|---|---:|---:|---:|---:|
| 00 | 178 | 0.1 | 0.2 | 0.2 |
| 01 | 180 | 0.1 | 0.2 | 0.2 |
| 02 | 180 | 0.1 | 0.2 | 0.2 |
| 03 | 180 | 0.1 | 0.2 | 0.2 |
| 04 | 179 | 0.1 | 0.2 | 0.2 |
| 05 | 179 | 0.1 | 0.2 | 0.2 |
| 06 | 181 | 0.1 | 0.1 | 0.2 |
| 07 | 240 | 0.1 | 0.1 | 0.2 |
| 08 | 240 | 0.1 | 0.1 | 0.2 |
| 09 | 240 | 0.1 | 0.1 | 0.1 |
| 10 | 240 | 0.1 | 0.1 | 0.1 |
| 11 | 240 | 0.1 | 0.1 | 0.2 |
| 12 | 240 | 0.1 | 0.1 | 0.2 |
| 13 | 240 | 0.1 | 0.1 | 0.2 |
| 14 | 240 | 0.1 | 0.1 | 0.2 |
| 15 | 240 | 0.1 | 0.1 | 0.2 |
| 16 | 240 | 0.1 | 0.1 | 0.2 |
| 17 | 240 | 0.1 | 0.1 | 0.2 |
| 18 | 240 | 0.1 | 0.1 | 0.2 |
| 19 | 182 | 0.1 | 0.2 | 0.2 |
| 20 | 180 | 0.1 | 0.2 | 0.2 |
| 21 | 177 | 0.2 | 0.8 | 0.8 |
| 22 | 157 | 2.5 | 0.3 | 0.3 |
| 23 | 177 | 0.2 | 0.2 | 0.2 |

- **Agreement:** computed the same way (all minutes), this sample gives 0.1–0.2 pips at most hours, close to the 53 week's 0.1.
- **Rollover peak:** it sits at 22 UTC in the 53 week (winter) but at 21 UTC in this sample (mostly summer). This matches the New York-anchored rollover.

## 7. Sample limitations

- **Coverage:**
  - Only 10 weeks, i.e. 10 observations per hour-of-week cell.
  - Of these, 7 weeks are from 2018–2019, 1 from 2020, and 1 each from 2024 and 2025. Nothing covers 2021–2023 or 2026.
  - Spreads differ between years more than between regimes: the 2025 week has the highest level and 2020/w3 the lowest.
- **Week selection:** the weeks were chosen to test DST timing, not to represent typical conditions:
  - 6 of the 8 summer weeks lie in the US-only DST windows of March and late October.
  - There are only 2 winter weeks, so winter-specific values are not supported.
- **Events:** no holidays, central-bank days or flash events were targeted. The p90 values do not describe tail risk on such days.
- **Which spread this is:**
  - FXCM's spread is not the cost at the broker behind HistData, nor the cost at any broker a strategy would use.
  - It is the spread at each minute's close only: no intra-minute spread, slippage, commission or swap.
- **Zero and negative spreads (2018–2020):** these mean the bid and ask closes are not always simultaneous quotes, so close-to-close spreads in those years are approximate.
- **Terms of use:** FXCM's reply allows personal use. The minute-level table (`spread_minutes.parquet`) stays in the gitignored `data/` folder.

## 8. Total round-trip cost per trade (pips)

Cost per round trip = spread(percentile) + commission + slippage, from `CostModel.cost_for(timestamp_utc, percentile=None)`.

The commission and slippage are **broker-dependent assumptions, not measured from data**. They are set in `config/cost_model_v1.yaml` under `trading_costs` and should be replaced with the actual broker's terms:

- `spread_percentile: p75` (default)
- `commission_pips_round_trip: 0.6`
- `slippage_pips: 0.2` (per round trip)

That makes the fixed part 0.8 pips per trade. The spread is FXCM's, as in §7.

`cost_for` returns three flags: `is_rollover`, `is_weekly_open` and `is_market_closed`. A backtest can use them to decide whether to trade or close positions at those times. In market-closed time the value is the all-hours fallback, i.e. a placeholder, not a real price.

**By segment:**

| segment | spread median / p75 / p90 | total at median | total at p75 (default) | total at p90 |
|---|---|---:|---:|---:|
| regular, fallback cells / market closed | 0.2 / 0.2 / 0.3 | 1 | 1 | 1.1 |
| rollover | 0.9 / 1.9 / 3 | 1.7 | 2.7 | 3.8 |
| weekly_open_first_hour | 1.5 / 2.4 / 4.1 | 2.3 | 3.2 | 4.9 |
| weekly_open_rest | 0.2 / 0.3 / 0.4 | 1 | 1.1 | 1.2 |

**Regular hours: total at the default p75, UTC weekday × hour**

`*` = fallback cell. The rollover window and the weekly open are not in this grid; see the segment table above.

| UTC hour | Mon | Tue | Wed | Thu | Fri |
|---|---:|---:|---:|---:|---:|
| 00 | 1 | 1 | 1 | 1 | 1 |
| 01 | 1 | 1 | 1 | 1 | 1 |
| 02 | 1 | 1 | 1 | 1 | 1 |
| 03 | 1 | 1 | 1 | 1 | 1 |
| 04 | 1 | 1 | 1 | 1 | 1 |
| 05 | 1 | 1 | 1 | 1 | 1 |
| 06 | 1 | 1 | 1 | 1 | 1 |
| 07 | 1 | 1 | 1 | 1 | 1 |
| 08 | 1 | 1 | 1 | 1 | 1 |
| 09 | 1 | 1 | 1 | 1 | 1 |
| 10 | 1 | 1 | 1 | 1 | 1 |
| 11 | 1 | 1 | 1 | 1 | 1 |
| 12 | 1 | 1 | 1 | 1 | 1 |
| 13 | 1 | 1 | 1 | 1 | 1 |
| 14 | 1 | 1 | 1 | 1 | 1 |
| 15 | 1 | 1 | 1 | 1 | 1 |
| 16 | 1 | 1 | 1 | 1 | 1 |
| 17 | 1 | 1 | 1 | 1 | 1 |
| 18 | 1 | 1 | 1 | 1 | 1 |
| 19 | 1 | 1 | 1 | 1 | 1 |
| 20 | 1 | 1 | 1 | 1 | 1.1 |
| 21 | 1* | 1* | 1* | 1* | 1* |
| 22 | 1.2 | 1.1 | 1.2 | 1.1 | 1* |
| 23 | 1.1 | 1.1 | 1.1 | 1.1 | 1* |

- Check: `cost_for(2021-07-14 12:00 UTC)` = 1 pips, the same as the Wed 12 cell above.
- Config SHA-256: the manifest records `d7328127749ebf8a…` at build time. The `trading_costs` block was added after the build, so the current config SHA-256 is `e1085e9e5b297e32…`.
- The model tables do not use `trading_costs`, so the files in `data/processed/cost_model/v1/` were not rebuilt.
