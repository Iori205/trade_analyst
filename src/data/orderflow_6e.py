"""Audit the raw Databento 6E files and build order flow bars v1. Local files only; no API calls.

The 2019 trades come from two files that overlap at the join. Only that overlap is removed.
Repeated (ts_event, price, size, side, sequence) rows inside one file are separate fills of one
match event and are kept: the merged count equals the full-year count Databento quoted.

Bars are on the UTC clock, labelled by start time, and cover [start, start + timeframe).
A trade belongs to the bar of its ts_event. An interval without trades has no bar.

Run:
    .venv/bin/python -m src.data.orderflow_6e
    .venv/bin/python -m src.data.orderflow_6e --out <dir> --no-report   # rebuild only, for a hash check
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import warnings
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd
import yaml

from src.data.inventory import sha256_file
from src.data.splits import DEFAULT_SPLITS, guard_range, load_splits, read_range

CONFIG = Path("config/orderflow_6e_v1.yaml")
TIMEFRAMES = {"M15": 15, "H1": 60}
YEARS = range(2019, 2024)
KEY = ["ts_event", "price", "size", "side", "sequence"]
TRADE_FIELDS = ["ts_event", "ts_recv", "price", "size", "side", "sequence", "instrument_id", "flags"]
PRICE_SCALE = 1e9
PIP = 1e-4
NS_PER_MIN = 60_000_000_000
SPIKE_FUT, SPIKE_SPOT = 0.005, 0.001  # 1-minute log return: 6E moved this much while spot stayed under this
SCRIPTS = ["src/data/orderflow_6e.py", "src/data/splits.py", "config/orderflow_6e_v1.yaml"]
PART_FILE = "trades/2019.dbn.zst.part"
TAIL_FILE = "trades/2019_tail_from_20191122T0900Z.dbn.zst"
OHLCV_FILE = "ohlcv-1m/2015-2023.dbn.zst"
SPOT_FILE = "eurusd_m1_utc.parquet"


def read_dbn(path: Path) -> np.ndarray:
    """All complete records of a DBN file; a truncated last record is left out."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*truncated.*")
        chunks = list(db.DBNStore.from_file(path).to_ndarray(count=2_000_000))
    return np.concatenate(chunks)


def trades_frame(records: np.ndarray) -> pd.DataFrame:
    out = {f: records[f] for f in TRADE_FIELDS}
    out["side"] = np.char.decode(records["side"], "ascii")
    df = pd.DataFrame(out)
    return df.astype({"ts_event": "int64", "ts_recv": "int64", "price": "int64", "size": "int64"})


def merge_overlap(part: pd.DataFrame, tail: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """part + tail without the rows they share at the join; returns the merged rows and the counts.

    Rows match on KEY plus their occurrence number within KEY, so repeated fills survive and a
    part row is dropped only when the tail really has that copy.
    """
    start, end = tail["ts_event"].min(), part["ts_event"].max()
    p_win, t_win = part[part["ts_event"] >= start], tail[tail["ts_event"] <= end]
    p_key = p_win[KEY].assign(n=p_win.groupby(KEY, sort=False).cumcount())
    t_key = t_win[KEY].assign(n=t_win.groupby(KEY, sort=False).cumcount())
    merged = p_key.reset_index().merge(t_key, on=[*KEY, "n"], how="left", indicator=True)
    drop = merged.loc[merged["_merge"] == "both", "index"]
    keep = part.drop(index=drop)
    out = pd.concat([keep, tail], ignore_index=True).sort_values("ts_event", kind="stable", ignore_index=True)
    stats = {"part_rows": len(part), "tail_rows": len(tail), "overlap_part_rows": len(p_win),
             "overlap_tail_rows": len(t_win), "removed": len(drop), "merged_rows": len(out),
             "overlap_start_ns": int(start), "overlap_end_ns": int(end),
             "part_only_in_overlap": len(p_win) - len(drop), "tail_only_in_overlap": len(t_win) - len(drop)}
    return out, stats


def order_breaks(frames: list[pd.DataFrame], column: str) -> int:
    return sum(int((np.diff(f[column]) < 0).sum()) for f in frames)


def load_year(raw: Path, year: int) -> tuple[pd.DataFrame, dict | None, dict]:
    """Trades of one year in ts_event order, the merge counts (2019), and the order breaks per raw file."""
    if year == 2019:
        part, tail = trades_frame(read_dbn(raw / PART_FILE)), trades_frame(read_dbn(raw / TAIL_FILE))
        breaks = {c: order_breaks([part, tail], c) for c in ("ts_event", "ts_recv")}
        df, stats = merge_overlap(part, tail)
        return df, stats, breaks
    files = sorted((raw / "trades" / str(year)).glob("*.trades.dbn.zst"))
    frames = [trades_frame(read_dbn(f)) for f in files]
    breaks = {c: order_breaks(frames, c) for c in ("ts_event", "ts_recv")}
    # A month file can end a few ms into the next month, so the sort must span the whole year
    df = pd.concat(frames, ignore_index=True).sort_values("ts_event", kind="stable", ignore_index=True)
    return df, None, breaks


def build_bars(trades: pd.DataFrame, minutes: int, side_map: dict, degraded_days=()) -> pd.DataFrame:
    """Order flow bars from trades sorted by ts_event."""
    ts = trades["ts_event"].to_numpy(dtype="int64")
    if len(ts) == 0:
        raise ValueError("no trades")
    if (np.diff(ts) < 0).any():
        raise ValueError("trades must be sorted by ts_event")
    width = minutes * NS_PER_MIN
    bin_start = ts - ts % width
    first = np.flatnonzero(np.r_[True, bin_start[1:] != bin_start[:-1]])
    last = np.r_[first[1:], len(ts)] - 1
    sum_at = lambda values: np.add.reduceat(values, first)

    px = trades["price"].to_numpy(dtype="int64")
    size = trades["size"].to_numpy(dtype="int64")
    side = trades["side"].to_numpy()
    ids = trades["instrument_id"].to_numpy(dtype="int64")

    buy = sum_at(size * (side == side_map["buy"]))
    sell = sum_at(size * (side == side_map["sell"]))
    volume = sum_at(size)
    id_first, id_last = ids[first], ids[last]
    changed = np.r_[False, ids[1:] != ids[:-1]]  # True on the first trade of a new contract
    changes_in_bar = sum_at(changed.astype("int64")) - changed[first].astype("int64")
    roll_at_open = changed[first]                # contract changed exactly at this bar's start or in the gap before

    bars = pd.DataFrame({
        "bar_start_utc": pd.to_datetime(bin_start[first], unit="ns", utc=True),
        "open": px[first] / PRICE_SCALE,
        "high": np.maximum.reduceat(px, first) / PRICE_SCALE,
        "low": np.minimum.reduceat(px, first) / PRICE_SCALE,
        "close": px[last] / PRICE_SCALE,
        "vwap": sum_at(px * size) / volume / PRICE_SCALE,
        "volume": volume,
        "buy_volume": buy,
        "sell_volume": sell,
        "unknown_volume": volume - buy - sell,
        "delta": buy - sell,
        "delta_ratio": (buy - sell) / volume,
        "trade_count": last - first + 1,
        "instrument_id_first": id_first,
        "instrument_id_last": id_last,
        "roll_flag": (changes_in_bar > 0) | roll_at_open,
        "roll_inside_bar": changes_in_bar > 0,
    })
    days = pd.DatetimeIndex(pd.to_datetime([str(d) for d in degraded_days], utc=True))
    bars["degraded_flag"] = bars["bar_start_utc"].dt.normalize().isin(days)
    return bars


def add_returns(bars: pd.DataFrame) -> pd.DataFrame:
    """Close-to-close log return; empty when the two closes are not on one contract."""
    out = bars.copy()
    ret = np.log(out["close"] / out["close"].shift(1))
    out["ret_log"] = ret.where(~out["roll_flag"])
    return out


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    with open(path, "xb") as handle:  # "x": never overwrite
        df.to_parquet(handle, index=False, engine="pyarrow", compression="snappy")


def split_bars(bars: pd.DataFrame, splits: dict) -> dict[str, pd.DataFrame]:
    guard_range(bars["bar_start_utc"].min(), bars["bar_start_utc"].max() + pd.Timedelta(hours=1), splits)
    out = {}
    for name, s in splits.items():
        part = bars[(bars["bar_start_utc"] >= s.start) & (bars["bar_start_utc"] < s.end)]
        if len(part):
            out[name] = add_returns(part.reset_index(drop=True))
    return out


def hash_inputs(raw: Path, manifest: dict) -> dict[str, str]:
    """Hash every raw file with a manifest hash; raises when one differs."""
    expected = {PART_FILE: manifest["partial"]["trades_2019"]["sha256"]}
    expected.update({f["file"]: f["sha256"] for f in manifest["files"].values()})
    for year, job in manifest["batch_jobs"].items():
        expected.update({f"trades/{year}/{n}": f["sha256"] for n, f in job["files"].items()})
    found = {}
    for rel, sha in sorted(expected.items()):
        found[rel] = sha256_file(raw / rel)
        if found[rel] != sha:
            raise AssertionError(f"{rel} does not match the manifest")
    return found


# Audit ---------------------------------------------------------------------------------------

def gap_stats(ts_ns: np.ndarray, year_of_start: np.ndarray | None = None) -> tuple[dict, pd.DataFrame]:
    """Gaps between neighbouring timestamps, by size; long weekday gaps come back as rows."""
    start = pd.to_datetime(ts_ns[:-1], unit="ns", utc=True)
    end = pd.to_datetime(ts_ns[1:], unit="ns", utc=True)
    mins = (ts_ns[1:] - ts_ns[:-1]) / NS_PER_MIN
    weekend = (start.dayofweek >= 4) & (mins >= 24 * 60)
    long = (mins >= 120) & ~weekend
    counts = {"5-29m": int(((mins >= 5) & (mins < 30)).sum()), "30-59m": int(((mins >= 30) & (mins < 60)).sum()),
              "60-119m": int(((mins >= 60) & (mins < 120)).sum()), "2h+ not weekend": int(long.sum()),
              "weekend": int(weekend.sum())}
    rows = pd.DataFrame({"from_utc": start[long], "to_utc": end[long], "hours": np.round(mins[long] / 60, 2)})
    return counts, rows


def ohlcv_frame(records: np.ndarray) -> pd.DataFrame:
    df = pd.DataFrame({k: records[k] for k in ("ts_event", "open", "close", "volume", "instrument_id")})
    return df.astype({"ts_event": "int64", "volume": "int64"})


def tick_check(trades: pd.DataFrame) -> dict:
    """Which side trades on upticks and downticks, within one contract."""
    p, ids = trades["price"].to_numpy(), trades["instrument_id"].to_numpy()
    side = trades["side"].to_numpy()[1:]
    same = ids[1:] == ids[:-1]
    up, down = (p[1:] > p[:-1]) & same, (p[1:] < p[:-1]) & same
    return {f"{name}_{s}": int((side[m] == s).sum()) for name, m in (("up", up), ("down", down)) for s in "ABN"}


def roll_table(ohlcv: pd.DataFrame, spot: pd.Series) -> pd.DataFrame:
    """Every contract change in ohlcv-1m. Jump = first open on the new contract - last close on the old.

    The two prices are minutes apart, so the spot move between them is taken out to estimate the basis.
    last_weekday_vol_ratio: volume of the last weekday before the roll date, over the median weekday
    of the 20 weekdays ending 10 weekdays before the roll.
    """
    ids = ohlcv["instrument_id"].to_numpy()
    times = pd.to_datetime(ohlcv["ts_event"].to_numpy(), unit="ns", utc=True)
    daily = pd.Series(ohlcv["volume"].to_numpy(), index=times).groupby(times.floor("D")).sum()
    daily = daily[daily.index.dayofweek < 5]
    rows = []
    for i in np.flatnonzero(ids[1:] != ids[:-1]) + 1:
        old, new = ohlcv.iloc[i - 1], ohlcv.iloc[i]
        t_old = pd.Timestamp(int(old["ts_event"]), unit="ns", tz="UTC")
        t_new = pd.Timestamp(int(new["ts_event"]), unit="ns", tz="UTC")
        jump = (new["open"] - old["close"]) / PRICE_SCALE / PIP
        s_old, s_new = spot.asof(t_old), spot.asof(t_new)
        spot_move = (s_new - s_old) / PIP
        before = daily[daily.index < t_new.floor("D")]
        rows.append({"old_last_bar_utc": t_old, "new_first_bar_utc": t_new, "old_id": int(old["instrument_id"]),
                     "new_id": int(new["instrument_id"]), "minutes_apart": (t_new - t_old).total_seconds() / 60,
                     "jump_pips": round(jump, 1), "spot_move_pips": round(spot_move, 1),
                     "basis_est_pips": round(jump - spot_move, 1),
                     "last_weekday_vol_ratio": round(before.iloc[-1] / before.iloc[-30:-10].median(), 2)})
    return pd.DataFrame(rows)


def spot_compare(ohlcv: pd.DataFrame, spot_m1: pd.DataFrame, lags=range(-5, 6)) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pearson r of 1-minute returns by year and lag. Positive lag: spot is `lag` minutes after 6E.

    A return needs two neighbouring minutes, on one contract for 6E. Spot keeps one copy of each minute.
    """
    fut = pd.DataFrame({"close": ohlcv["close"].to_numpy() / PRICE_SCALE, "id": ohlcv["instrument_id"].to_numpy()},
                       index=pd.to_datetime(ohlcv["ts_event"].to_numpy(), unit="ns", utc=True))
    r_fut = np.log(fut["close"]).diff()
    ok = (fut.index.to_series().diff() == pd.Timedelta(minutes=1)) & (fut["id"] == fut["id"].shift(1))
    r_fut = r_fut[ok.to_numpy()]
    spot = spot_m1.sort_values("timestamp_utc", kind="stable").drop_duplicates("timestamp_utc").set_index("timestamp_utc")
    r_spot = np.log(spot["close"]).diff()
    r_spot = r_spot[spot.index.to_series().diff() == pd.Timedelta(minutes=1)]
    low_quality = spot.index[spot["low_quality_period"].astype(bool)]

    rows, best = [], []
    spike = lambda both: (both["f"].abs() >= SPIKE_FUT) & (both["s"].abs() < SPIKE_SPOT)
    groups = [(str(y), r_fut[r_fut.index.year == y]) for y in sorted(set(r_fut.index.year))]
    groups.append(("2023 without low_quality_period", r_fut[(r_fut.index.year == 2023) & ~r_fut.index.isin(low_quality)]))
    for name, f in groups:
        by_lag = {}
        for lag in lags:
            s = r_spot.copy()
            s.index = s.index - pd.Timedelta(minutes=lag)
            both = pd.concat([f.rename("f"), s.rename("s")], axis=1, join="inner").dropna()
            by_lag[lag] = float(both["f"].corr(both["s"]))
            if lag == 0:
                n, at_zero = len(both), both
        rows.append({"period": name, **{f"lag_{k:+d}": round(v, 4) for k, v in by_lag.items()}})
        top = max(by_lag, key=by_lag.get)
        best.append({"period": name, "pairs": n, "r_lag0": round(by_lag[0], 4), "best_lag": top,
                     "r_best": round(by_lag[top], 4),
                     "spearman_lag0": round(float(at_zero["f"].corr(at_zero["s"], method="spearman")), 4),
                     "spikes": int(spike(at_zero).sum()),
                     "r_lag0_no_spikes": round(float(at_zero[~spike(at_zero)]["f"].corr(at_zero[~spike(at_zero)]["s"])), 4)})
    return pd.DataFrame(best), pd.DataFrame(rows)


def md_table(df: pd.DataFrame) -> str:
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(map(str, row)) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def git_state(root: Path) -> dict:
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", *SCRIPTS],
                           capture_output=True, text=True)
    return {"git_commit": head.stdout.strip() or None, "git_dirty": bool(dirty.stdout.strip())}


def run(root: Path, out_dir: Path | None = None, report: bool = True) -> dict:
    root = Path(root)
    cfg = yaml.safe_load((root / CONFIG).read_text(encoding="utf-8"))
    raw = root / cfg["raw_dir"]
    out = root / (out_dir or cfg["output_dir"])
    if out.exists():
        raise FileExistsError(f"{out} exists; versions are never overwritten")
    manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    side_map = cfg["side_map"]
    degraded = sorted(str(d) for d in cfg["degraded_days"])
    splits = load_splits(root / DEFAULT_SPLITS)
    raw_hashes = hash_inputs(raw, manifest)
    manifest_sha = sha256_file(raw / "manifest.json")

    ohlcv = ohlcv_frame(read_dbn(raw / OHLCV_FILE))
    ohlcv_ts = ohlcv["ts_event"].to_numpy()
    ohlcv_minute = pd.Series(ohlcv["volume"].to_numpy(), index=ohlcv_ts)

    audit = {"years": {}, "tick": {}, "gaps_trades": {}, "merge": None}
    gap_rows, flags_seen, degraded_rows = [], {}, []
    collected = {tf: [] for tf in TIMEFRAMES}
    for year in YEARS:
        trades, merge, breaks = load_year(raw, year)
        expected = (manifest["batch_jobs"][str(year)]["expected_records"] if year != 2019 else
                    next(a["expected_records"] for a in manifest["attempts"] if a["id"] == "trades_2019"))
        if year == 2019:
            audit["merge"] = merge
        ts = trades["ts_event"].to_numpy()
        sides = trades["side"].value_counts().to_dict()
        vol = trades.groupby("side")["size"].sum().to_dict()
        recv = trades["ts_recv"].to_numpy()
        m1 = trades.groupby(ts - ts % NS_PER_MIN)["size"].sum()
        m1_recv = trades.groupby(recv - recv % NS_PER_MIN)["size"].sum()
        y_ohlcv = ohlcv_minute[(ohlcv_ts >= m1.index.min()) & (ohlcv_ts <= m1.index.max())]
        joined = pd.concat([m1.rename("t"), y_ohlcv.rename("o")], axis=1).fillna(0)
        joined_recv = pd.concat([m1_recv.rename("t"), y_ohlcv.rename("o")], axis=1).fillna(0)
        audit["years"][year] = {
            "rows": len(trades), "expected": expected, "ts_event_order_breaks": breaks["ts_event"],
            "ts_recv_order_breaks": breaks["ts_recv"],
            "key_repeats": int(trades.duplicated(KEY).sum()),
            "first": str(pd.Timestamp(int(ts[0]), unit="ns")), "last": str(pd.Timestamp(int(ts[-1]), unit="ns")),
            "A": sides.get("A", 0), "B": sides.get("B", 0), "N": sides.get("N", 0),
            "vol_A": int(vol.get("A", 0)), "vol_B": int(vol.get("B", 0)), "vol_N": int(vol.get("N", 0)),
            "size_zero": int((trades["size"] == 0).sum()),
            "minutes": len(joined), "minutes_differ_ts_event": int((joined["t"] != joined["o"]).sum()),
            "minutes_differ_ts_recv": int((joined_recv["t"] != joined_recv["o"]).sum()),
            "ts_recv_before_ts_event": int((recv < ts).sum()), "min_recv_minus_event_ms": round(float((recv - ts).min()) / 1e6, 1),
            "volume_trades": int(joined["t"].sum()), "volume_ohlcv": int(joined["o"].sum()),
        }
        for flag, n in trades["flags"].value_counts().items():
            flags_seen[int(flag)] = flags_seen.get(int(flag), 0) + int(n)
        audit["tick"][year] = tick_check(trades)
        audit["gaps_trades"][year], rows = gap_stats(ts)
        gap_rows.append(rows)
        day = pd.to_datetime(ts, unit="ns", utc=True).strftime("%Y-%m-%d")
        by_day = trades.groupby(day)["size"].agg(["size", "sum"])
        for d in degraded:
            if d in by_day.index:
                month = by_day[by_day.index.str.startswith(d[:7])]
                degraded_rows.append({"date": d, "trades": int(by_day.loc[d, "size"]), "volume": int(by_day.loc[d, "sum"]),
                                      "volume / month median day": round(by_day.loc[d, "sum"] / month["sum"].median(), 2)})
            elif d[:4] == str(year):
                degraded_rows.append({"date": d, "trades": 0, "volume": 0, "volume / month median day": 0.0})
        for tf, minutes in TIMEFRAMES.items():
            collected[tf].append(build_bars(trades, minutes, side_map, degraded))
        del trades

    outputs, bars_summary, side_corr = {}, {}, {}
    out.mkdir(parents=True, exist_ok=False)
    for tf in TIMEFRAMES:
        bars = pd.concat(collected[tf], ignore_index=True)
        for name, frame in split_bars(bars, splits).items():
            path = out / f"orderflow_6e_{tf.lower()}_{name}.parquet"
            write_parquet(frame, path)
            outputs[path.name] = {"timeframe": tf, "split": name, "rows": len(frame), "sha256": sha256_file(path)}
            bars_summary[f"{tf}/{name}"] = {
                "bars": len(frame), "trades": int(frame["trade_count"].sum()), "volume": int(frame["volume"].sum()),
                "roll_flag": int(frame["roll_flag"].sum()), "roll_inside_bar": int(frame["roll_inside_bar"].sum()),
                "degraded_flag": int(frame["degraded_flag"].sum()),
                "ret_log_empty": int(frame["ret_log"].isna().sum()),
                "first": str(frame["bar_start_utc"].min()), "last": str(frame["bar_start_utc"].max())}
            valid = frame.dropna(subset=["ret_log"])
            years = valid["bar_start_utc"].dt.year
            for y, g in valid.groupby(years):
                side_corr.setdefault(tf, {})[int(y)] = round(float(g["delta_ratio"].corr(g["ret_log"])), 4)

    if raw_hashes != hash_inputs(raw, manifest) or sha256_file(raw / "manifest.json") != manifest_sha:
        raise AssertionError("a raw file changed during the build")
    (out / "SHA256SUMS.txt").write_text("".join(f"{o['sha256']}  {n}\n" for n, o in sorted(outputs.items())))
    bar_manifest = {
        "dataset": "orderflow_6e", "version": out.name,
        "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input": {"path": cfg["raw_dir"], "manifest_sha256": manifest_sha, "files": raw_hashes,
                  "symbol": manifest["symbol"], "dataset": manifest["dataset"]},
        "handling": {
            "label": "bar start time, UTC; bar = [start, start + timeframe); trade time = ts_event",
            "side_map": side_map,
            "side_note": "A = sell aggressor, B = buy aggressor; differs from buy=A in prompts/next.md, see the report",
            "volume": "contracts; volume = buy_volume + sell_volume + unknown_volume (side N)",
            "delta_ratio": "delta / volume, with side N in volume",
            "roll_flag": "bar with a contract change inside it, or the first bar on a new contract",
            "roll_inside_bar": "the strict case only: the change is inside the bar",
            "ret_log": "ln(close / previous bar close) within a split; empty on roll_flag bars and the first bar",
            "degraded_flag": "bar_start_utc date is a degraded day; bars kept",
            "empty_intervals": "no bar",
            "2019_merge": "overlap of .part and tail removed; repeated fills inside a file kept",
            "low_quality_period": "EURUSD spot flag; not applied to 6E",
        },
        "degraded_days": degraded, "splits_config_sha256": sha256_file(root / DEFAULT_SPLITS),
        "outputs": outputs, "summary": bars_summary, "merge_2019": audit["merge"], **git_state(root),
        "scripts_sha256": {s: sha256_file(root / s) for s in SCRIPTS},
    }
    (out / "manifest.json").write_text(json.dumps(bar_manifest, indent=2) + "\n", encoding="utf-8")

    result = {"outputs": outputs, "bars_summary": bars_summary}
    if report:
        result["report"] = str(write_report(root, cfg, manifest, ohlcv, splits, audit, gap_rows, flags_seen,
                                            degraded_rows, bars_summary, side_corr, degraded))
    return result


def write_report(root, cfg, manifest, ohlcv, splits, audit, gap_rows, flags_seen, degraded_rows,
                 bars_summary, side_corr, degraded) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rep = root / "reports" / f"orderflow_6e_audit_{stamp}"
    rep.mkdir(parents=True, exist_ok=False)
    spot_m1 = read_range(root / cfg["spot_dir"] / SPOT_FILE, pd.Timestamp("2015-01-01", tz="UTC"),
                         pd.Timestamp("2024-01-01", tz="UTC"), splits, "timestamp_utc",
                         ["timestamp_utc", "source_file", "source_line", "close", "low_quality_period"])
    spot_m1 = spot_m1.dropna(subset=["timestamp_utc"])
    best, by_lag = spot_compare(ohlcv, spot_m1)
    by_lag.to_csv(rep / "spot_corr_by_lag.csv", index=False)
    spot_one = spot_m1.sort_values("timestamp_utc", kind="stable").drop_duplicates("timestamp_utc").set_index("timestamp_utc")["close"]
    rolls = roll_table(ohlcv, spot_one)
    rolls.to_csv(rep / "rolls.csv", index=False)
    long_gaps = pd.concat(gap_rows, ignore_index=True)
    long_gaps.to_csv(rep / "gaps_trades_2h_plus.csv", index=False)

    ts = ohlcv["ts_event"].to_numpy()
    o_gaps, o_rows = gap_stats(ts)
    o_rows.to_csv(rep / "gaps_ohlcv_2h_plus.csv", index=False)
    years = pd.DataFrame.from_dict(audit["years"], orient="index")
    yr = years.rename_axis("year").reset_index()
    tick = pd.DataFrame.from_dict(audit["tick"], orient="index").rename_axis("year").reset_index()
    tick["up: B share"] = (tick["up_B"] / (tick["up_A"] + tick["up_B"])).round(4)
    tick["down: A share"] = (tick["down_A"] / (tick["down_A"] + tick["down_B"])).round(4)
    corr = pd.DataFrame(side_corr).rename_axis("year").reset_index()
    payload = {"audit": audit, "ohlcv_gaps": o_gaps, "spot": best.to_dict("records"), "flags": flags_seen,
               "degraded": degraded_rows, "bars": bars_summary, "side_corr": side_corr}
    (rep / "run.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    m = audit["merge"]
    yr["N volume %"] = (100 * yr["vol_N"] / (yr["vol_A"] + yr["vol_B"] + yr["vol_N"])).round(3)
    repeats = int(yr["key_repeats"].sum())
    up_b = tick["up_B"].sum() / (tick["up_A"].sum() + tick["up_B"].sum())
    down_a = tick["down_A"].sum() / (tick["down_A"].sum() + tick["down_B"].sum())
    roll_rows = rolls[rolls["new_first_bar_utc"].dt.year >= 2019]
    late = rolls[rolls["minutes_apart"] > 120]
    failed = best[(best["r_lag0"] <= 0.9) | (best["best_lag"] != 0)]
    inside = sum(v["roll_inside_bar"] for v in bars_summary.values())
    y15 = best[best["period"] == "2015"].iloc[0]
    findings = [
        f"1. **Side mapping differs from the task.** The task said buy = A, sell = B. The data and the vendor docs say the reverse, "
        f"so the bars use buy = B, sell = A. {up_b:.1%} of upticks are B and {down_a:.1%} of downticks are A, and `delta_ratio` has a "
        f"positive same-bar correlation with the return in every year (0.26 to 0.32). `databento_dbn` documents A as the sell aggressor "
        f"and B as the buy aggressor. To follow the task literally, change `side_map` in `config/orderflow_6e_v1.yaml` and build v2; every delta flips sign.",
        f"2. **2019 merge: {m['removed']} rows removed, all in the join.** Merged count {m['merged_rows']:,} equals the {yr.loc[yr.year == 2019, 'expected'].iloc[0]:,} Databento quoted. "
        f"The 5-field key was applied only to the overlap. Across 2019-2023 {repeats:,} rows repeat that key inside one file ({int(yr.loc[yr.year == 2019, 'key_repeats'].iloc[0]):,} in 2019); "
        f"they are fills of one match event and were kept. Yearly volume equals ohlcv-1m exactly with them, so a global dedup would have lost real volume.",
        f"3. **Rolls fall on bar boundaries.** {len(rolls)} rolls in 2015-2023, {len(roll_rows)} in the trade years. `roll_inside_bar` is true on {inside} bars, so a strict inside-the-bar flag would be empty. "
        f"`roll_flag` is therefore also true on the first bar of a new contract, and `ret_log` is empty there. Jumps are the quarterly futures basis, not moves: median {rolls['jump_pips'].median():.1f} pips, range {rolls['jump_pips'].min():.1f} to {rolls['jump_pips'].max():.1f}.",
        f"4. **The last weekday before a roll is thin.** Volume on that day is a median {roll_rows['last_weekday_vol_ratio'].median():.2f} of normal in the trade years: liquidity has already moved to the next contract but `6E.v.0` has not. "
        f"Those Friday bars hold a fraction of the market's flow. They are not flagged; `rolls.csv` lists the ratios.",
        "5. **June 2023 roll.** " + "; ".join(f"{r.old_last_bar_utc} to {r.new_first_bar_utc}: {r.minutes_apart:.0f} minutes" for r in late.itertuples())
        + ". The old contract stopped mid Friday, so the rest of that Friday is missing from `6E.v.0`. The gap table counts this as a weekend.",
        "6. **Spot check:** " + ("all years pass." if failed.empty else "; ".join(f"{r.period} fails (r {r.r_lag0}, best lag {r.best_lag})" for r in failed.itertuples()))
        + f". Best lag is 0 in every period, so this is not a clock error. 2015 has {y15.spikes:,} 1-minute moves of at least 0.5% in 6E with no spot move, and the ones inspected reverse the next minute. Without them r is {y15.r_lag0_no_spikes}, still under 0.9, and Spearman is {y15.spearman_lag0}, so the 2015 failure is only partly explained. All other years pass. 2015 is outside the bars.",
        f"7. **ohlcv-1m is bucketed on ts_recv.** Bars here use ts_event. Yearly volume agrees exactly, and on ts_recv no minute differs; {int(yr['minutes_differ_ts_event'].sum()):,} of {int(yr['minutes'].sum()):,} minutes differ on ts_event, by moving lots across a minute edge. "
        f"{int(yr['ts_recv_before_ts_event'].sum()):,} trades have ts_recv before ts_event; the yearly counts are in the table below. The largest step is {abs(yr['min_recv_minus_event_ms'].min()):,.0f} ms, so it can move a trade across a bar edge only by that much.",
        "8. **Gaps.** `gaps_trades_2h_plus.csv` holds the long weekday gaps. Most match shortened holiday sessions. 2019-02-27 00:39 to 03:45 UTC is on no degraded list and is unexplained.",
        "9. **Scope.** 12 of the 14 degraded days have trades; all 12 are flagged and kept. 2021-12-05, 2022-01-02 and 2022-11-06 are Sundays, so their low ratio is normal. The condition is for the whole dataset, not 6E alone. Trades hold no 2024 data, and the `low_quality_period` flag is a spot flag, so it was not applied to the 6E bars.",
    ]
    s = [f"# 6E audit and order flow bars v1\n\nGenerated {stamp}. Local files only. Raw hashes matched the manifest before and after the build. Prices are given as pip differences only.\n",
         "## Findings\n", "\n".join(findings) + "\n",
         "## Raw trades: order and side\n",
         md_table(yr[["year", "rows", "expected", "ts_event_order_breaks", "ts_recv_order_breaks", "key_repeats", "A", "B", "N", "N volume %", "size_zero"]]),
         f"\nThe N share rose from July 2023 and was also higher in January-August 2019; it stays under 0.31% of volume. Flags seen: {flags_seen}.\n",
         "## ohlcv-1m\n",
         f"{len(ohlcv):,} rows, order breaks {int((np.diff(ts) < 0).sum())}, duplicate timestamps {int((np.diff(ts) == 0).sum())}. Minute steps of 5 minutes or more: {o_gaps}.\n",
         "## 2019 merge\n", "```json\n" + json.dumps(m, indent=1) + "\n```\n",
         "## Trades vs ohlcv-1m volume\n",
         md_table(yr[["year", "minutes", "minutes_differ_ts_event", "minutes_differ_ts_recv", "volume_trades", "volume_ohlcv", "ts_recv_before_ts_event", "min_recv_minus_event_ms"]]),
         "\n## Side vs tick direction\n", md_table(tick[["year", "up: B share", "down: A share"]]),
         "\n## delta_ratio vs same-bar return (Pearson r)\n", md_table(corr),
         "\n## Trades gaps\n", md_table(pd.DataFrame.from_dict(audit["gaps_trades"], orient="index").rename_axis("year").reset_index()),
         "\n## Degraded days with trades\n", md_table(pd.DataFrame(degraded_rows)),
         "\n2017-11-13 and 2018-10-21 are before the trades start; they appear only in ohlcv-1m.\n",
         "## Rolls\n", md_table(rolls),
         "\nbasis_est = jump minus the spot move between the two bars.\n",
         f"## Spot vs 6E 1-minute returns\n\nSpikes: |6E return| >= {SPIKE_FUT:.1%} with |spot return| < {SPIKE_SPOT:.1%}. All lags are in `spot_corr_by_lag.csv`.\n",
         md_table(best), "\n## Bars\n",
         md_table(pd.DataFrame.from_dict(bars_summary, orient="index").rename_axis("file").reset_index()), "\n"]
    (rep / "summary.md").write_text("\n".join(s), encoding="utf-8")
    return rep


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="output directory, relative to the root")
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(Path("."), args.out, not args.no_report), indent=1, default=str))
