# FXCM batch 1: preparation (nothing downloaded)

Created 2026-10-26 09:00 UTC. **Preparation only.**
- No candle file was requested or downloaded, and `data/reference/` was not created.
- No existing data, Parquet file, report or planned list was changed.
- The timezone policy stays C6 (no conversion).

Files in this folder:
- `candidate_urls.csv` — the five URLs, with availability and the planned destination for each
- `manifest_template.csv` — the empty manifest schema to be filled at fetch time
- `source_hashes_check.txt` — the before/after hash check and the test result

## 1. URL pattern (documented)

The FXCM MarketData README was re-read on 2026-10-26 (raw GitHub; documentation only):
- Pattern: `https://candledata.fxcorporate.com/{periodicity}/{instrument}/{year}/{int of week of year}.csv.gz`
- Values used: periodicity `m1`, instrument `EURUSD`
- Example given: `https://candledata.fxcorporate.com/m1/EURUSD/2020/1.csv.gz`
- Weeks: "1 to 52/53". Years listed: 2017, 2018, 2019, 2020.

**The README does not define "week of year".**
- Its example script uses Python `isocalendar()`, but the server serves week 53 for years that have only 52 ISO weeks.
- The README's own example, 2020/1, returned **404** in the 2026-10-22 probe.

So the week numbering is **not verified from documentation**. Instead, every file's contents will be checked (§3).

For these five weeks, ISO numbering and the Sunday-start alternative point to the same trading week. The probe's Last-Modified timestamps are also consistent with that week: for example, 2018/43 was stamped Sun 2018-10-28 22:03 GMT, right after the Oct 22–26 week. That is supporting evidence, not proof.

## 2. Candidate URLs and availability

| Year/week | URL | Intended week (Mon) | In planned list | Probe 2026-10-22 |
|---|---|---|---|---|
| 2018/12 | https://candledata.fxcorporate.com/m1/EURUSD/2018/12.csv.gz | 2018-03-19 | Yes (A3), available | 206, 146,996 B |
| 2018/43 | https://candledata.fxcorporate.com/m1/EURUSD/2018/43.csv.gz | 2018-10-22 | Yes (A3, mislabelled US-only; actually both-summer), available | 206, 145,937 B |
| 2018/44 | https://candledata.fxcorporate.com/m1/EURUSD/2018/44.csv.gz | 2018-10-29 | Yes (A3), available | 206, 144,833 B |
| 2019/11 | https://candledata.fxcorporate.com/m1/EURUSD/2019/11.csv.gz | 2019-03-11 | Yes (B0), available | 206, 138,756 B |
| 2019/44 | https://candledata.fxcorporate.com/m1/EURUSD/2019/44.csv.gz | 2019-10-28 | **NO: outside the original list** | 206, 132,928 B (probe only) |

The total is 709,450 bytes compressed. Availability may have changed since the probe, and 2018/12 shows a later revision date (2018-03-29).

## 3. Content checks before any file is used

Files are treated as untrusted. The checks run from a script stored outside the data folder, with `python -I` and only stdlib `gzip`/pandas. No decompressed copy is written into `data/`.

1. **Integrity:**
   - the gzip stream decompresses completely;
   - SHA-256 of the `.gz` exactly as received;
   - size compared with the probe value, where a difference is noted rather than treated as failure.
2. **Schema:**
   - the header must be exactly `DateTime,BidOpen,…,AskClose`, the same as `53.csv`;
   - parsing uses the existing strict reader `read_fxcm_csv`, which applies the `MM/DD/YYYY HH:MM:SS.fff` regex with no timezone applied (pandas reads `.gz` directly);
   - the date order is confirmed (day field > 12 seen).
3. **Date coverage**, with labels taken as written and nothing shifted:
   - first label: on the Sunday before the intended Monday, between 20:00 and 23:59;
   - last label: on the Friday of the intended week, between 20:00 and 23:59;
   - every label within [Sunday 00:00, Saturday 00:00) of the intended week;
   - five weekdays present.
   - Outcome: `coverage_status` = `ok`, or `mismatch` with the observed range. A mismatched file is **kept on disk but excluded**. It is never re-labelled or renamed, and is not substituted with another week without new approval.
4. **Quality:** run the existing `fxcm_audit` checks: duplicates, ordering, gaps, OHLC, bid/ask and spreads.

Before fetching, I'll add a small test confirming that `read_fxcm_csv` reads a synthetic `.csv.gz`. Nothing in the code needs to change for that.

## 4. Destination and manifest (planned, not created)

```
data/reference/fxcm/
  m1/EURUSD/2018/12.csv.gz   (as received; mirrors the URL path)
  m1/EURUSD/2018/43.csv.gz
  m1/EURUSD/2018/44.csv.gz
  m1/EURUSD/2019/11.csv.gz
  m1/EURUSD/2019/44.csv.gz
  MANIFEST.csv               (one row per file; columns as manifest_template.csv)
  SHA256SUMS.txt             (shasum -a 256 format)
  TERMS_NOTE.md              (the FXCM terms basis you confirm; your record of the email)
```

**Fetch rules:**
- **No overwriting.** Abort if `data/reference/fxcm/` already exists; each file is written once, and only if absent.
- **Download method:**
  - `curl --fail --proto =https --max-filesize 2M`, one request per file, with a short pause between requests;
  - written to a `.part` file and renamed only after the gzip check passes;
  - HTTP headers saved into the manifest.
- **Separation:** no file goes into the HistData folders, and nothing is merged with them, converted or filled.
- **Afterwards:** re-verify the hashes of all existing data and Parquet files.

## 5. Unresolved questions

1. **Terms:** FXCM's email is still not saved in the project, and the EULA text is unread. All five weeks are inside the README years 2017–2020, but your confirmation of personal research use is needed first.
2. **2019/44 is not in the planned list.** It needs your explicit approval as an addition.
3. **Week numbering is undocumented.** It is consistent for these five weeks, but only content checks can confirm it.
4. **The README example 2020/1 returns 404**, so documentation and server don't fully agree.
5. **Price side and revisions:** whether the prices are bid, ask or mid, and whether files are revised, is undocumented. The 2018/12 file was modified 10 days after its week.

## 6. Safety and tests

See `source_hashes_check.txt`.
