"""Export typed, analysis-ready CSV datasets for Tableau."""

from __future__ import annotations

import csv
import os
import shutil
import sqlite3
import tempfile
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .seasonality import seasonal_profile

PREFECTURE_FIELDS = [
    "date",
    "year",
    "month",
    "month_name",
    "country_code",
    "country_name",
    "geography_level",
    "prefecture_code",
    "prefecture_name",
    "facility_type_code",
    "facility_type_name",
    "release_type",
    "data_scope",
    "guest_nights_total",
    "guest_nights_japanese",
    "guest_nights_foreign",
    "foreign_share_pct",
    "occupancy_rate_pct",
    "occupancy_yoy_delta_pp",
    "occupancy_2019_delta_pp",
    "has_yoy_comparison",
    "has_2019_comparison",
    "facility_count",
    "source_file_id",
    "source_url",
    "source_filename",
    "source_published_on",
    "source_retrieved_at",
    "source_sha256",
    "dataset_generated_at",
]

MUNICIPALITY_FIELDS = [
    "date",
    "year",
    "month",
    "month_name",
    "country_code",
    "country_name",
    "geography_level",
    "prefecture_code",
    "prefecture_name",
    "municipality_id",
    "municipality_key",
    "municipality_name",
    "room_size_class",
    "release_type",
    "data_scope",
    "record_status",
    "guest_nights_total",
    "guest_nights_japanese",
    "guest_nights_foreign",
    "foreign_share_pct",
    "occupied_rooms",
    "occupancy_rate_pct",
    "occupancy_yoy_delta_pp",
    "occupancy_2019_delta_pp",
    "has_yoy_comparison",
    "has_2019_comparison",
    "population_facility_count",
    "responding_facility_count",
    "coverage_start_date",
    "coverage_end_date",
    "coverage_months",
    "source_file_id",
    "source_stat_inf_id",
    "source_url",
    "source_filename",
    "source_published_on",
    "source_retrieved_at",
    "source_sha256",
    "dataset_generated_at",
]

# One row per prefecture per completed calendar year: a cross-sectional
# screening/ranking dataset (which markets are foreign-guest heavy, which
# swing most between peak and trough season) distinct from the monthly
# time series above. Seasonal variation is measured within a single
# calendar year on purpose -- see hotel_supply_demand.seasonality -- so it
# is not diluted by multi-year trend or the pandemic recovery.
PREFECTURE_ANNUAL_SUMMARY_FIELDS = [
    "year",
    "prefecture_code",
    "prefecture_name",
    "release_type",
    "guest_nights_total",
    "foreign_share_pct",
    "occupancy_rate_pct_avg",
    "occupancy_seasonal_cv",
    "occupancy_seasonal_range_pp",
    "occupancy_peak_month",
    "occupancy_bottom_month",
    "facility_count",
    "source_url",
    "source_filename",
    "source_published_on",
    "source_retrieved_at",
    "source_sha256",
    "dataset_generated_at",
]

METADATA_FIELDS = [
    "dataset_name",
    "row_count",
    "observed_row_count",
    "min_date",
    "max_date",
    "geography_level",
    "release_type",
    "data_scope",
    "source_name",
    "source_url",
    "dataset_generated_at",
    "notes",
]

SOURCE_NAME = "観光庁 宿泊旅行統計調査"
SOURCE_URL = "https://www.mlit.go.jp/kankocho/tokei_hakusyo/shukuhakutokei.html"


class BiExportError(ValueError):
    """Raised when the canonical database cannot produce a safe BI export."""


def _date(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}-01"


def _month_name(month: int) -> str:
    return f"{month}月"


def _foreign_share(foreign: int | None, total: int | None) -> float | None:
    if foreign is None or total in (None, 0):
        return None
    return foreign / total * 100


def _delta(current: float | None, comparison: float | None) -> float | None:
    if current is None or comparison is None:
        return None
    return current - comparison


def _periods(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    start_index = start[0] * 12 + start[1] - 1
    end_index = end[0] * 12 + end[1] - 1
    periods = []
    for index in range(start_index, end_index + 1):
        year, zero_based_month = divmod(index, 12)
        periods.append((year, zero_based_month + 1))
    return periods


def _require_tables(connection: sqlite3.Connection) -> None:
    required = {
        "source_files",
        "prefectures",
        "monthly_prefecture_market",
        "national_occupancy",
        "municipality_source_files",
        "municipalities",
        "monthly_municipality_market",
    }
    present = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        )
    }
    missing = sorted(required - present)
    if missing:
        raise BiExportError(f"BI export requires database objects: {', '.join(missing)}")


def _prefecture_rows(
    connection: sqlite3.Connection, base_year: int, generated_at: str
) -> list[dict[str, Any]]:
    facts = connection.execute(
        """SELECT f.year,f.month,f.prefecture_code,p.name AS prefecture_name,
                  f.release_type,f.total_guests,f.japanese_guests,f.foreign_guests,
                  f.occupancy_rate,f.facilities,f.source_file_id,
                  s.url,s.filename,s.published_on,s.retrieved_at,s.sha256
             FROM monthly_prefecture_market AS f
             JOIN prefectures AS p ON p.code=f.prefecture_code
             JOIN source_files AS s ON s.id=f.source_file_id
            WHERE f.release_type='final'
            ORDER BY f.year,f.month,f.prefecture_code"""
    ).fetchall()
    national = connection.execute(
        """SELECT n.year,n.month,n.release_type,n.occupancy_rate,n.source_file_id,
                  s.url,s.filename,s.published_on,s.retrieved_at,s.sha256
             FROM national_occupancy AS n
             JOIN source_files AS s ON s.id=n.source_file_id
            WHERE n.release_type='final'
            ORDER BY n.year,n.month"""
    ).fetchall()
    if not facts or not national:
        raise BiExportError("prefecture or national monthly data is empty")

    occupancy = {
        (row["year"], row["month"], row["prefecture_code"]): row["occupancy_rate"] for row in facts
    }
    national_occupancy = {(row["year"], row["month"]): row["occupancy_rate"] for row in national}
    rows: list[dict[str, Any]] = []
    for row in facts:
        previous = occupancy.get((row["year"] - 1, row["month"], row["prefecture_code"]))
        base = occupancy.get((base_year, row["month"], row["prefecture_code"]))
        rows.append(
            {
                "date": _date(row["year"], row["month"]),
                "year": row["year"],
                "month": row["month"],
                "month_name": _month_name(row["month"]),
                "country_code": "JP",
                "country_name": "日本",
                "geography_level": "prefecture",
                "prefecture_code": f"{row['prefecture_code']:02d}",
                "prefecture_name": row["prefecture_name"],
                "facility_type_code": "all",
                "facility_type_name": "全施設",
                "release_type": row["release_type"],
                "data_scope": "prefecture_all_facilities",
                "guest_nights_total": row["total_guests"],
                "guest_nights_japanese": row["japanese_guests"],
                "guest_nights_foreign": row["foreign_guests"],
                "foreign_share_pct": _foreign_share(row["foreign_guests"], row["total_guests"]),
                "occupancy_rate_pct": row["occupancy_rate"],
                "occupancy_yoy_delta_pp": _delta(row["occupancy_rate"], previous),
                "occupancy_2019_delta_pp": _delta(row["occupancy_rate"], base),
                "has_yoy_comparison": int(
                    row["occupancy_rate"] is not None and previous is not None
                ),
                "has_2019_comparison": int(row["occupancy_rate"] is not None and base is not None),
                "facility_count": row["facilities"],
                "source_file_id": row["source_file_id"],
                "source_url": row["url"],
                "source_filename": row["filename"],
                "source_published_on": row["published_on"],
                "source_retrieved_at": row["retrieved_at"],
                "source_sha256": row["sha256"],
                "dataset_generated_at": generated_at,
            }
        )
    for row in national:
        previous = national_occupancy.get((row["year"] - 1, row["month"]))
        base = national_occupancy.get((base_year, row["month"]))
        rows.append(
            {
                "date": _date(row["year"], row["month"]),
                "year": row["year"],
                "month": row["month"],
                "month_name": _month_name(row["month"]),
                "country_code": "JP",
                "country_name": "日本",
                "geography_level": "national",
                "prefecture_code": "00",
                "prefecture_name": "全国",
                "facility_type_code": "all",
                "facility_type_name": "全施設",
                "release_type": row["release_type"],
                "data_scope": "official_national_occupancy",
                "guest_nights_total": None,
                "guest_nights_japanese": None,
                "guest_nights_foreign": None,
                "foreign_share_pct": None,
                "occupancy_rate_pct": row["occupancy_rate"],
                "occupancy_yoy_delta_pp": _delta(row["occupancy_rate"], previous),
                "occupancy_2019_delta_pp": _delta(row["occupancy_rate"], base),
                "has_yoy_comparison": int(previous is not None),
                "has_2019_comparison": int(base is not None),
                "facility_count": None,
                "source_file_id": row["source_file_id"],
                "source_url": row["url"],
                "source_filename": row["filename"],
                "source_published_on": row["published_on"],
                "source_retrieved_at": row["retrieved_at"],
                "source_sha256": row["sha256"],
                "dataset_generated_at": generated_at,
            }
        )
    return sorted(
        rows, key=lambda item: (item["date"], item["geography_level"], item["prefecture_code"])
    )


def _municipality_rows(
    connection: sqlite3.Connection, base_year: int, generated_at: str
) -> list[dict[str, Any]]:
    municipalities = connection.execute(
        """SELECT id,prefecture_code,prefecture_name,municipality_name
             FROM municipalities
            ORDER BY prefecture_code,municipality_name"""
    ).fetchall()
    source_rows = connection.execute(
        """SELECT id,year,month,release_type,stat_inf_id,url,filename,
                  published_on,retrieved_at,sha256
             FROM municipality_source_files
            ORDER BY year,month"""
    ).fetchall()
    fact_rows = connection.execute(
        """SELECT year,month,municipality_id,room_size_class,release_type,
                  total_guests,japanese_guests,foreign_guests,occupied_rooms,
                  occupancy_rate,population_facilities,responding_facilities,
                  source_file_id
             FROM monthly_municipality_market
            WHERE room_size_class='total' AND release_type='second_preliminary'
            ORDER BY year,month,municipality_id"""
    ).fetchall()
    if not municipalities or not source_rows or not fact_rows:
        raise BiExportError("municipality source, master, or total-room-size data is empty")

    source_by_period = {(row["year"], row["month"]): row for row in source_rows}
    start = (source_rows[0]["year"], source_rows[0]["month"])
    end = (source_rows[-1]["year"], source_rows[-1]["month"])
    periods = _periods(start, end)
    facts = {(row["year"], row["month"], row["municipality_id"]): row for row in fact_rows}
    coverage: dict[int, tuple[str, str, int]] = {}
    for municipality in municipalities:
        observed = [
            _date(row["year"], row["month"])
            for row in fact_rows
            if row["municipality_id"] == municipality["id"]
        ]
        coverage[municipality["id"]] = (min(observed), max(observed), len(observed))

    rows: list[dict[str, Any]] = []
    for municipality in municipalities:
        municipality_id = municipality["id"]
        coverage_start, coverage_end, coverage_months = coverage[municipality_id]
        for year, month in periods:
            fact = facts.get((year, month, municipality_id))
            source = source_by_period.get((year, month))
            previous = facts.get((year - 1, month, municipality_id))
            base = facts.get((base_year, month, municipality_id))
            occupancy = fact["occupancy_rate"] if fact is not None else None
            previous_occupancy = previous["occupancy_rate"] if previous is not None else None
            base_occupancy = base["occupancy_rate"] if base is not None else None
            total = fact["total_guests"] if fact is not None else None
            foreign = fact["foreign_guests"] if fact is not None else None
            rows.append(
                {
                    "date": _date(year, month),
                    "year": year,
                    "month": month,
                    "month_name": _month_name(month),
                    "country_code": "JP",
                    "country_name": "日本",
                    "geography_level": "municipality",
                    "prefecture_code": f"{municipality['prefecture_code']:02d}",
                    "prefecture_name": municipality["prefecture_name"],
                    "municipality_id": municipality_id,
                    "municipality_key": f"{municipality['prefecture_code']:02d}:{municipality['municipality_name']}",
                    "municipality_name": municipality["municipality_name"],
                    "room_size_class": "total",
                    "release_type": source["release_type"] if source is not None else None,
                    "data_scope": "principal_municipalities_total_room_size",
                    "record_status": "published" if fact is not None else "not_listed",
                    "guest_nights_total": total,
                    "guest_nights_japanese": fact["japanese_guests"] if fact is not None else None,
                    "guest_nights_foreign": foreign,
                    "foreign_share_pct": _foreign_share(foreign, total),
                    "occupied_rooms": fact["occupied_rooms"] if fact is not None else None,
                    "occupancy_rate_pct": occupancy,
                    "occupancy_yoy_delta_pp": _delta(occupancy, previous_occupancy),
                    "occupancy_2019_delta_pp": _delta(occupancy, base_occupancy),
                    "has_yoy_comparison": int(
                        occupancy is not None and previous_occupancy is not None
                    ),
                    "has_2019_comparison": int(
                        occupancy is not None and base_occupancy is not None
                    ),
                    "population_facility_count": fact["population_facilities"]
                    if fact is not None
                    else None,
                    "responding_facility_count": fact["responding_facilities"]
                    if fact is not None
                    else None,
                    "coverage_start_date": coverage_start,
                    "coverage_end_date": coverage_end,
                    "coverage_months": coverage_months,
                    "source_file_id": source["id"] if source is not None else None,
                    "source_stat_inf_id": source["stat_inf_id"] if source is not None else None,
                    "source_url": source["url"] if source is not None else None,
                    "source_filename": source["filename"] if source is not None else None,
                    "source_published_on": source["published_on"] if source is not None else None,
                    "source_retrieved_at": source["retrieved_at"] if source is not None else None,
                    "source_sha256": source["sha256"] if source is not None else None,
                    "dataset_generated_at": generated_at,
                }
            )
    return rows


def _prefecture_annual_summary_rows(
    connection: sqlite3.Connection, generated_at: str
) -> list[dict[str, Any]]:
    """One row per prefecture per completed calendar year of final data.

    A year only qualifies once its 'final' release covers all 12 months for
    every prefecture -- matching the same completeness the static reports
    require -- so this naturally excludes a year still awaiting its annual
    final revision instead of exporting a partial, misleading profile.
    """
    facts = connection.execute(
        """SELECT f.year,f.month,f.prefecture_code,p.name AS prefecture_name,
                  f.total_guests,f.foreign_guests,f.occupancy_rate,f.facilities,
                  s.url,s.filename,s.published_on,s.retrieved_at,s.sha256
             FROM monthly_prefecture_market AS f
             JOIN prefectures AS p ON p.code=f.prefecture_code
             JOIN source_files AS s ON s.id=f.source_file_id
            WHERE f.release_type='final'
            ORDER BY f.year,f.prefecture_code,f.month"""
    ).fetchall()

    by_year_prefecture: dict[tuple[int, int], list[sqlite3.Row]] = {}
    for row in facts:
        by_year_prefecture.setdefault((row["year"], row["prefecture_code"]), []).append(row)

    rows: list[dict[str, Any]] = []
    for (year, code), months in sorted(by_year_prefecture.items()):
        available = {row["month"] for row in months}
        if available != set(range(1, 13)):
            continue  # a year still missing months (e.g. awaiting its annual final revision)
        months = sorted(months, key=lambda row: row["month"])
        december = months[-1]
        occupancy = [float(row["occupancy_rate"]) for row in months]
        profile = seasonal_profile(occupancy)
        total = sum(row["total_guests"] for row in months)
        foreign = sum(row["foreign_guests"] for row in months)
        rows.append(
            {
                "year": year,
                "prefecture_code": f"{code:02d}",
                "prefecture_name": months[0]["prefecture_name"],
                "release_type": "final",
                "guest_nights_total": total,
                "foreign_share_pct": _foreign_share(foreign, total),
                "occupancy_rate_pct_avg": profile.average,
                "occupancy_seasonal_cv": profile.coefficient_of_variation,
                "occupancy_seasonal_range_pp": profile.range_pp,
                "occupancy_peak_month": profile.peak_month,
                "occupancy_bottom_month": profile.bottom_month,
                "facility_count": december["facilities"],
                "source_url": december["url"],
                "source_filename": december["filename"],
                "source_published_on": december["published_on"],
                "source_retrieved_at": december["retrieved_at"],
                "source_sha256": december["sha256"],
                "dataset_generated_at": generated_at,
            }
        )
    return rows


def _validate_annual_summary_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise BiExportError("prefecture_annual_summary export is empty")
    if set(rows[0]) != set(PREFECTURE_ANNUAL_SUMMARY_FIELDS):
        raise BiExportError("prefecture_annual_summary export schema does not match its contract")
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = (row["year"], row["prefecture_code"])
        if key in seen:
            raise BiExportError(f"duplicate prefecture_annual_summary export key: {key}")
        seen.add(key)
        occupancy = row["occupancy_rate_pct_avg"]
        if not 0 <= occupancy <= 200:
            raise BiExportError(
                f"invalid prefecture_annual_summary occupancy rate: {key} {occupancy}"
            )


def _validate_rows(
    rows: list[dict[str, Any]], fields: list[str], keys: list[str], dataset: str
) -> None:
    if not rows:
        raise BiExportError(f"{dataset} export is empty")
    if set(rows[0]) != set(fields):
        raise BiExportError(f"{dataset} export schema does not match its contract")
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = tuple(row[field] for field in keys)
        if key in seen:
            raise BiExportError(f"duplicate {dataset} export key: {key}")
        seen.add(key)
        occupancy = row.get("occupancy_rate_pct")
        if occupancy is not None and not 0 <= float(occupancy) <= 200:
            raise BiExportError(f"invalid {dataset} occupancy rate: {key} {occupancy}")
        total = row.get("guest_nights_total")
        japanese = row.get("guest_nights_japanese")
        foreign = row.get("guest_nights_foreign")
        if (
            total is not None
            and japanese is not None
            and foreign is not None
            and total != japanese + foreign
        ):
            raise BiExportError(f"invalid {dataset} guest composition: {key}")
        for flag, delta in (
            ("has_yoy_comparison", "occupancy_yoy_delta_pp"),
            ("has_2019_comparison", "occupancy_2019_delta_pp"),
        ):
            if row[flag] == 0 and row[delta] is not None:
                raise BiExportError(f"invalid {dataset} comparison flag: {key} {flag}")


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _replace_directory(staged: Path, destination: Path) -> None:
    backup: Path | None = None
    if destination.exists():
        backup = destination.parent / f".{destination.name}.backup-{uuid.uuid4().hex}"
        os.replace(destination, backup)
    try:
        os.replace(staged, destination)
    except Exception:
        if backup is not None and backup.exists():
            os.replace(backup, destination)
        raise
    if backup is not None:
        shutil.rmtree(backup)


def _validate_paths(database: Path, output_dir: Path) -> tuple[Path, Path]:
    database = database.resolve()
    output_dir = output_dir.resolve()
    if not database.is_file():
        raise BiExportError(f"database not found: {database}")
    if output_dir.exists() and not output_dir.is_dir():
        raise BiExportError(f"BI output path is not a directory: {output_dir}")
    if output_dir == database or output_dir in database.parents:
        raise BiExportError("BI output directory must not contain the database")
    if output_dir == Path(output_dir.anchor):
        raise BiExportError("BI output directory must not be a filesystem root")
    return database, output_dir


def export_bi_data(database: Path, output_dir: Path, base_year: int = 2019) -> dict[str, Any]:
    """Generate validated Tableau CSVs and atomically replace the previous export."""
    database, output_dir = _validate_paths(database, output_dir)
    generated_at = datetime.now(UTC).isoformat()
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        _require_tables(connection)
        prefecture_rows = _prefecture_rows(connection, base_year, generated_at)
        municipality_rows = _municipality_rows(connection, base_year, generated_at)
        annual_summary_rows = _prefecture_annual_summary_rows(connection, generated_at)
    finally:
        connection.close()

    _validate_rows(
        prefecture_rows,
        PREFECTURE_FIELDS,
        ["date", "geography_level", "prefecture_code", "release_type"],
        "prefecture",
    )
    _validate_rows(
        municipality_rows,
        MUNICIPALITY_FIELDS,
        ["date", "municipality_key"],
        "municipality",
    )
    _validate_annual_summary_rows(annual_summary_rows)
    observed_municipalities = sum(row["record_status"] == "published" for row in municipality_rows)
    annual_summary_years = sorted({row["year"] for row in annual_summary_rows})
    metadata_rows = [
        {
            "dataset_name": "prefecture_monthly",
            "row_count": len(prefecture_rows),
            "observed_row_count": len(prefecture_rows),
            "min_date": min(row["date"] for row in prefecture_rows),
            "max_date": max(row["date"] for row in prefecture_rows),
            "geography_level": "national,prefecture",
            "release_type": "final",
            "data_scope": "official national occupancy and prefecture all facilities",
            "source_name": SOURCE_NAME,
            "source_url": SOURCE_URL,
            "dataset_generated_at": generated_at,
            "notes": "National rows contain official occupancy only; they are not a sum or average of prefectures.",
        },
        {
            "dataset_name": "municipality_monthly",
            "row_count": len(municipality_rows),
            "observed_row_count": observed_municipalities,
            "min_date": min(row["date"] for row in municipality_rows),
            "max_date": max(row["date"] for row in municipality_rows),
            "geography_level": "municipality",
            "release_type": "second_preliminary",
            "data_scope": "principal municipalities, total room-size class",
            "source_name": SOURCE_NAME,
            "source_url": SOURCE_URL,
            "dataset_generated_at": generated_at,
            "notes": "not_listed rows are an explicit dense calendar and must remain null, not zero.",
        },
        {
            "dataset_name": "prefecture_annual_summary",
            "row_count": len(annual_summary_rows),
            "observed_row_count": len(annual_summary_rows),
            "min_date": f"{annual_summary_years[0]}-01-01",
            "max_date": f"{annual_summary_years[-1]}-12-31",
            "geography_level": "prefecture",
            "release_type": "final",
            "data_scope": "prefecture all facilities, completed calendar years only",
            "source_name": SOURCE_NAME,
            "source_url": SOURCE_URL,
            "dataset_generated_at": generated_at,
            "notes": (
                "One row per prefecture per completed calendar year, for cross-sectional "
                "ranking/screening. Seasonal CV/range are within that single calendar year, "
                "not a multi-year window."
            ),
        },
    ]

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hotel-bi-export-", dir=output_dir.parent) as temporary:
        staged = Path(temporary) / output_dir.name
        staged.mkdir()
        _write_csv(staged / "prefecture_monthly.csv", PREFECTURE_FIELDS, prefecture_rows)
        _write_csv(staged / "municipality_monthly.csv", MUNICIPALITY_FIELDS, municipality_rows)
        _write_csv(
            staged / "prefecture_annual_summary.csv",
            PREFECTURE_ANNUAL_SUMMARY_FIELDS,
            annual_summary_rows,
        )
        _write_csv(staged / "metadata.csv", METADATA_FIELDS, metadata_rows)
        _replace_directory(staged, output_dir)

    return {
        "output_dir": str(output_dir),
        "base_year": base_year,
        "generated_at": generated_at,
        "datasets": {
            "prefecture_monthly": {"rows": len(prefecture_rows)},
            "municipality_monthly": {
                "rows": len(municipality_rows),
                "observed_rows": observed_municipalities,
            },
            "prefecture_annual_summary": {"rows": len(annual_summary_rows)},
            "metadata": {"rows": len(metadata_rows)},
        },
    }
