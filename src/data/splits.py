"""Research splits and the test-set guard.

Splits are defined in config/splits.yaml on the UTC clock. Every read of processed
data should go through this module: a read whose time range touches a locked split
raises TestSetLockedError unless the caller passes unlock_test=True explicitly.
A read without a time range counts as touching everything.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

DEFAULT_SPLITS = Path("config/splits.yaml")


class TestSetLockedError(PermissionError):
    """Raised when locked (test) data is requested without unlock_test=True."""

    __test__ = False  # not a pytest class


@dataclass(frozen=True)
class Split:
    name: str
    start: pd.Timestamp          # inclusive, UTC
    end: pd.Timestamp            # exclusive, UTC (config end day + 1)
    locked: bool = False
    exclude_flags: tuple[str, ...] = ()


def load_splits(path: Path = DEFAULT_SPLITS) -> dict[str, Split]:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    splits = {}
    for name, s in cfg["splits"].items():
        start = pd.Timestamp(str(s["start"]), tz="UTC")
        end = pd.Timestamp(str(s["end"]), tz="UTC") + pd.Timedelta(days=1)
        if start != start.normalize() or end <= start:
            raise ValueError(f"split {name}: bad range {s['start']} .. {s['end']}")
        splits[name] = Split(name, start, end, bool(s.get("locked", False)), tuple(s.get("exclude_flags", [])))
    ordered = sorted(splits.values(), key=lambda s: s.start)
    for a, b in zip(ordered, ordered[1:]):
        if b.start < a.end:
            raise ValueError(f"splits {a.name} and {b.name} overlap")
    return splits


def locked_overlap(start, end, splits: dict[str, Split]) -> list[str]:
    """Locked splits that intersect [start, end); None means unbounded on that side."""
    lo = pd.Timestamp.min.tz_localize("UTC") if start is None else pd.Timestamp(start)
    hi = pd.Timestamp.max.tz_localize("UTC") if end is None else pd.Timestamp(end)
    return [s.name for s in splits.values() if s.locked and lo < s.end and s.start < hi]


def guard_range(start, end, splits: dict[str, Split], unlock_test: bool = False) -> None:
    hit = locked_overlap(start, end, splits)
    if hit and unlock_test is not True:
        raise TestSetLockedError(f"range {start} .. {end} touches locked split(s) {hit}; "
                                 "pass unlock_test=True only for an approved final evaluation")


def read_range(path: Path, start, end, splits: dict[str, Split], time_column: str,
               columns: list[str] | None = None, unlock_test: bool = False) -> pd.DataFrame:
    """Rows of a Parquet file with start <= time_column < end, after the guard."""
    guard_range(start, end, splits, unlock_test)
    filters = []
    if start is not None:
        filters.append((time_column, ">=", pd.Timestamp(start)))
    if end is not None:
        filters.append((time_column, "<", pd.Timestamp(end)))
    return pd.read_parquet(path, columns=columns, filters=filters or None)


def read_m1_split(path: Path, name: str, splits: dict[str, Split], columns: list[str] | None = None,
                  unlock_test: bool = False) -> tuple[pd.DataFrame, int]:
    """Processed M1 rows of one split, with its exclude_flags applied; also the excluded row count."""
    s = splits[name]
    if columns is not None:
        columns = list(dict.fromkeys([*columns, *s.exclude_flags]))
    df = read_range(path, s.start, s.end, splits, "timestamp_utc", columns, unlock_test)
    drop = pd.Series(False, index=df.index)
    for flag in s.exclude_flags:
        drop |= df[flag].astype(bool)
    return df[~drop].reset_index(drop=True), int(drop.sum())
