"""Within-window seasonal-variation metrics shared by the static reports and BI export.

Kept here, independent of both the prefecture analysis (LTM-window) and BI
export (calendar-year) call sites, so "how seasonal variation is measured"
has exactly one definition instead of being reimplemented per consumer.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class SeasonalProfile:
    coefficient_of_variation: float
    range_pp: float
    peak_month: int
    bottom_month: int
    average: float


def seasonal_profile(monthly_values: list[float]) -> SeasonalProfile:
    """Summarize within-window seasonal swing from consecutive monthly values.

    ``peak_month``/``bottom_month`` are 1-based positions within
    ``monthly_values`` (e.g. calendar month for a 12-month calendar-year
    window), not calendar months in general -- callers with a different
    window shape are responsible for mapping the index back themselves.
    """
    if not monthly_values:
        raise ValueError("seasonal_profile requires at least one monthly value")
    average = statistics.mean(monthly_values)
    return SeasonalProfile(
        coefficient_of_variation=statistics.pstdev(monthly_values) / average if average else 0.0,
        range_pp=max(monthly_values) - min(monthly_values),
        peak_month=monthly_values.index(max(monthly_values)) + 1,
        bottom_month=monthly_values.index(min(monthly_values)) + 1,
        average=average,
    )
