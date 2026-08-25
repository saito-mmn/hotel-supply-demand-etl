"""Records exchanged by the municipality-level ETL pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MunicipalityMonthlyRecord:
    year: int
    month: int
    prefecture_code: int
    prefecture_name: str
    municipality_name: str
    total_guests: int | None
    japanese_guests: int | None
    foreign_guests: int | None
    occupied_rooms: float | None
    occupancy_rate: float | None
    population_facilities: int | None
    responding_facilities: int | None
    room_size_class: str = "total"
    release_type: str = "second_preliminary"
