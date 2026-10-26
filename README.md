# trade_analyst: EURUSD M1 research

Research foundation for EURUSD quantitative work. **Current stage: data inventory and quality audit only.** No models, strategies, backtests or live trading.

## Layout
```
data/HISTDATA_COM_ASCII_EURUSD_M1*/   raw HistData M1 CSV + TXT status reports (read-only)
eurusd_{1m,15m,1h,4h}.parquet         existing derived files (unverified, read-only)
config/research.yaml                  paths, timezone status, audit thresholds
src/data/inventory.py                 file inventory, HistData TXT report parser
src/data/audit.py                     read-only quality audit + report writer
tests/                                unit tests on small synthetic fixtures
reports/data_audit_<UTC stamp>/       one directory per audit run (never overwritten)
```

## Setup
Requires Python 3.11+. The project uses a local virtual environment; nothing is installed globally.
```bash
cd trade_analyst   # repository root
~/.local/bin/python3.11 -m venv .venv            # or any Python >= 3.11
.venv/bin/python -m pip install -r requirements.txt
```

## Run
```bash
.venv/bin/python -m pytest                       # unit tests (synthetic data only)
.venv/bin/python -m src.data.inventory           # print raw-file inventory
.venv/bin/python -m src.data.audit               # full audit -> reports/data_audit_<stamp>/
```
The audit hashes every source file (raw CSV/TXT and Parquet) before and after it runs, and exits with an error if anything changed.

## Data rules
- Raw and derived market data are never modified, moved or renamed by project code.
- Timestamps are kept **naive, on the source clock**. The source timezone is **unverified** (see the latest audit report, section 7). No code converts or localises timestamps.
- The audit reports duplicates, ordering problems, OHLC violations and gaps without repairing anything. Cleaning will be a separate, explicit step.
- A verified backup of the market data exists at `../EURUSD_backup_2026-10-22/` (`SHA256SUMS.txt` inside).
