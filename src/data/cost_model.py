"""Spread / cost model v1 from FXCM M1 bid/ask bars.

Spread per minute = ask_close - bid_close, in pips. FXCM labels are UTC. Each minute
is put in one segment, defined on the New York clock so that it follows DST:

  weekly_open_first_hour  Sunday 17:00-18:00 New York (first hour of the trading week)
  weekly_open_rest        the rest of the UTC Sunday
  rollover                Mon-Fri 16:55-18:00 New York (about 21-22 UTC)
  regular                 everything else Mon-Fri; modelled per UTC weekday x hour (5 x 24)
  market_closed           no trading; the lookup returns the fallback

Negative and zero spreads are counted and kept in the minute table but are not used in
the statistics. Extreme spreads are counted and kept in the statistics. A cell with too
few minutes or weeks uses the all-hours (regular) statistics and is marked as fallback.
The FXCM files are only read.

Run:
    .venv/bin/python -m src.data.cost_model
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import platform
import subprocess
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.data.fxcm_audit import read_fxcm_csv
from src.data.inventory import sha256_file

DEFAULT_CONFIG = Path("config/cost_model_v1.yaml")
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
SPECIAL_SEGMENTS = ["weekly_open_first_hour", "weekly_open_rest", "rollover"]
STAT_COLUMNS = ["median", "p75", "p90"]
SCRIPTS = ["src/data/cost_model.py", "src/data/fxcm_audit.py"]
MAX_PERMUTATIONS = 20000


def load_cost_config(path: Path = DEFAULT_CONFIG) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def hm(text: str) -> int:
    h, m = str(text).split(":")
    return int(h) * 60 + int(m)


# ---------------------------------------------------------------------------
# Segments and regimes
# ---------------------------------------------------------------------------
def classify(utc: pd.Series, cfg: dict) -> pd.DataFrame:
    """Segment, regime and UTC weekday/hour of each UTC instant."""
    utc = pd.Series(pd.DatetimeIndex(utc).tz_convert("UTC"))
    seg_cfg = cfg["segments"]
    local = utc.dt.tz_convert(seg_cfg["clock"])
    ny_dow, ny_min = local.dt.dayofweek, local.dt.hour * 60 + local.dt.minute
    offset = (local.dt.tz_localize(None) - utc.dt.tz_localize(None)) / pd.Timedelta(minutes=1)
    standard = pd.Timestamp("2021-01-13", tz=seg_cfg["clock"]).utcoffset() / pd.Timedelta(minutes=1)
    summer = offset > standard
    open_start = hm(seg_cfg["weekly_open_first_hour"]["start"])
    closed = (ny_dow == 5) | ((ny_dow == 4) & (ny_min >= open_start)) | ((ny_dow == 6) & (ny_min < open_start))
    sunday_utc = utc.dt.dayofweek == 6
    first_hour = (ny_dow == 6) & (ny_min >= open_start) & (ny_min < hm(seg_cfg["weekly_open_first_hour"]["end"]))
    roll = (ny_min >= hm(seg_cfg["rollover"]["start"])) & (ny_min < hm(seg_cfg["rollover"]["end"]))
    segment = np.select(
        [closed, first_hour, sunday_utc, roll],
        ["market_closed", "weekly_open_first_hour", "weekly_open_rest", "rollover"], default="regular")
    return pd.DataFrame({"segment": segment, "regime": np.where(summer, "summer", "winter"),
                         "weekday": utc.dt.dayofweek.to_numpy(), "hour": utc.dt.hour.to_numpy()})


def rollover_hours(cfg: dict) -> dict[str, set[int]]:
    """UTC hours that the New York rollover window touches, per regime."""
    zone = cfg["segments"]["clock"]
    start, end = hm(cfg["segments"]["rollover"]["start"]), hm(cfg["segments"]["rollover"]["end"])
    out = {}
    for regime, day in (("summer", "2021-07-07"), ("winter", "2021-01-13")):
        shift = -pd.Timestamp(day, tz=zone).utcoffset() / pd.Timedelta(minutes=1)
        lo, hi = int(start + shift), int(end + shift)
        if hi > 24 * 60:
            raise ValueError("rollover window crosses UTC midnight; weekday marking would be wrong")
        out[regime] = set(range(lo // 60, -(-hi // 60)))
    return out


# ---------------------------------------------------------------------------
# Minute spreads
# ---------------------------------------------------------------------------
def minute_spreads(fx: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """fx: columns file, timestamp_label (naive UTC), bid_close, ask_close."""
    utc = pd.DatetimeIndex(fx["timestamp_label"]).tz_localize("UTC")
    spread = ((fx["ask_close"] - fx["bid_close"]) / cfg["pip"]).round(4).to_numpy()
    out = pd.DataFrame({"file": fx["file"].to_numpy(), "timestamp_utc": utc, "spread_pips": spread})
    out = pd.concat([out, classify(out["timestamp_utc"], cfg)], axis=1)
    out["category"] = np.select([spread < 0, spread == 0, spread > cfg["anomalies"]["extreme_pips"]],
                                ["negative", "zero", "extreme"], default="normal")
    out["used"] = spread > 0
    return out.sort_values(["timestamp_utc", "file"], kind="mergesort").reset_index(drop=True)


def stats(group: pd.DataFrame, cfg: dict) -> dict:
    s = group["spread_pips"]
    row = {"n_minutes": int(len(s)), "n_weeks": int(group["file"].nunique())}
    for name, q in cfg["quantiles"].items():
        row[name] = round(float(s.quantile(q)), 4) if len(s) else np.nan
    row["mean"] = round(float(s.mean()), 4) if len(s) else np.nan  # descriptive / tie-break only
    return row


def sufficient(row: dict, cfg: dict) -> bool:
    return row["n_minutes"] >= cfg["sample"]["min_minutes"] and row["n_weeks"] >= cfg["sample"]["min_weeks"]


def hour_of_week(used: pd.DataFrame, cfg: dict, fallback: dict, regime: str = "all") -> pd.DataFrame:
    """5 x 24 table of regular-segment statistics; insufficient cells take the fallback values."""
    regular = used[used["segment"] == "regular"]
    if regime != "all":
        regular = regular[regular["regime"] == regime]
    groups = dict(tuple(regular.groupby(["weekday", "hour"])))
    roll = rollover_hours(cfg)
    rows = []
    for wd, hour in itertools.product(range(5), range(24)):
        g = groups.get((wd, hour), regular.iloc[0:0])
        cell = stats(g, cfg)
        ok = sufficient(cell, cfg)
        row = {"regime": regime, "weekday": wd, "weekday_name": WEEKDAYS[wd], "hour_utc": hour,
               "n_minutes": cell["n_minutes"], "n_weeks": cell["n_weeks"],
               **{f"cell_{c}": cell[c] for c in [*STAT_COLUMNS, "mean"]},
               **{c: (cell[c] if ok else fallback[c]) for c in STAT_COLUMNS},
               "fallback": not ok,
               "rollover_hour_summer": hour in roll["summer"], "rollover_hour_winter": hour in roll["winter"]}
        rows.append(row)
    return pd.DataFrame(rows)


def segment_table(used: pd.DataFrame, cfg: dict, fallback: dict) -> pd.DataFrame:
    """Pooled ('all') row per segment, used by the lookup, plus descriptive summer / winter rows.

    An insufficient pooled row takes the all-hours fallback; an insufficient regime row takes its pooled row.
    """
    rows = []
    for seg in SPECIAL_SEGMENTS:
        g_all = used[used["segment"] == seg]
        pooled = None
        for regime in ("all", "summer", "winter"):
            g = g_all if regime == "all" else g_all[g_all["regime"] == regime]
            s = stats(g, cfg)
            ok = sufficient(s, cfg)
            base = fallback if regime == "all" else pooled
            row = {"segment": seg, "regime": regime, "n_minutes": s["n_minutes"], "n_weeks": s["n_weeks"],
                   **{f"cell_{c}": s[c] for c in [*STAT_COLUMNS, "mean"]},
                   **{c: (s[c] if ok else base[c]) for c in STAT_COLUMNS},
                   "fallback": not ok, "fallback_to": "" if ok else ("all_hours" if regime == "all" else "segment_all")}
            pooled = pooled or row
            rows.append(row)
    return pd.DataFrame(rows)


def regime_test(used: pd.DataFrame, cfg: dict) -> dict:
    """Exact permutation test of winter vs summer on regular hours.

    Statistic: median over hour-of-week cells of (mean of winter-week cell means -
    mean of summer-week cell means). Week labels are permuted, keeping group sizes.
    """
    regular = used[used["segment"] == "regular"]
    week_regime = regular.groupby("file")["regime"].agg(lambda r: r.mode().iloc[0])
    winter = sorted(week_regime[week_regime == "winter"].index)
    files = sorted(week_regime.index)
    out = {"weeks_summer": len(files) - len(winter), "weeks_winter": len(winter), "winter_weeks": winter,
           "alpha": cfg["regime"]["alpha"], "min_effect_pips": cfg["regime"]["min_effect_pips"]}
    if not winter or len(winter) == len(files):
        return {**out, "statistic_pips": None, "p_value": None, "separate": False,
                "note": "only one regime in the sample"}
    cells = regular.groupby(["file", "weekday", "hour"])["spread_pips"].mean().unstack(["weekday", "hour"])
    cells = cells.loc[files]

    def statistic(group):
        a, b = cells.loc[list(group)].mean(), cells.drop(list(group)).mean()
        return float((a - b).dropna().median())

    n = comb(len(files), len(winter))
    if n > MAX_PERMUTATIONS:
        raise ValueError(f"{n} permutations; exact test too large")
    observed = statistic(winter)
    null = [statistic(g) for g in itertools.combinations(files, len(winter))]
    p = float(np.mean([abs(x) >= abs(observed) - 1e-12 for x in null]))
    separate = p <= cfg["regime"]["alpha"] and abs(observed) >= cfg["regime"]["min_effect_pips"]
    return {**out, "statistic_pips": round(observed, 4), "p_value": round(p, 4), "permutations": n,
            "min_attainable_p": round(1 / n, 4), "separate": bool(separate)}


def audit53_comparison(minutes: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Hour-of-day medians from the 53.csv audit against this sample, computed the same way (all minutes)."""
    ref = pd.read_csv(path)
    ours = minutes.groupby("hour")["spread_pips"].median().rename("sample_median_all_minutes")
    used = minutes[minutes["used"]].groupby("hour")["spread_pips"].median().rename("sample_median_positive")
    return (ref.rename(columns={"label_hour": "hour", "count": "audit53_count", "median": "audit53_median",
                                "max": "audit53_max"})
            .merge(ours, left_on="hour", right_index=True, how="left")
            .merge(used, left_on="hour", right_index=True, how="left"))


def build(minutes: pd.DataFrame, cfg: dict) -> dict:
    used = minutes[minutes["used"]]
    fallback = stats(used[used["segment"] == "regular"], cfg)
    regime = regime_test(used, cfg)
    regimes = ["summer", "winter"] if regime["separate"] else ["all"]
    table = pd.concat([hour_of_week(used, cfg, fallback, r) for r in regimes], ignore_index=True)
    anomalies = (minutes.groupby(["file", "category"]).size().unstack(fill_value=0)
                 .reindex(columns=["normal", "extreme", "zero", "negative"], fill_value=0))
    anomalies.loc["all"] = anomalies.sum()
    return {"hour_of_week": table, "segments": segment_table(used, cfg, fallback), "regime_test": regime,
            "fallback": {"source": "all regular-segment minutes", **fallback},
            "anomalies": anomalies.reset_index()}


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------
class CostModel:
    """Spread lookup in pips. Every UTC instant gets a value > 0."""

    def __init__(self, hour_table: pd.DataFrame, segments: pd.DataFrame, fallback: dict, cfg: dict):
        self.cfg = cfg
        self.fallback = fallback
        self.hours = hour_table.set_index(["regime", "weekday", "hour_utc"])
        self.segments = segments[segments["regime"] == "all"].set_index("segment")
        self.separate = set(hour_table["regime"]) != {"all"}

    @classmethod
    def load(cls, model_dir: Path, cfg: dict) -> "CostModel":
        model_dir = Path(model_dir)
        fallback = json.loads((model_dir / "model.json").read_text(encoding="utf-8"))["fallback"]
        return cls(pd.read_csv(model_dir / "hour_of_week.csv"), pd.read_csv(model_dir / "segments.csv"), fallback, cfg)

    def lookup(self, utc, quantile: str = "median") -> pd.DataFrame:
        """Spread per instant: columns spread_pips, segment, source ('cell', 'segment' or 'fallback')."""
        c = classify(pd.Series(pd.DatetimeIndex(utc)), self.cfg)
        value = pd.Series(float(self.fallback[quantile]), index=c.index)
        source = pd.Series("fallback", index=c.index, dtype=object)
        regular = c["segment"] == "regular"
        key = pd.MultiIndex.from_arrays([c["regime"] if self.separate else ["all"] * len(c), c["weekday"], c["hour"]])
        cells = self.hours.reindex(key[regular.to_numpy()])
        value[regular] = cells[quantile].to_numpy()
        source[regular] = np.where(cells["fallback"].to_numpy(), "fallback", "cell")
        special = c["segment"].isin(self.segments.index)
        segs = self.segments.reindex(c.loc[special, "segment"])
        value[special] = segs[quantile].to_numpy()
        source[special] = np.where(segs["fallback"].to_numpy(), "fallback", "segment")
        return pd.DataFrame({"spread_pips": np.maximum(value.to_numpy(), self.cfg["floor_pips"]),
                             "segment": c["segment"].to_numpy(), "source": source.to_numpy()})

    def cost_for(self, timestamp_utc, percentile: str | None = None):
        """Round-trip cost in pips = spread(percentile) + commission + slippage (config trading_costs).

        Flags mark rollover, weekly-open and market-closed instants, so a backtest can decide
        whether to trade or close positions then. A scalar timestamp returns a dict, anything
        else a DataFrame with one row per timestamp.
        """
        tc = self.cfg["trading_costs"]
        percentile = percentile or tc["spread_percentile"]
        if percentile not in STAT_COLUMNS:
            raise ValueError(f"spread percentile {percentile!r} not in {STAT_COLUMNS}")
        scalar = np.ndim(timestamp_utc) == 0
        out = self.lookup([timestamp_utc] if scalar else timestamp_utc, percentile)
        out.insert(0, "timestamp_utc", pd.DatetimeIndex([timestamp_utc] if scalar else timestamp_utc))
        out["percentile"] = percentile
        out["commission_pips"] = float(tc["commission_pips_round_trip"])
        out["slippage_pips"] = float(tc["slippage_pips"])
        out["total_pips"] = out["spread_pips"] + out["commission_pips"] + out["slippage_pips"]
        out["is_rollover"] = out["segment"] == "rollover"
        out["is_weekly_open"] = out["segment"].str.startswith("weekly_open")
        out["is_market_closed"] = out["segment"] == "market_closed"
        return out.iloc[0].to_dict() if scalar else out


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def read_sources(fxcm_dir: Path) -> tuple[pd.DataFrame, list[dict]]:
    manifest = pd.read_csv(fxcm_dir / "MANIFEST.csv")
    recorded = dict(line.split()[::-1] for line in (fxcm_dir / "SHA256SUMS.txt").read_text().splitlines() if line)
    frames, inputs = [], []
    for local in sorted(manifest["local_path"], key=lambda p: (int(Path(p).parent.name), int(Path(p).name.split(".")[0]))):
        path = fxcm_dir / local
        sha = sha256_file(path)
        if recorded.get(local) != sha:
            raise AssertionError(f"{path} does not match SHA256SUMS.txt")
        fx = read_fxcm_csv(path)
        label = f"{Path(local).parent.name}/{Path(local).name}"
        frames.append(fx.assign(file=label)[["file", "timestamp_label", "bid_close", "ask_close"]])
        inputs.append({"path": str(Path(local)), "sha256": sha, "rows": len(fx)})
    return pd.concat(frames, ignore_index=True), inputs


def write_csv(df: pd.DataFrame, path: Path) -> None:
    with open(path, "x", encoding="utf-8", newline="") as handle:
        df.to_csv(handle, index=False, float_format="%.4f", lineterminator="\n")


def git_state(root: Path) -> dict:
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        return {"git_commit": None, "git_dirty": None}
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", *SCRIPTS, "config"],
                           capture_output=True, text=True)
    return {"git_commit": head.stdout.strip(), "git_dirty": bool(dirty.stdout.strip())}


def run(root: Path, config_path: Path = DEFAULT_CONFIG, out_dir: Path | None = None) -> dict:
    root = Path(root)
    cfg = load_cost_config(root / config_path)
    out = root / (out_dir or cfg["output_dir"])
    if out.exists():
        raise FileExistsError(f"{out} exists; versions are never overwritten")
    fxcm_dir = root / cfg["source"]["fxcm_dir"]
    fx, inputs = read_sources(fxcm_dir)
    minutes = minute_spreads(fx, cfg)
    model = build(minutes, cfg)
    a53_path = root / cfg["source"]["audit_53_spread_by_hour"]
    comparison = audit53_comparison(minutes, a53_path) if a53_path.exists() else None

    out.mkdir(parents=True, exist_ok=False)
    with open(out / "spread_minutes.parquet", "xb") as handle:
        minutes.to_parquet(handle, index=False, engine="pyarrow", compression="snappy")
    write_csv(model["hour_of_week"], out / "hour_of_week.csv")
    write_csv(model["segments"], out / "segments.csv")
    write_csv(model["anomalies"], out / "anomalies.csv")
    names = ["spread_minutes.parquet", "hour_of_week.csv", "segments.csv", "anomalies.csv"]
    if comparison is not None:
        write_csv(comparison, out / "audit53_comparison.csv")
        names.append("audit53_comparison.csv")
    with open(out / "model.json", "x", encoding="utf-8") as handle:  # deterministic: no timestamps
        json.dump({"version": cfg["version"], "fallback": model["fallback"], "regime_test": model["regime_test"],
                   "floor_pips": cfg["floor_pips"]}, handle, indent=2, sort_keys=True)
    names.append("model.json")
    if any(sha256_file(fxcm_dir / i["path"]) != i["sha256"] for i in inputs):
        raise AssertionError("an input changed during the build")

    manifest = {
        "dataset": "cost_model", "version": out.name,
        "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {"path": str(config_path), "sha256": sha256_file(root / config_path)},
        "inputs": {"fxcm_dir": cfg["source"]["fxcm_dir"], "files": inputs,
                   "audit_53_spread_by_hour": ({"path": cfg["source"]["audit_53_spread_by_hour"],
                                                "sha256": sha256_file(a53_path), "use": "comparison only"}
                                               if comparison is not None else None)},
        "price_basis": "FXCM bid/ask close of each M1 bar; labels UTC per FXCM api reply 2026-10-23",
        **git_state(root),
        "scripts_sha256": {s: sha256_file(root / s) for s in SCRIPTS if (root / s).exists()},
        "outputs": {n: sha256_file(out / n) for n in names},
        "minutes": int(len(minutes)), "minutes_used": int(minutes["used"].sum()),
        "environment": {"python": platform.python_version(), "pandas": pd.__version__,
                        "pyarrow": __import__("pyarrow").__version__},
    }
    with open(out / "manifest.json", "x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    with open(out / "SHA256SUMS.txt", "x", encoding="utf-8") as handle:
        for n in [*names, "manifest.json"]:
            handle.write(f"{sha256_file(out / n)}  {n}\n")
    return {"manifest": manifest, "model": model, "comparison": comparison, "minutes": minutes, "out_dir": out}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    r = run(Path.cwd(), args.config, args.out)
    print(json.dumps({"regime_test": r["model"]["regime_test"], "fallback": r["model"]["fallback"],
                      "outputs": r["manifest"]["outputs"]}, indent=2))
    print(f"written: {r['out_dir']}")


if __name__ == "__main__":
    main()
