from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MonthlyRecord:
    year: int
    month: int
    prefecture_code: int
    prefecture_name: str
    total_guests: int | None
    foreign_guests: int | None
    japanese_guests: int | None
    occupancy_rate: float | None
    facilities: int | None
    release_type: str = "final"
