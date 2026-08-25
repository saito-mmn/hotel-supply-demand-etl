"""Compute transparent market-monitoring metrics from the Phase 1 database."""

from __future__ import annotations

import sqlite3
import statistics
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path


class AnalysisError(ValueError):
    pass


@dataclass(frozen=True)
class AnalysisConfig:
    base_year: int
    target_year: int
    target_month: int
    release_type: str
    ltm_months: int
    recent_months: int


def load_analysis_config(
    path: Path, *, target_year: int | None = None, base_year: int | None = None
) -> AnalysisConfig:
    with path.open("rb") as handle:
        settings = tomllib.load(handle)["analysis"]
    config = AnalysisConfig(
        base_year=base_year or int(settings["base_year"]),
        target_year=target_year or int(settings["target_year"]),
        target_month=int(settings.get("target_month", 12)),
        release_type=str(settings["release_type"]),
        ltm_months=int(settings.get("ltm_months", 12)),
        recent_months=int(settings.get("recent_months", 3)),
    )
    if not 1 <= config.target_month <= 12:
        raise AnalysisError("target_month must be between 1 and 12")
    if config.ltm_months != 12:
        raise AnalysisError("Phase 2 supports a 12-month LTM window")
    if not 1 <= config.recent_months <= config.ltm_months:
        raise AnalysisError("recent_months must be between 1 and ltm_months")
    return config


def config_as_dict(config: AnalysisConfig) -> dict:
    return asdict(config)


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1) * 100


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * 100


def _periods(end_year: int, end_month: int, count: int) -> list[tuple[int, int]]:
    end_index = end_year * 12 + end_month - 1
    periods = []
    for index in range(end_index - count + 1, end_index + 1):
        year, zero_based_month = divmod(index, 12)
        periods.append((year, zero_based_month + 1))
    return periods


def _load_monthly(connection: sqlite3.Connection, release_type: str) -> dict[tuple[int, int, int], sqlite3.Row]:
    rows = connection.execute(
        "SELECT * FROM latest_prefecture_market WHERE release_type = ? ORDER BY year, month, prefecture_code",
        (release_type,),
    ).fetchall()
    return {(row["year"], row["month"], row["prefecture_code"]): row for row in rows}


def _window(
    monthly: dict[tuple[int, int, int], sqlite3.Row],
    periods: list[tuple[int, int]],
    code: int,
) -> list[sqlite3.Row]:
    rows = [monthly.get((year, month, code)) for year, month in periods]
    if any(row is None for row in rows):
        raise AnalysisError(f"incomplete comparison window for prefecture code {code}: {periods}")
    return [row for row in rows if row is not None]


def _sum(rows: list[sqlite3.Row], field: str) -> float | None:
    values = [row[field] for row in rows]
    return float(sum(values)) if values and all(value is not None for value in values) else None


def _mean(rows: list[sqlite3.Row], field: str) -> float | None:
    values = [row[field] for row in rows]
    return float(statistics.mean(values)) if values and all(value is not None for value in values) else None


def analyze_database(database: Path, config: AnalysisConfig) -> list[dict]:
    if config.target_year <= config.base_year:
        raise AnalysisError("target year must be later than base year")
    current_periods = _periods(config.target_year, config.target_month, config.ltm_months)
    previous_periods = _periods(config.target_year - 1, config.target_month, config.ltm_months)
    base_periods = _periods(config.base_year, config.target_month, config.ltm_months)
    recent_periods = current_periods[-config.recent_months :]
    recent_previous_periods = previous_periods[-config.recent_months :]

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        monthly = _load_monthly(connection, config.release_type)
        target_codes = sorted({code for year, month, code in monthly if (year, month) == current_periods[-1]})
        if len(target_codes) != 47:
            raise AnalysisError(f"target period must contain 47 prefectures: {len(target_codes)}")
        output = []
        for code in target_codes:
            current = _window(monthly, current_periods, code)
            previous = _window(monthly, previous_periods, code)
            base = _window(monthly, base_periods, code)
            recent = _window(monthly, recent_periods, code)
            recent_previous = _window(monthly, recent_previous_periods, code)
            total = _sum(current, "total_guests")
            previous_total = _sum(previous, "total_guests")
            base_total = _sum(base, "total_guests")
            foreign = _sum(current, "foreign_guests")
            previous_foreign = _sum(previous, "foreign_guests")
            base_foreign = _sum(base, "foreign_guests")
            japanese = _sum(current, "japanese_guests")
            previous_japanese = _sum(previous, "japanese_guests")
            foreign_share = _ratio(foreign, total)
            previous_foreign_share = _ratio(previous_foreign, previous_total)
            monthly_demand = [float(row["total_guests"]) for row in current]
            monthly_japanese = [
                float(row["japanese_guests"]) if row["japanese_guests"] is not None else None
                for row in current
            ]
            monthly_foreign = [
                float(row["foreign_guests"]) if row["foreign_guests"] is not None else None
                for row in current
            ]
            monthly_occupancy = [float(row["occupancy_rate"]) for row in current]
            metrics = {
                "prefecture_code": code,
                "prefecture_name": current[-1]["prefecture_name"],
                "target_year": config.target_year,
                "target_month": config.target_month,
                "base_year": config.base_year,
                "release_type": config.release_type,
                "total_guests": total,
                "average_occupancy_rate": _mean(current, "occupancy_rate"),
                "average_facilities": _mean(current, "facilities"),
                "facilities": float(current[-1]["facilities"]),
                "foreign_share_pct": foreign_share,
                "demand_vs_base_pct": _ratio(total, base_total),
                "occupancy_vs_base_pp": _mean(current, "occupancy_rate")
                - _mean(base, "occupancy_rate"),
                "foreign_vs_base_pct": _ratio(foreign, base_foreign),
                "demand_ltm_yoy_pct": _pct_change(total, previous_total),
                "foreign_ltm_yoy_pct": _pct_change(foreign, previous_foreign),
                "japanese_ltm_yoy_pct": _pct_change(japanese, previous_japanese),
                "occupancy_ltm_yoy_pp": _mean(current, "occupancy_rate") - _mean(previous, "occupancy_rate"),
                "facility_ltm_yoy_pct": _pct_change(_mean(current, "facilities"), _mean(previous, "facilities")),
                "facility_yoy_pct": _pct_change(current[-1]["facilities"], previous[-1]["facilities"]),
                "foreign_share_yoy_pp": foreign_share - previous_foreign_share,
                "recent_demand_yoy_pct": _pct_change(_sum(recent, "total_guests"), _sum(recent_previous, "total_guests")),
                "recent_occupancy_yoy_pp": _mean(recent, "occupancy_rate") - _mean(recent_previous, "occupancy_rate"),
                "monthly_cv": statistics.pstdev(monthly_demand) / statistics.mean(monthly_demand),
                "peak_month_share_pct": max(monthly_demand) / sum(monthly_demand) * 100,
                "seasonal_occupancy_cv": statistics.pstdev(monthly_occupancy)
                / statistics.mean(monthly_occupancy),
                "occupancy_seasonal_range_pp": max(monthly_occupancy)
                - min(monthly_occupancy),
                "top3_demand_share_pct": sum(sorted(monthly_demand, reverse=True)[:3])
                / sum(monthly_demand)
                * 100,
                "monthly_total_guests": monthly_demand,
                "monthly_japanese_guests": monthly_japanese,
                "monthly_foreign_guests": monthly_foreign,
                "monthly_occupancy_rate": monthly_occupancy,
                "monthly_labels": [f"{year}-{month:02d}" for year, month in current_periods],
            }
            output.append(metrics)
        return output
    finally:
        connection.close()
