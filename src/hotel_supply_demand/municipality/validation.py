"""Quality checks for municipality-level monthly records."""

from __future__ import annotations

from collections import Counter, defaultdict
import math

from .models import MunicipalityMonthlyRecord


class MunicipalityDataQualityError(ValueError):
    pass


ROOM_SIZE_CLASSES = {"total", "1_to_9", "10_to_19", "20_plus"}


def _complete_sum(values: list[int | None]) -> int | None:
    return sum(values) if all(value is not None for value in values) else None


def validate_municipality_records(records: list[MunicipalityMonthlyRecord]) -> dict:
    if not records:
        raise MunicipalityDataQualityError("municipality records are empty")
    keys = [
        (
            record.year,
            record.month,
            record.prefecture_code,
            record.municipality_name,
            record.room_size_class,
            record.release_type,
        )
        for record in records
    ]
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    if duplicates:
        raise MunicipalityDataQualityError(
            f"duplicate municipality record keys: {duplicates[:5]}"
        )

    periods = {(record.year, record.month, record.release_type) for record in records}
    if len(periods) != 1:
        raise MunicipalityDataQualityError(f"records must contain one period: {sorted(periods)}")

    grouped: dict[tuple[int, str], dict[str, MunicipalityMonthlyRecord]] = defaultdict(dict)
    for record in records:
        if not 1 <= record.prefecture_code <= 47:
            raise MunicipalityDataQualityError(
                f"prefecture code out of range: {record.prefecture_code}"
            )
        if not record.prefecture_name or not record.municipality_name:
            raise MunicipalityDataQualityError("prefecture and municipality names are required")
        if record.room_size_class not in ROOM_SIZE_CLASSES:
            raise MunicipalityDataQualityError(
                f"unknown room size class: {record.room_size_class}"
            )
        for field in (
            "total_guests",
            "japanese_guests",
            "foreign_guests",
            "occupied_rooms",
            "population_facilities",
            "responding_facilities",
        ):
            value = getattr(record, field)
            if value is not None and value < 0:
                raise MunicipalityDataQualityError(
                    f"negative {field}: {record.municipality_name} {value}"
                )
        if record.occupancy_rate is not None and not 0 <= record.occupancy_rate <= 200:
            raise MunicipalityDataQualityError(
                f"occupancy rate out of range: {record.municipality_name}"
            )
        if (
            record.total_guests is not None
            and record.japanese_guests is not None
            and record.foreign_guests is not None
            and record.japanese_guests + record.foreign_guests != record.total_guests
        ):
            raise MunicipalityDataQualityError(
                f"guest components do not equal total: {record.municipality_name}"
            )
        if (
            record.responding_facilities is not None
            and record.population_facilities is not None
            and record.responding_facilities > record.population_facilities
        ):
            raise MunicipalityDataQualityError(
                f"responding facilities exceed population: {record.municipality_name}"
            )
        grouped[(record.prefecture_code, record.municipality_name)][
            record.room_size_class
        ] = record

    for municipality, by_class in grouped.items():
        if set(by_class) != ROOM_SIZE_CLASSES:
            raise MunicipalityDataQualityError(
                f"incomplete room size classes for {municipality}: {sorted(by_class)}"
            )
        total = by_class["total"]
        detail = [by_class[name] for name in ("1_to_9", "10_to_19", "20_plus")]
        population_sum = _complete_sum([record.population_facilities for record in detail])
        response_sum = _complete_sum([record.responding_facilities for record in detail])
        if total.population_facilities != population_sum:
            raise MunicipalityDataQualityError(
                f"population facility total mismatch for {municipality}"
            )
        if total.responding_facilities != response_sum:
            raise MunicipalityDataQualityError(
                f"responding facility total mismatch for {municipality}"
            )
        for field in ("total_guests", "foreign_guests", "occupied_rooms"):
            detail_sum = _complete_sum([getattr(record, field) for record in detail])
            total_value = getattr(total, field)
            mismatch = (
                not math.isclose(float(total_value), float(detail_sum))
                if detail_sum is not None and total_value is not None
                else detail_sum is not None and total_value is None
            )
            if mismatch:
                raise MunicipalityDataQualityError(
                    f"{field} total mismatch for {municipality}"
                )

    year, month, release_type = next(iter(periods))
    return {
        "rows": len(records),
        "municipalities": len(grouped),
        "prefectures": len({record.prefecture_code for record in records}),
        "year": year,
        "month": month,
        "release_type": release_type,
        "non_null_total_occupancy": sum(
            record.room_size_class == "total" and record.occupancy_rate is not None
            for record in records
        ),
    }
