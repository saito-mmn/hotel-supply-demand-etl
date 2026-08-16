from __future__ import annotations

from collections import Counter

from .models import MonthlyRecord


class DataQualityError(ValueError):
    pass


def validate_records(records: list[MonthlyRecord], expected_years: set[int]) -> dict[str, int]:
    expected = len(expected_years) * 12 * 47
    errors: list[str] = []
    if len(records) != expected:
        errors.append(f"row count {len(records)} != {expected}")
    keys = [(r.year, r.month, r.prefecture_code, r.release_type) for r in records]
    duplicates = sum(count - 1 for count in Counter(keys).values() if count > 1)
    if duplicates:
        errors.append(f"duplicate keys: {duplicates}")
    names_by_code: dict[int, set[str]] = {}
    for record in records:
        names_by_code.setdefault(record.prefecture_code, set()).add(record.prefecture_name)
    inconsistent_names = [code for code, names in names_by_code.items() if len(names) != 1]
    if inconsistent_names:
        errors.append(f"inconsistent prefecture names: {inconsistent_names}")
    for record in records:
        if record.year not in expected_years or not 1 <= record.month <= 12 or not 1 <= record.prefecture_code <= 47:
            errors.append(f"invalid dimension: {record}")
            break
        if record.occupancy_rate is not None and not 0 <= record.occupancy_rate <= 100:
            errors.append(f"invalid occupancy rate: {record}")
            break
        if any(value is not None and value < 0 for value in (record.total_guests, record.foreign_guests, record.facilities)):
            errors.append(f"negative value: {record}")
            break
        if record.total_guests is not None and record.foreign_guests is not None and record.foreign_guests > record.total_guests:
            errors.append(f"foreign guests exceed total: {record}")
            break
    if errors:
        raise DataQualityError("; ".join(errors))
    return {"rows": len(records), "years": len(expected_years), "duplicates": 0}
