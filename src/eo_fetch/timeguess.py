"""Guess the data time from a file path or name (model cycles, radar, grids, daily files)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

# model cycle folder, e.g. gfs.20260915/12/atmos/...
CYCLE_PATH = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})/(\d{2})/")
# ten digits: YYYYMMDDHH (ICON: ..._2026110300_...) or YYMMDDHHMM (RADOLAN: ...-2610312220-...)
TEN_DIGITS = re.compile(r"(?<!\d)(\d{10})(?!\d)")
# eight digits with an optional time: 20260915, 20260915_001318, 20260915T0013
NAME_DATE = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?:[_T-]?(\d{2})(\d{2})(\d{2})?)?(?!\d)")
# six digits YYYYMM (monthly files), only when they look like a plausible month
YEAR_MONTH = re.compile(r"(?<!\d)(\d{4})(\d{2})(?!\d)")


def make_time(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0):
    """Return a UTC datetime, or None for an implausible year or an impossible date."""
    if not 1950 <= year <= 2100:
        return None
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    except ValueError:
        return None


def guess_time(key: str) -> datetime | None:
    """Guess the data time from a model-cycle folder or from the file name.

    Returns None when nothing plausible is found. The time is a guess: it is meant for display
    and for --start/--end filtering, and for model data it is the cycle (initialisation) time.
    """
    match = CYCLE_PATH.search(key)
    if match:
        year, month, day, hour = (int(group) for group in match.groups())
        return make_time(year, month, day, hour)
    name = key.rsplit("/", 1)[-1]
    match = TEN_DIGITS.search(name)
    if match:
        digits = match.group(1)
        full = make_time(int(digits[:4]), int(digits[4:6]), int(digits[6:8]), int(digits[8:10]))
        if full:
            return full
        short = make_time(
            2000 + int(digits[:2]),
            int(digits[2:4]),
            int(digits[4:6]),
            int(digits[6:8]),
            int(digits[8:10]),
        )
        if short:
            return short
    match = NAME_DATE.search(name)
    if match:
        year, month, day, hour, minute, second = (int(g) if g else 0 for g in match.groups())
        found = make_time(year, month, day, hour, minute, second)
        if found:
            return found
    match = YEAR_MONTH.search(name)
    if match:
        return make_time(int(match.group(1)), int(match.group(2)), 1)
    return None
