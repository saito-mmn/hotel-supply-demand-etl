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
        "SELECT * FROM monthly_market WHERE release_type = ? ORDER BY year, month, prefecture_code",
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


def _monthly_yoy(
    current: list[sqlite3.Row], previous: list[sqlite3.Row], field: str, *, difference: bool = False
) -> list[float] | None:
    values = []
    for current_row, previous_row in zip(current, previous, strict=True):
        current_value = current_row[field]
        previous_value = previous_row[field]
        if current_value is None or previous_value is None:
            return None
        if difference:
            values.append(float(current_value - previous_value))
        else:
            change = _pct_change(current_value, previous_value)
            if change is None:
                return None
            values.append(change)
    return values


def _direction(value: float | None) -> str:
    if value is None:
        return "—"
    return "↑" if value > 0 else "↓" if value < 0 else "→"


def _percentile_ranks(rows: list[dict], field: str) -> None:
    values = sorted(row[field] for row in rows if row[field] is not None)
    for row in rows:
        value = row[field]
        if value is None:
            row[f"{field}_percentile"] = None
            row[f"{field}_relative"] = "比較不能"
            continue
        less = sum(candidate < value for candidate in values)
        equal = sum(candidate == value for candidate in values)
        percentile = (less + equal / 2) / len(values) * 100
        row[f"{field}_percentile"] = percentile
        row[f"{field}_relative"] = (
            "全国上位25%" if percentile >= 75 else "全国下位25%" if percentile <= 25 else "全国中位50%"
        )


def _signals(metrics: dict) -> list[str]:
    signals = []
    if metrics["recent_all_demand_yoy_negative"]:
        signals.append("需要減速")
    if metrics["demand_ltm_yoy_pct"] < 0:
        signals.append("中期縮小")
    if metrics["recent_all_occupancy_yoy_negative"]:
        signals.append("稼働悪化")
    if metrics["facility_ltm_yoy_pct"] > 0 and metrics["occupancy_ltm_yoy_pp"] < 0:
        signals.append("供給増加警戒")
    if metrics["demand_ltm_yoy_pct"] > 0 and metrics["occupancy_ltm_yoy_pp"] > 0 and metrics["facility_ltm_yoy_pct"] <= 0:
        signals.append("需要先行型成長")
    if metrics["demand_ltm_yoy_pct"] > 0 and metrics["facility_ltm_yoy_pct"] > 0 and metrics["occupancy_ltm_yoy_pp"] >= 0:
        signals.append("供給追随型成長")
    if metrics["foreign_ltm_yoy_pct"] > metrics["demand_ltm_yoy_pct"] and metrics["foreign_share_yoy_pp"] > 0:
        signals.append("インバウンド主導")
    if metrics["demand_vs_base_pct"] > 100:
        signals.append("コロナ前水準超過")
    return signals


def _classify(signals: list[str]) -> str:
    if "需要減速" in signals and "中期縮小" in signals:
        return "需要減速・中期縮小"
    if "供給増加警戒" in signals:
        return "供給増加警戒"
    if "需要減速" in signals:
        return "足元需要減速"
    if "中期縮小" in signals:
        return "中期縮小"
    if "稼働悪化" in signals:
        return "足元稼働悪化"
    if "インバウンド主導" in signals and ("需要先行型成長" in signals or "供給追随型成長" in signals):
        return "インバウンド主導・需要拡大型"
    for state in ("需要先行型成長", "供給追随型成長"):
        if state in signals:
            return state
    if "コロナ前水準超過" in signals:
        return "コロナ前水準超過"
    return "方向感混在・横ばい"


def _observed_fact(metrics: dict) -> str:
    return (
        f"LTM延べ宿泊者数は前年比{metrics['demand_ltm_yoy_pct']:+.1f}%、"
        f"{metrics['base_year']}年同月終了LTM比{metrics['demand_vs_base_pct']:.1f}%。"
        f"直近{metrics['recent_months']}か月需要は前年比{metrics['recent_demand_yoy_pct']:+.1f}%、"
        f"LTM平均稼働率は前年差{metrics['occupancy_ltm_yoy_pp']:+.1f}pt。"
    )


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
            foreign_share = _ratio(foreign, total)
            previous_foreign_share = _ratio(previous_foreign, previous_total)
            recent_demand_yoy = _monthly_yoy(recent, recent_previous, "total_guests")
            recent_occupancy_yoy = _monthly_yoy(
                recent, recent_previous, "occupancy_rate", difference=True
            )
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
                "recent_months": config.recent_months,
                "release_type": config.release_type,
                "total_guests": total,
                "average_occupancy_rate": _mean(current, "occupancy_rate"),
                "average_facilities": _mean(current, "facilities"),
                "foreign_share_pct": foreign_share,
                "demand_vs_base_pct": _ratio(total, base_total),
                "demand_ltm_yoy_pct": _pct_change(total, previous_total),
                "foreign_ltm_yoy_pct": _pct_change(foreign, previous_foreign),
                "occupancy_ltm_yoy_pp": _mean(current, "occupancy_rate") - _mean(previous, "occupancy_rate"),
                "facility_ltm_yoy_pct": _pct_change(_mean(current, "facilities"), _mean(previous, "facilities")),
                "foreign_share_yoy_pp": foreign_share - previous_foreign_share,
                "recent_demand_yoy_pct": _pct_change(_sum(recent, "total_guests"), _sum(recent_previous, "total_guests")),
                "recent_occupancy_yoy_pp": _mean(recent, "occupancy_rate") - _mean(recent_previous, "occupancy_rate"),
                "recent_all_demand_yoy_negative": bool(recent_demand_yoy) and all(value < 0 for value in recent_demand_yoy),
                "recent_all_occupancy_yoy_negative": bool(recent_occupancy_yoy) and all(value < 0 for value in recent_occupancy_yoy),
                "monthly_cv": statistics.pstdev(monthly_demand) / statistics.mean(monthly_demand),
                "peak_month_share_pct": max(monthly_demand) / sum(monthly_demand) * 100,
                "seasonal_occupancy_cv": statistics.pstdev(monthly_occupancy)
                / statistics.mean(monthly_occupancy),
                "top3_demand_share_pct": sum(sorted(monthly_demand, reverse=True)[:3])
                / sum(monthly_demand)
                * 100,
                "monthly_total_guests": monthly_demand,
                "monthly_japanese_guests": monthly_japanese,
                "monthly_foreign_guests": monthly_foreign,
                "monthly_labels": [f"{year}-{month:02d}" for year, month in current_periods],
                "data_quality_note": "",
            }
            metrics["recovery_direction"] = _direction(metrics["demand_vs_base_pct"] - 100)
            metrics["demand_mix_direction"] = _direction(metrics["foreign_share_yoy_pp"])
            metrics["momentum_direction"] = _direction(metrics["demand_ltm_yoy_pct"])
            metrics["supply_demand_direction"] = _direction(metrics["occupancy_ltm_yoy_pp"])
            signals = _signals(metrics)
            metrics["signals"] = signals
            metrics["watch_reasons"] = [
                signal for signal in signals if signal in {"需要減速", "中期縮小", "稼働悪化", "供給増加警戒"}
            ]
            metrics["is_watch"] = bool(metrics["watch_reasons"])
            metrics["market_state"] = _classify(signals)
            metrics["observed_fact"] = _observed_fact(metrics)
            metrics["interpretation"] = "都道府県単位の一次スクリーニングであり、個別ホテルの収益性や担保価値を直接示さない。"
            metrics["next_action"] = "対象ホテルの客室数・ADR・RevPAR・GOP、競合施設の開閉業、商圏別需要を追加確認する。"
            output.append(metrics)
        for field in (
            "demand_ltm_yoy_pct",
            "foreign_share_pct",
            "facility_ltm_yoy_pct",
            "recent_demand_yoy_pct",
            "seasonal_occupancy_cv",
            "top3_demand_share_pct",
        ):
            _percentile_ranks(output, field)
        for metrics in output:
            characteristics = []
            if metrics["seasonal_occupancy_cv_relative"] == "全国上位25%":
                characteristics.append("高季節性")
            elif metrics["seasonal_occupancy_cv_relative"] == "全国下位25%":
                characteristics.append("低季節性")
            if metrics["top3_demand_share_pct_relative"] == "全国上位25%":
                characteristics.append("ピーク集中型")
            metrics["market_characteristics"] = characteristics
        return output
    finally:
        connection.close()
