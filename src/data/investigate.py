"""Read-only investigation of timestamp semantics, duplicates and gaps.

Builds on src.data.audit. Nothing here modifies, sorts, deduplicates or
converts the source files. Where an in-memory view needs ordering, e.g. for
1-minute returns, it is a sorted copy that excludes every duplicated
timestamp, so no copy of a duplicate is preferred over another.

The timezone hypotheses tested (all on the naive source clock):
  H1 fixed UTC-5 all year            (HistData FAQ: "EST without DST")
  H2 America/New_York                (UTC-5, UTC-4 during US DST)
  H3 New York offsets, EU dates      (UTC-5, UTC-4 during EU summer time)

Run:
    .venv/bin/python -m src.data.investigate
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.audit import detect_gaps, find_duplicates, find_out_of_order, load_config, load_raw, md_table, write_new
from src.data.inventory import discover_raw_files, parse_gap_report, sha256_file

HYPOTHESES = {
    "H1_fixed_utc-5": "Fixed UTC-5 all year (HistData FAQ: EST without DST)",
    "H2_america_new_york": "New York local time: UTC-5, UTC-4 during US DST",
    "H3_ny_offset_eu_dates": "UTC-5, UTC-4 during EU summer time (New York offsets, EU switch dates)",
}
# regime -> (US on summer time, EU/UK on summer time). EU summer without US summer never occurs.
REGIMES = {"both_standard": (False, False), "both_summer": (True, True), "us_summer_eu_standard": (True, False)}

# Events with documented clock times, used as independent anchors.
ANCHORS = {
    "us_0830_release": {
        "follows": "us", "utc_standard": "13:30", "utc_summer": "12:30",
        "candidates": ["07:30", "08:30", "09:30"],
        "basis": "US macro releases (e.g. BLS employment, CPI) are published at 08:30 New York time",
    },
    "london_1600_fix": {
        "follows": "uk", "utc_standard": "16:00", "utc_summer": "15:00",
        "candidates": ["10:00", "11:00", "12:00"],
        "basis": "WM/Reuters FX benchmark is fixed at 16:00 London time; activity measured in the 5 minutes before",
    },
    "weekly_open_1700_ny": {
        "follows": "us", "utc_standard": "22:00", "utc_summer": "21:00",
        "candidates": ["16:00", "17:00", "18:00"],
        "basis": "Industry/broker convention (not an exchange rule): FX week opens Sunday 17:00 New York",
    },
}


# An anchor observation counts as decisive only if its strongest candidate
# minute is at least this many times stronger than the runner-up.
DECISIVE_RATIO = 1.5


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------
def nth_weekday(year: int, month: int, weekday: int, n: int) -> pd.Timestamp:
    first = pd.Timestamp(year, month, 1)
    return first + pd.Timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def last_weekday(year: int, month: int, weekday: int) -> pd.Timestamp:
    last = pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)
    return last - pd.Timedelta(days=(last.weekday() - weekday) % 7)


def dst_switch_dates(year: int) -> dict[str, pd.Timestamp]:
    """Current US (since 2007) and EU/UK (since 1996) DST switch Sundays."""
    return {
        "us_start": nth_weekday(year, 3, 6, 2),
        "eu_start": last_weekday(year, 3, 6),
        "eu_end": last_weekday(year, 10, 6),
        "us_end": nth_weekday(year, 11, 6, 1),
    }


def dst_regime(timestamps: pd.Series) -> pd.Series:
    """DST regime of each timestamp's calendar date (source clock)."""
    days = pd.Series(timestamps).dt.normalize()
    years = days.dt.year
    regime = pd.Series("both_standard", index=days.index, dtype=object)
    for year in years.unique():
        s = dst_switch_dates(int(year))
        in_year = years == year
        regime[in_year & (days >= s["eu_start"]) & (days < s["eu_end"])] = "both_summer"
        window = ((days >= s["us_start"]) & (days < s["eu_start"])) | ((days >= s["eu_end"]) & (days < s["us_end"]))
        regime[in_year & window] = "us_summer_eu_standard"
    return regime


def window_part(timestamps: pd.Series, regime: pd.Series) -> pd.Series:
    """Split the US-summer/EU-standard regime into its spring and autumn windows."""
    month = pd.Series(timestamps).dt.month
    part = regime.copy()
    is_window = regime == "us_summer_eu_standard"
    part[is_window & (month <= 6)] = "window_spring"
    part[is_window & (month > 6)] = "window_autumn"
    return part


def easter_sunday(year: int) -> pd.Timestamp:
    """Gregorian Easter (anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return pd.Timestamp(year, month, day)


def holiday_calendar(year: int) -> dict[pd.Timestamp, list[str]]:
    """Dates on which a reduced or closed data feed is *plausible*. Not verified closures."""
    easter = easter_sunday(year)
    entries = [
        (pd.Timestamp(year, 1, 1), "New Year's Day"),
        (pd.Timestamp(year, 12, 24), "Christmas Eve"),
        (pd.Timestamp(year, 12, 25), "Christmas Day"),
        (pd.Timestamp(year, 12, 26), "Boxing Day"),
        (pd.Timestamp(year, 12, 31), "New Year's Eve"),
        (easter - pd.Timedelta(days=2), "Good Friday"),
        (easter + pd.Timedelta(days=1), "Easter Monday"),
        (pd.Timestamp(year, 7, 4), "US Independence Day"),
        (nth_weekday(year, 1, 0, 3), "US Martin Luther King Jr. Day"),
        (nth_weekday(year, 2, 0, 3), "US Presidents' Day"),
        (last_weekday(year, 5, 0), "US Memorial Day / UK Spring Bank Holiday"),
        (nth_weekday(year, 9, 0, 1), "US Labor Day"),
        (nth_weekday(year, 11, 3, 4), "US Thanksgiving"),
        (nth_weekday(year, 11, 3, 4) + pd.Timedelta(days=1), "Day after US Thanksgiving"),
        (nth_weekday(year, 5, 0, 1), "UK Early May Bank Holiday"),
        (last_weekday(year, 8, 0), "UK Summer Bank Holiday"),
    ]
    if year >= 2021:
        entries.append((pd.Timestamp(year, 6, 19), "US Juneteenth"))
    calendar: dict[pd.Timestamp, list[str]] = {}
    for day, name in entries:
        calendar.setdefault(day, []).append(name)
    return calendar


# ---------------------------------------------------------------------------
# Hypothesis predictions
# ---------------------------------------------------------------------------
def source_offset_hours(hypothesis: str, us_summer: bool, eu_summer: bool) -> int:
    if hypothesis == "H1_fixed_utc-5":
        return -5
    if hypothesis == "H2_america_new_york":
        return -5 + int(us_summer)
    if hypothesis == "H3_ny_offset_eu_dates":
        return -5 + int(eu_summer)
    raise ValueError(hypothesis)


def predicted_source_time(anchor: str, hypothesis: str, regime: str) -> str:
    """Source-clock HH:MM at which an anchor event should appear under a hypothesis."""
    spec = ANCHORS[anchor]
    us_summer, eu_summer = REGIMES[regime]
    event_summer = us_summer if spec["follows"] == "us" else eu_summer
    utc = pd.Timestamp("2000-01-03 " + spec["utc_summer" if event_summer else "utc_standard"])
    local = utc + pd.Timedelta(hours=source_offset_hours(hypothesis, us_summer, eu_summer))
    return local.strftime("%H:%M")


def prediction_table() -> pd.DataFrame:
    rows = []
    for anchor in ANCHORS:
        for regime in REGIMES:
            row = {"anchor": anchor, "regime": regime}
            row.update({h: predicted_source_time(anchor, h, regime) for h in HYPOTHESES})
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Observed evidence
# ---------------------------------------------------------------------------
def returns_view(raw: pd.DataFrame) -> pd.DataFrame:
    """Absolute 1-minute log returns between consecutive weekday minutes.

    In-memory, sorted copy; every duplicated timestamp is excluded entirely.
    """
    duplicated = raw["timestamp"].duplicated(keep=False)
    view = raw.loc[~duplicated, ["timestamp", "close"]].sort_values("timestamp")
    ts = view["timestamp"]
    abs_return = np.log(view["close"]).diff().abs()
    keep = (ts.diff() == pd.Timedelta(minutes=1)) & (ts.dt.weekday < 5)
    out = pd.DataFrame({"timestamp": ts[keep].to_numpy(), "abs_log_return": abs_return[keep].to_numpy()})
    out["regime"] = dst_regime(out["timestamp"]).to_numpy()
    out["part"] = window_part(out["timestamp"], out["regime"]).to_numpy()
    out["year"] = out["timestamp"].dt.year
    out["hm"] = out["timestamp"].dt.strftime("%H:%M")
    return out


def anchor_strength(profile: pd.Series, anchor: str, hm: str) -> float:
    """Anchor activity at source time hm, relative to the 06:00-13:00 median minute."""
    baseline = profile.loc["06:00":"13:00"].median()
    if anchor == "london_1600_fix":
        end = pd.Timestamp("2000-01-03 " + hm)
        minutes = [(end - pd.Timedelta(minutes=k)).strftime("%H:%M") for k in range(5, 0, -1)]
        value = profile.reindex(minutes).mean()
    else:
        value = profile.get(hm, np.nan)
    return float(value / baseline)


def intraday_anchor_observations(view: pd.DataFrame, group_by: list[str]) -> pd.DataFrame:
    """Observed source time of each intraday anchor per group, and hypothesis consistency."""
    rows = []
    for key, group in view.groupby(group_by):
        key = key if isinstance(key, tuple) else (key,)
        labels = dict(zip(group_by, key))
        regime = group["regime"].iloc[0]
        profile = group.groupby("hm")["abs_log_return"].mean()
        n_days = group["timestamp"].dt.normalize().nunique()
        for anchor in ("us_0830_release", "london_1600_fix"):
            strengths = {hm: anchor_strength(profile, anchor, hm) for hm in ANCHORS[anchor]["candidates"]}
            observed = max(strengths, key=strengths.get)
            ranked = sorted(strengths.values(), reverse=True)
            ratio = round(ranked[0] / ranked[1], 2)
            row = {**labels, "regime": regime, "anchor": anchor, "weekdays": n_days, "observed_time": observed,
                   "strength_ratio_top_vs_second": ratio, "decisive": ratio >= DECISIVE_RATIO}
            row.update({f"strength_{hm}": round(v, 2) for hm, v in strengths.items()})
            for h in HYPOTHESES:
                row[f"{h}_predicts"] = predicted_source_time(anchor, h, regime)
                row[f"{h}_consistent"] = row[f"{h}_predicts"] == observed
            rows.append(row)
    return pd.DataFrame(rows)


def daily_release_minutes(view: pd.DataFrame, start: str, end: str, top: int = 2) -> pd.DataFrame:
    """Per weekday, the strongest source-clock minutes between 07:00 and 09:59."""
    window = view[(view["timestamp"] >= start) & (view["timestamp"] < end)
                  & view["timestamp"].dt.hour.between(7, 9)]
    rows = []
    for day, part in window.groupby(window["timestamp"].dt.normalize()):
        best = part.nlargest(top, "abs_log_return")
        rows.append({"date": day.date(), "weekday": day.day_name(), "regime": part["regime"].iloc[0],
                     **{f"top{i + 1}": f"{t:%H:%M} ({x * 1e4:.1f}bp)" for i, (t, x) in
                        enumerate(best[["timestamp", "abs_log_return"]].itertuples(index=False))}})
    return pd.DataFrame(rows)


def repeated_block_continuity(raw: pd.DataFrame, identical_groups: pd.DataFrame) -> pd.DataFrame:
    """For each identical repeated block: are the copies equal and are prices continuous at the joins?"""
    rows = []
    for g in identical_groups.itertuples(index=False):
        part = raw[raw["source_file"] == g.source_file]
        span = part[(part["timestamp"] >= g.first_timestamp) & (part["timestamp"] <= g.last_timestamp)]
        first_row, last_row = span["source_row"].min(), span["source_row"].max()
        n = g.timestamps
        copy1, copy2 = span.iloc[:n], span.iloc[n:2 * n]
        before = part[part["source_row"] == first_row - 1]
        after = part[part["source_row"] == last_row + 1]
        rows.append({
            "source_file": g.source_file, "date": g.date,
            "copies_equal": bool(np.array_equal(copy1[["open", "high", "low", "close"]].to_numpy(),
                                                copy2[["open", "high", "low", "close"]].to_numpy())),
            "close_before": float(before["close"].iloc[0]), "open_copy1": float(copy1["open"].iloc[0]),
            "close_copy1_end": float(copy1["close"].iloc[-1]), "open_copy2": float(copy2["open"].iloc[0]),
            "close_copy2_end": float(copy2["close"].iloc[-1]), "open_after": float(after["open"].iloc[0]),
            "join_into_copy2_pips": round(abs(copy2["open"].iloc[0] - copy1["close"].iloc[-1]) * 1e4, 1),
            "outer_joins_pips": f"{abs(copy1['open'].iloc[0] - before['close'].iloc[0]) * 1e4:.1f} / "
                                f"{abs(after['open'].iloc[0] - copy2['close'].iloc[-1]) * 1e4:.1f}",
        })
    return pd.DataFrame(rows)


def unique_closes(raw: pd.DataFrame) -> pd.Series:
    """Close by timestamp, in-memory, excluding every duplicated timestamp."""
    duplicated = raw["timestamp"].duplicated(keep=False)
    return raw.loc[~duplicated].set_index("timestamp")["close"].sort_index()


def spring_hole_price_change(closes: pd.Series, transitions: pd.DataFrame) -> pd.DataFrame:
    """Close-to-close change across each 60-bar EU-spring hole vs the typical 61-minute change."""
    later = closes.reindex(closes.index + pd.Timedelta(minutes=61)).to_numpy()
    typical = float(np.nanmedian(np.abs(later - closes.to_numpy())) * 1e4)
    rows = []
    for t in transitions[(transitions["event"] == "eu_start") & transitions["long_gaps_on_day"].str.contains("60 bars")].itertuples():
        day = pd.Timestamp(t.date)
        a, b = day + pd.Timedelta(hours=18, minutes=59), day + pd.Timedelta(hours=20)
        if a in closes.index and b in closes.index:
            rows.append({"date": t.date, "change_pips": round(abs(closes[b] - closes[a]) * 1e4, 1),
                         "median_61min_change_pips": round(typical, 1)})
    return pd.DataFrame(rows)


def weekly_open_observations(gaps: pd.DataFrame) -> pd.DataFrame:
    """Weekly open time per year and DST regime of the opening Sunday."""
    weekend = gaps[gaps["category"] == "weekend"]
    opens = weekend["first_bar_after"].reset_index(drop=True)
    df = pd.DataFrame({"week_open": opens, "year": opens.dt.year, "regime": dst_regime(opens).to_numpy(),
                       "open_hm": opens.dt.strftime("%H:%M"), "open_hour": opens.dt.hour})
    df["part"] = window_part(df["week_open"], df["regime"]).to_numpy()
    for h in HYPOTHESES:
        predicted = df["regime"].map(lambda r: predicted_source_time("weekly_open_1700_ny", h, r))
        df[f"{h}_predicted_hour"] = predicted.str[:2].astype(int)
        df[f"{h}_consistent_hour"] = df[f"{h}_predicted_hour"] == df["open_hour"]
    return df


def summarize_weekly_opens(opens: pd.DataFrame, group_by: list[str]) -> pd.DataFrame:
    agg = {"weeks": ("week_open", "size"),
           "open_hours_seen": ("open_hour", lambda s: ",".join(f"{h}:00x{n}" for h, n in s.value_counts().sort_index().items()))}
    agg.update({f"{h}_consistent_weeks": (f"{h}_consistent_hour", "sum") for h in HYPOTHESES})
    return opens.groupby(group_by).agg(**agg).reset_index()


def dst_transition_days(raw: pd.DataFrame, gaps: pd.DataFrame, txt_gaps: pd.DataFrame) -> pd.DataFrame:
    """What the data shows on each DST switch Sunday in range."""
    ts = raw["timestamp"]
    first, last = ts.min(), ts.max()
    dup_counts = ts[ts.duplicated(keep=False)].dt.normalize().value_counts()
    rows = []
    for year in range(first.year, last.year + 1):
        for event, day in dst_switch_dates(year).items():
            if not (first.normalize() <= day <= last.normalize()):
                continue
            on_day = ts[ts.dt.normalize() == day]
            evening = on_day[(on_day.dt.hour >= 17) & (on_day.dt.hour < 22)]
            day_gaps = gaps[(gaps["last_bar_before"].dt.normalize() == day) & (gaps["category"] != "weekend")
                            & (gaps["missing_bars"] >= 30)]
            opening = gaps[(gaps["category"] == "weekend") & (gaps["first_bar_after"].dt.normalize() == day)]
            day_txt = txt_gaps[(txt_gaps["start"].dt.normalize() == day) & (txt_gaps["seconds"] >= 1800)]
            rows.append({
                "year": year, "event": event, "date": day.date(),
                "week_open": opening["first_bar_after"].min() if len(opening) else pd.NaT,
                "rows_17_to_22": len(evening), "distinct_minutes_17_to_22": evening.nunique(),
                "duplicated_rows_on_day": int(dup_counts.get(day, 0)),
                "long_gaps_on_day": "; ".join(
                    f"{a:%H:%M}->{b:%H:%M} ({m} bars)" for a, b, m in
                    day_gaps[["last_bar_before", "first_bar_after", "missing_bars"]].itertuples(index=False)),
                "txt_tick_gaps_ge_30min": "; ".join(
                    f"{s:%H:%M:%S} {sec}s" for s, sec in day_txt[["start", "seconds"]].itertuples(index=False)),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Duplicates (with original text and row order)
# ---------------------------------------------------------------------------
def read_lines(paths: dict[str, Path], names) -> dict[str, list[str]]:
    return {name: paths[name].read_text(encoding="ascii").splitlines() for name in set(names)}


def dst_association(day: pd.Timestamp) -> str:
    matches = [event for event, d in dst_switch_dates(day.year).items() if d == day.normalize()]
    return ",".join(matches) if matches else ""


def duplicate_reports(raw: pd.DataFrame, paths: dict[str, Path]) -> dict[str, pd.DataFrame]:
    dup = find_duplicates(raw)
    out_of_order = find_out_of_order(raw)
    lines = read_lines(paths, list(dup["source_file"].astype(str)) + list(out_of_order["source_file"].astype(str)))

    conflicting = dup[dup["status"] == "conflicting"].copy()
    conflicting["occurrence"] = conflicting.groupby("timestamp").cumcount() + 1
    conflicting["line_number"] = conflicting["source_row"] + 1
    conflicting["raw_line"] = [lines[f][r] for f, r in zip(conflicting["source_file"].astype(str), conflicting["source_row"])]
    conflicting["timestamp_string"] = [line.split(";")[0] for line in conflicting["raw_line"]]
    conflicting["dst_switch_date"] = conflicting["timestamp"].map(dst_association)
    conflicting = conflicting[["source_file", "line_number", "timestamp_string", "occurrence", "group_size",
                               "open", "high", "low", "close", "volume", "raw_line", "dst_switch_date"]]

    context = []
    for name, part in dup[dup["status"] == "conflicting"].groupby("source_file", observed=True):
        lo, hi = part["source_row"].min() - 3, part["source_row"].max() + 3
        for row in range(max(lo, 0), min(hi, len(lines[str(name)]) - 1) + 1):
            context.append({"source_file": name, "line_number": row + 1, "raw_line": lines[str(name)][row],
                            "is_conflicting_duplicate": row in set(part["source_row"])})

    identical = dup[dup["status"] == "identical"].copy()
    identical["occurrence"] = identical.groupby("timestamp").cumcount() + 1
    identical["date"] = identical["timestamp"].dt.normalize()
    groups = []
    for (name, day), part in identical.groupby(["source_file", "date"], observed=True):
        blocks = part.groupby("occurrence")["source_row"].agg(["min", "max"]) + 1
        groups.append({
            "source_file": name, "date": day.date(), "weekday": day.day_name(),
            "timestamps": part["timestamp"].nunique(), "rows": len(part),
            "first_timestamp": part["timestamp"].min(), "last_timestamp": part["timestamp"].max(),
            "block_line_ranges": "; ".join(f"occurrence {o}: lines {a}-{b}" for o, (a, b) in blocks.iterrows()),
            "all_values_identical": True,
            "dst_switch_date": dst_association(day),
        })

    ooo = out_of_order.copy()
    ooo["line_number"] = ooo["source_row"] + 1
    ooo["raw_line"] = [lines[f][r] for f, r in zip(ooo["source_file"].astype(str), ooo["source_row"])]
    ooo["previous_raw_line"] = [lines[f][r - 1] for f, r in zip(ooo["source_file"].astype(str), ooo["source_row"])]
    ooo["kind"] = np.where(ooo["timestamp"] == ooo["previous_timestamp"], "repeat_of_previous", "earlier_than_previous")
    ooo["dst_switch_date"] = ooo["timestamp"].map(dst_association)
    ooo = ooo[["source_file", "line_number", "kind", "raw_line", "previous_raw_line", "dst_switch_date"]]

    return {"conflicting": conflicting, "conflict_context": pd.DataFrame(context),
            "identical_groups": pd.DataFrame(groups), "out_of_order": ooo}


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------
def classify_gap_hypothesis(start: pd.Timestamp, end: pd.Timestamp, audit_category: str) -> tuple[str, str]:
    """(category, basis) for a non-short gap. Every category is a hypothesis."""
    if audit_category == "weekend":
        return "likely_weekend_or_market_closure", "Fri/Sat -> Sun/Mon within weekend threshold"
    first_day, last_day = start.normalize(), end.normalize()
    for year in {first_day.year, last_day.year}:
        for event, day in dst_switch_dates(year).items():
            if first_day - pd.Timedelta(days=1) <= day <= last_day + pd.Timedelta(days=1):
                return "possible_dst_effect", f"touches {event} {day.date()}"
    names = []
    for day in pd.date_range(first_day, last_day, freq="D"):
        names += holiday_calendar(day.year).get(day, [])
    if names:
        return "possible_holiday", ", ".join(dict.fromkeys(names))
    return "unexplained", ""


def gap_report(raw: pd.DataFrame, audit_cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    gaps = detect_gaps(raw["timestamp"], expected_minutes=audit_cfg["expected_bar_minutes"],
                       short_gap_max_minutes=audit_cfg["short_gap_max_minutes"],
                       weekend_max_hours=audit_cfg["weekend_max_hours"])
    long = gaps[gaps["category"] != "intraweek_short"].copy()
    classified = [classify_gap_hypothesis(a, b, c) for a, b, c in
                  long[["last_bar_before", "first_bar_after", "category"]].itertuples(index=False)]
    long["hypothesis_category"] = [c for c, _ in classified]
    long["hypothesis_basis"] = [b for _, b in classified]
    long["start_weekday"] = long["last_bar_before"].dt.day_name()
    long = long.rename(columns={"category": "audit_category"})
    return long, gaps


# ---------------------------------------------------------------------------
# Decision table
# ---------------------------------------------------------------------------
def consistency_counts(obs: pd.DataFrame, column_suffix: str) -> dict[str, tuple[int, int]]:
    return {h: (int(obs[f"{h}{column_suffix}"].sum()), len(obs)) for h in HYPOTHESES}


def format_counts(counts: dict[str, tuple[int, int]]) -> str:
    return ", ".join(f"{h.split('_')[0]} {k}/{n}" for h, (k, n) in counts.items())


def support_status(counts: dict[str, tuple[int, int]]) -> str:
    """Name the hypotheses consistent with every check, without claiming verification."""
    full = [h for h, (k, n) in counts.items() if n and k == n]
    if len(full) == 1:
        return f"Only {full[0]} is consistent with all checks; hypothesis, not verified against a UTC source"
    if full:
        return f"Several hypotheses fit all checks ({', '.join(full)}); unresolved"
    return "No hypothesis fits all checks; unresolved"


def change_point_status(us_windows: pd.DataFrame) -> str:
    """Bracket the switch from H2-like to H3-like behaviour using the US anchor windows."""
    ordered = us_windows.assign(order=us_windows["year"] * 10 + us_windows["part"].eq("window_autumn"))
    ordered = ordered[ordered["decisive"]].sort_values("order")
    h2_only = ordered[ordered["H2_america_new_york_consistent"] & ~ordered["H3_ny_offset_eu_dates_consistent"]]
    h3_only = ordered[ordered["H3_ny_offset_eu_dates_consistent"] & ~ordered["H2_america_new_york_consistent"]]
    if h2_only.empty or h3_only.empty:
        return "No clear change point in the anchor windows"
    last_h2, first_h3 = h2_only.iloc[-1], h3_only.iloc[0]
    later_h2 = h2_only[h2_only["order"] > first_h3["order"]]
    status = (f"Decisive windows only (ratio >= {DECISIVE_RATIO}). Last H2-like window: {last_h2['year']} {last_h2['part']}; first H3-like window: "
              f"{first_h3['year']} {first_h3['part']}")
    if len(later_h2):
        status += "; H2-like windows after the change: " + ", ".join(
            f"{y} {p}" for y, p in later_h2[["year", "part"]].values)
    return status + ". Hypothesis, not verified"


def decision_table(r: dict) -> pd.DataFrame:
    era = r["anchors_by_era"]
    early, late = era[era["era"] == "2015-2018"], era[era["era"] == "2019-2026"]
    opens = r["weekly_opens"]
    early_opens, late_opens = opens[opens["year"] <= 2018], opens[opens["year"] >= 2019]
    yearly = r["anchors_by_year"]
    us_win = yearly[(yearly["anchor"] == "us_0830_release") & yearly["part"].str.startswith("window")]
    win_summary = "; ".join(f"{y} {p.split('_')[1]}: {t}" for y, p, t in us_win[["year", "part", "observed_time"]].values)
    autumn_2024 = r["transitions"].query("year == 2024 and event in ['eu_end', 'us_end']")
    early_counts, late_counts = consistency_counts(early, "_consistent"), consistency_counts(late, "_consistent")
    groups = r["duplicates"]["identical_groups"]
    cont = r["repeat_continuity"]
    daily_2024 = r["autumn_2024_daily"]
    window_2024 = daily_2024[daily_2024["regime"] == "us_summer_eu_standard"]
    spring = r["transitions"][r["transitions"]["event"] == "eu_start"]
    spring_holes = spring[spring["long_gaps_on_day"].str.contains(r"\(60 bars\)", regex=True)]
    h1_contradicted = any(c["H1_fixed_utc-5"][0] < c["H1_fixed_utc-5"][1] for c in (early_counts, late_counts))

    rows = [
        ("Is the raw clock fixed UTC-5 (EST, no DST)?",
         "Documented: HistData FAQ says EST without DST. Observed: intraday anchor consistency "
         f"2015-2018 {format_counts(early_counts)}; 2019-2026 {format_counts(late_counts)}.",
         "Contradicted by observed evidence" if h1_contradicted else "Not contradicted by anchors",
         "Ask HistData which clock the M1 ASCII files use; compare overlapping days with an independent "
         "UTC-stamped M1 source"),
        ("What clock do 2015-2018 timestamps follow?",
         f"Intraday anchors 2015-2018: {format_counts(early_counts)}. Weekly opens 2015-2018 "
         f"(17:00 NY convention): {format_counts(consistency_counts(early_opens, '_consistent_hour'))}.",
         support_status(early_counts),
         "Cross-check against an independent UTC-stamped source for several weeks in each regime"),
        ("What clock do 2019-2026 timestamps follow?",
         f"Intraday anchors 2019-2026: {format_counts(late_counts)}. Weekly opens 2019-2026: "
         f"{format_counts(consistency_counts(late_opens, '_consistent_hour'))}. See dst_transitions.csv "
         "for the switch-Sunday hours.",
         support_status(late_counts),
         "Same UTC cross-check; ask HistData whether their feed changed between 2018 and 2019"),
        ("When did the behaviour change?",
         f"US 08:30 anchor in US-summer/EU-standard windows by year: {win_summary}.",
         change_point_status(us_win),
         "Inspect raw data and an external source around the bracketing windows"),
        ("Why does autumn 2024 lack the October repeated hour?",
         "Transition rows: " + "; ".join(
             f"{e} {d}: open {o}, dup rows {n}, gaps [{g}]" for e, d, o, n, g in
             autumn_2024[["event", "date", "week_open", "duplicated_rows_on_day", "long_gaps_on_day"]].values)
         + ". 2024 autumn window US 08:30 anchor: "
         + ", ".join(us_win.query("year == 2024 and part == 'window_autumn'")["observed_time"])
         + ". Strongest 07:00-09:59 minute per weekday in that window: "
         + "; ".join(f"{d} {t}" for d, t in window_2024[["date", "top1"]].itertuples(index=False))
         + ". No source bars 16:00-16:59 on 2024-10-27.",
         "Unresolved. Weekday anchors fit H3, while the Sunday open fits H2 (or H3 with the first hour absent)",
         "Compare 2024-10-27 to 2024-11-03 against an external UTC source; ask HistData"),
        ("Is the 17:00 New York weekly open independently supported?",
         "Documented only as broker/industry convention (e.g. FXCM rollover at 17:00 ET; brokers vary). "
         f"Observed weekly opens consistent with 17:00 NY under each hypothesis: 2015-2018 "
         f"{format_counts(consistency_counts(early_opens, '_consistent_hour'))}; 2019-2026 "
         f"{format_counts(consistency_counts(late_opens, '_consistent_hour'))}.",
         "Partially supported (convention); used only as corroboration, never alone",
         "Not needed for the timezone decision if intraday anchors and a UTC cross-check agree"),
        ("Which 2026-07-05 conflicting record is correct?",
         f"{r['duplicates']['conflicting']['timestamp_string'].nunique()} timestamps x 2 variants, out of order "
         "(duplicates_conflicting.csv).",
         "Unresolved; no record chosen",
         "Compare with an independent source or a fresh HistData download of 2026-07"),
        ("Are the identical October repeated hours a DST artefact?",
         f"{len(groups)} identical groups; on an EU autumn switch Sunday: "
         f"{int((groups['dst_switch_date'] == 'eu_end').sum()) if len(groups) else 0}; "
         f"time spans: {', '.join(sorted({f'{a:%H:%M}-{b:%H:%M}' for a, b in groups[['first_timestamp', 'last_timestamp']].itertuples(index=False)})) if len(groups) else 'none'}."
         + f" Second copy equal to first: {int(cont['copies_equal'].sum())}/{len(cont)}. "
         "Weekly open earlier that same evening already matches the post-switch offset (dst_transitions.csv), "
         "and weekday anchors after it match the same offset, so the repeat is not a persistent clock change.",
         "Origin unresolved; a vendor processing artefact is plausible. Whether the copy replaced a real "
         "hour of data is unknown",
         "UTC cross-check of those Sunday evenings; ask HistData"),
        ("Is the March missing hour real missing data or a clock jump?",
         f"EU spring switch Sundays with a ~60-bar gap: {len(spring_holes)}/{len(spring)} "
         f"({', '.join(str(y) for y in spring_holes['year'])}); TXT tick gaps on those days: "
         f"{', '.join(t for t in spring_holes['txt_tick_gaps_ge_30min'] if t) or 'none'}. "
         "Weekly open before the hole and weekday anchors after it imply the same offset. Price change across "
         f"the hole: {', '.join(f'{c:.1f}' for c in r['spring_holes']['change_pips'])} pips vs median "
         f"61-minute change {r['spring_holes']['median_61min_change_pips'].iloc[0] if len(r['spring_holes']) else 'n/a'} pips.",
         "Unresolved: not a persistent clock shift; consistent with one lost hour of data or a vendor artefact",
         "UTC cross-check of those Sundays"),
        ("What caused the Feb-Jul 2023 gaps?",
         f"{int(((r['gaps_long'].first_bar_after.dt.year == 2023) & (r['gaps_long'].hypothesis_category == 'unexplained')).sum())} "
         "unexplained long gaps in 2023 (gaps_long.csv).",
         "Unexplained (a source-feed outage is plausible); not verified",
         "Compare against an independent source; check whether a newer HistData 2023 file differs"),
        ("Are the remaining unexplained gaps real outages?",
         f"{int((r['gaps_long'].hypothesis_category == 'unexplained').sum())} unexplained long gaps in total.",
         "Unexplained",
         "Spot-check largest ones against an independent source"),
    ]
    return pd.DataFrame(rows, columns=["question", "evidence", "status", "next_verification_step"])


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_investigation(root: Path, config: dict) -> dict:
    data_cfg = config["data"]
    raw_dir = root / data_cfg["raw_dir"]
    csv_paths = discover_raw_files(raw_dir, data_cfg["raw_csv_glob"])
    txt_paths = sorted(raw_dir.glob(data_cfg["raw_csv_glob"].replace(".csv", ".txt")))
    parquet_paths = [root / p for p in data_cfg["parquet_files"].values()]
    sources = csv_paths + txt_paths + parquet_paths
    hashes_before = {str(p): sha256_file(p) for p in sources}

    raw = load_raw(csv_paths)
    gaps_long, gaps_all = gap_report(raw, config["audit"])
    view = returns_view(raw)
    view["era"] = np.where(view["year"] <= 2018, "2015-2018", "2019-2026")
    txt_gaps = pd.concat([parse_gap_report(p)["gaps"] for p in txt_paths], ignore_index=True)
    opens = weekly_open_observations(gaps_all)

    results = {
        "predictions": prediction_table(),
        "anchors_by_era": intraday_anchor_observations(view, ["era", "regime"]),
        "anchors_by_year": intraday_anchor_observations(view, ["year", "part"]),
        "weekly_opens": opens,
        "weekly_opens_by_year": summarize_weekly_opens(opens, ["year", "part"]),
        "transitions": dst_transition_days(raw, gaps_all, txt_gaps),
        "duplicates": duplicate_reports(raw, {p.name: p for p in csv_paths}),
        "gaps_long": gaps_long,
        "autumn_2024_daily": daily_release_minutes(view, "2024-10-21", "2024-11-09"),
        "config": config,
    }
    results["repeat_continuity"] = repeated_block_continuity(raw, results["duplicates"]["identical_groups"])
    results["spring_holes"] = spring_hole_price_change(unique_closes(raw), results["transitions"])
    results["gap_summary"] = (gaps_long.assign(year=gaps_long["first_bar_after"].dt.year)
                              .groupby(["year", "hypothesis_category"])["missing_bars"].agg(["size", "sum"])
                              .rename(columns={"size": "gaps", "sum": "missing_bars"}).reset_index())
    results["decisions"] = decision_table(results)
    results["hashes_before"] = hashes_before
    results["hashes_after"] = {str(p): sha256_file(p) for p in sources}
    return results


def render_summary(r: dict) -> str:
    unchanged = r["hashes_before"] == r["hashes_after"]
    era = r["anchors_by_era"]
    era_cols = ["era", "regime", "anchor", "weekdays", "observed_time"] + [f"{h}_predicts" for h in HYPOTHESES]
    yearly = r["anchors_by_year"]
    win = yearly[yearly["part"].str.startswith("window")]
    win_cols = ["year", "part", "anchor", "weekdays", "observed_time", "strength_ratio_top_vs_second", "decisive"]
    dups = r["duplicates"]
    gaps = r["gaps_long"]
    gap_counts = gaps.groupby("hypothesis_category")["missing_bars"].agg(["size", "sum"]).reset_index()
    unexplained = gaps[gaps["hypothesis_category"] == "unexplained"].sort_values("missing_bars", ascending=False)
    unexplained_2023 = unexplained["first_bar_after"].dt.year == 2023
    top_unexplained = unexplained[~unexplained_2023].head(15)

    sections = [
        "# Timestamp, duplicate and gap investigation (read-only)",
        f"Generated (UTC): {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S}. "
        "All times are naive source-clock values. No data was modified, sorted, deduplicated or converted on disk. "
        f"Source files unchanged during run: **{'YES' if unchanged else 'NO'}** ({len(r['hashes_before'])} files).",
        "## 1. Documented facts",
        "- HistData FAQ (histdata.com/f-a-q): *\"The timezone of all data is: Eastern Standard Time (EST) "
        "time-zone WITHOUT Day Light Savings adjustments.\"* Bars are built from the tick **bid** price.\n"
        "- The local TXT status reports contain no timezone statement.\n"
        "- 17:00 New York as the FX week/day boundary is a broker/industry convention (e.g. FXCM rollover help), "
        "with broker-to-broker variation. It is not an exchange rule.\n"
        "- Anchor events with documented clock times: US releases at 08:30 New York; WM/Reuters fix at 16:00 London.",
        "## 2. Hypotheses and their predictions (source clock)",
        "\n".join(f"- **{h}**: {d}" for h, d in HYPOTHESES.items()),
        md_table(r["predictions"]),
        "## 3. Observed evidence: intraday anchors by era",
        "Observed time = the candidate minute with the strongest activity (see CSV for strength ratios). "
        "Weekdays only; duplicated timestamps excluded.",
        md_table(era[era_cols]),
        "## 4. Observed evidence: US-summer/EU-standard windows by year",
        "These windows are the only periods where H2 and H3 disagree; they are short (about 15 spring "
        "and 5 autumn weekdays per year), so individual years are noisier. Only rows with "
        f"strength ratio >= {DECISIVE_RATIO} are treated as decisive.",
        md_table(win[win_cols]),
        "## 5. Weekly opens by year and regime",
        md_table(r["weekly_opens_by_year"]),
        "## 6. DST switch Sundays",
        md_table(r["transitions"]),
        "Repeated October blocks: copy equality and price joins (pips):",
        md_table(r["repeat_continuity"]) if len(r["repeat_continuity"]) else "none",
        "March holes: price change across the gap:",
        md_table(r["spring_holes"]) if len(r["spring_holes"]) else "none",
        "Autumn 2024: strongest 07:00-09:59 minutes per weekday (US releases at 08:30 New York):",
        md_table(r["autumn_2024_daily"]),
        "## 7. Duplicates",
        f"- Identical duplicate groups: {len(dups['identical_groups'])} "
        f"({int(dups['identical_groups']['rows'].sum()) if len(dups['identical_groups']) else 0} rows), "
        f"of which on a DST switch date: {int((dups['identical_groups']['dst_switch_date'] != '').sum()) if len(dups['identical_groups']) else 0}.",
        md_table(dups["identical_groups"]) if len(dups["identical_groups"]) else "",
        f"- Conflicting duplicate rows: {len(dups['conflicting'])} "
        f"({dups['conflicting']['timestamp_string'].nunique()} timestamps). No record is preferred.",
        md_table(dups["conflicting"].drop(columns=["raw_line"])) if len(dups["conflicting"]) else "",
        "Context lines around the conflicting block (original order):",
        md_table(dups["conflict_context"]) if len(dups["conflict_context"]) else "",
        f"- Out-of-order rows: {len(dups['out_of_order'])}",
        md_table(dups["out_of_order"]) if len(dups["out_of_order"]) else "",
        "## 8. Gaps (all categories are hypotheses unless independently verified)",
        "Gaps longer than the short-gap threshold, plus weekends. Precedence: weekend, then DST date, "
        "then holiday calendar, else unexplained. Holiday dates are plausible feed closures, not verified market closures.",
        md_table(gap_counts.rename(columns={"size": "gaps", "sum": "missing_bars"})),
        f"Unexplained gaps in 2023: {int(unexplained_2023.sum())} "
        f"({int(unexplained.loc[unexplained_2023, 'missing_bars'].sum())} missing bars). "
        "Largest unexplained gaps outside 2023:",
        md_table(top_unexplained[["last_bar_before", "first_bar_after", "missing_bars", "start_weekday"]]),
        "## 9. Decision table",
        md_table(r["decisions"]),
    ]
    return "\n\n".join(s for s in sections if s) + "\n"


def write_investigation(r: dict, reports_dir: Path, stamp: str | None = None) -> Path:
    stamp = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(reports_dir) / f"timestamp_investigation_{stamp}"
    run_dir.mkdir(parents=False, exist_ok=False)
    write_new(run_dir / "summary.md", render_summary(r))
    tables = {
        "timezone_predictions": r["predictions"],
        "timezone_anchors_by_era": r["anchors_by_era"],
        "timezone_anchors_by_year": r["anchors_by_year"],
        "timezone_weekly_opens": r["weekly_opens"],
        "timezone_weekly_opens_by_year": r["weekly_opens_by_year"],
        "dst_transitions": r["transitions"],
        "dst_repeated_block_continuity": r["repeat_continuity"],
        "dst_spring_hole_price_change": r["spring_holes"],
        "timezone_autumn_2024_daily": r["autumn_2024_daily"],
        "duplicates_conflicting": r["duplicates"]["conflicting"],
        "duplicates_conflict_context": r["duplicates"]["conflict_context"],
        "duplicates_identical_groups": r["duplicates"]["identical_groups"],
        "duplicates_out_of_order": r["duplicates"]["out_of_order"],
        "gaps_long": r["gaps_long"],
        "gaps_summary": r["gap_summary"],
        "decision_table": r["decisions"],
    }
    for name, table in tables.items():
        write_new(run_dir / f"{name}.csv", table.to_csv(index=False))
    write_new(run_dir / "source_hashes.json",
              json.dumps({"before": r["hashes_before"], "after": r["hashes_after"]}, indent=2))
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only timestamp/duplicate/gap investigation.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="config/research.yaml")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config = load_config(root / args.config)
    results = run_investigation(root, config)
    run_dir = write_investigation(results, root / config["reports"]["dir"])
    unchanged = results["hashes_before"] == results["hashes_after"]
    print(f"Report written to {run_dir}")
    print(f"Source files unchanged: {'YES' if unchanged else 'NO'}")
    if not unchanged:
        raise SystemExit("Source file hashes changed during the investigation.")


if __name__ == "__main__":
    main()
