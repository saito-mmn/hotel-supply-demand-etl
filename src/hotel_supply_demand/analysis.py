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
    release_type: str
    demand_below_base_pct: float
    demand_yoy_decline_pct: float
    demand_yoy_improvement_pct: float
    occupancy_decline_pp: float
    occupancy_improvement_pp: float
    facility_growth_pct: float
    absorption_gap_pct: float
    foreign_share_shift_pp: float
    foreign_share_concentration_pct: float
    monthly_cv_high: float


def load_analysis_config(path: Path, *, target_year: int | None = None, base_year: int | None = None) -> AnalysisConfig:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    settings = raw["analysis"]
    thresholds = raw["thresholds"]
    return AnalysisConfig(
        base_year=base_year or int(settings["base_year"]),
        target_year=target_year or int(settings["target_year"]),
        release_type=str(settings["release_type"]),
        **{name: float(value) for name, value in thresholds.items()},
    )


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1) * 100


def _ratio(numerator: float | None, denominator: float | None, multiplier: float = 100) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * multiplier


def _annual_rows(connection: sqlite3.Connection, years: set[int], release_type: str) -> dict[tuple[int, int], sqlite3.Row]:
    placeholders = ",".join("?" for _ in years)
    rows = connection.execute(
        f"SELECT * FROM annual_market WHERE year IN ({placeholders}) AND months = 12 AND release_type = ?",
        [*sorted(years), release_type],
    ).fetchall()
    return {(row["year"], row["prefecture_code"]): row for row in rows}


def _monthly_demand(connection: sqlite3.Connection, year: int, code: int) -> list[float]:
    return [
        float(row[0])
        for row in connection.execute(
            "SELECT total_guests FROM monthly_market WHERE year=? AND prefecture_code=? ORDER BY month",
            (year, code),
        )
        if row[0] is not None
    ]


def _classify(metrics: dict, config: AnalysisConfig) -> str:
    if metrics["data_quality_note"]:
        return "データ不足・比較不能"
    if metrics["demand_yoy_pct"] is None or metrics["occupancy_yoy_pp"] is None or metrics["facility_yoy_pct"] is None:
        return "データ不足・比較不能"
    if metrics["demand_yoy_pct"] <= config.demand_yoy_decline_pct or metrics["occupancy_yoy_pp"] <= config.occupancy_decline_pp:
        return "需要悪化兆候"
    if metrics["facility_yoy_pct"] >= config.facility_growth_pct and metrics["absorption_gap_pct"] <= config.absorption_gap_pct:
        return "供給増加に対する需要吸収の要確認"
    if metrics["demand_yoy_pct"] >= config.demand_yoy_improvement_pct and metrics["occupancy_yoy_pp"] >= config.occupancy_improvement_pp:
        return "需要・稼働率改善"
    if metrics["monthly_cv"] >= config.monthly_cv_high or metrics["foreign_share_pct"] >= config.foreign_share_concentration_pct:
        return "高変動・需要構成偏重"
    if metrics["demand_vs_base_pct"] < config.demand_below_base_pct:
        return "改善継続性の要確認"
    return "おおむね横ばい"


def _watch_reasons(metrics: dict, config: AnalysisConfig) -> list[str]:
    reasons = []
    if metrics["demand_vs_base_pct"] is not None and metrics["demand_vs_base_pct"] < config.demand_below_base_pct:
        reasons.append("2019年需要水準未達")
    if metrics["demand_yoy_pct"] is not None and metrics["demand_yoy_pct"] <= config.demand_yoy_decline_pct:
        reasons.append("需要の前年比低下")
    if metrics["occupancy_yoy_pp"] is not None and metrics["occupancy_yoy_pp"] <= config.occupancy_decline_pp:
        reasons.append("稼働率の前年比低下")
    if metrics["facility_yoy_pct"] is not None and metrics["absorption_gap_pct"] is not None and metrics["facility_yoy_pct"] >= config.facility_growth_pct and metrics["absorption_gap_pct"] <= config.absorption_gap_pct:
        reasons.append("供給増加に対する需要吸収の要確認")
    if metrics["foreign_share_yoy_pp"] is not None and abs(metrics["foreign_share_yoy_pp"]) >= config.foreign_share_shift_pp:
        reasons.append("外国人需要構成の大幅変化")
    if metrics["monthly_cv"] is not None and metrics["monthly_cv"] >= config.monthly_cv_high:
        reasons.append("月次需要の高変動")
    if metrics["foreign_share_pct"] is not None and metrics["foreign_share_pct"] >= config.foreign_share_concentration_pct:
        reasons.append("外国人需要への高集中")
    return reasons


def analyze_database(database: Path, config: AnalysisConfig) -> list[dict]:
    if config.target_year <= config.base_year:
        raise AnalysisError("target year must be later than base year")
    previous_year = config.target_year - 1
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        annual = _annual_rows(connection, {config.base_year, previous_year, config.target_year}, config.release_type)
        target_codes = sorted(code for year, code in annual if year == config.target_year)
        if len(target_codes) != 47:
            raise AnalysisError(f"target year must contain 47 complete prefectures: {len(target_codes)}")
        output = []
        for code in target_codes:
            current = annual.get((config.target_year, code))
            previous = annual.get((previous_year, code))
            base = annual.get((config.base_year, code))
            if not current or not previous or not base:
                raise AnalysisError(f"comparison year is incomplete for prefecture code {code}")
            demand = _monthly_demand(connection, config.target_year, code)
            monthly_cv = statistics.pstdev(demand) / statistics.mean(demand) if len(demand) == 12 and statistics.mean(demand) else None
            peak_month_share = max(demand) / sum(demand) * 100 if demand and sum(demand) else None
            current_foreign_share = _ratio(current["foreign_guests"], current["total_guests"])
            previous_foreign_share = _ratio(previous["foreign_guests"], previous["total_guests"])
            demand_yoy = _pct_change(current["total_guests"], previous["total_guests"])
            facility_yoy = _pct_change(current["average_facilities"], previous["average_facilities"])
            metrics = {
                "prefecture_code": code,
                "prefecture_name": current["prefecture_name"],
                "target_year": config.target_year,
                "base_year": config.base_year,
                "release_type": current["release_type"],
                "total_guests": current["total_guests"],
                "average_occupancy_rate": current["average_occupancy_rate"],
                "average_facilities": current["average_facilities"],
                "foreign_share_pct": current_foreign_share,
                "demand_vs_base_pct": _ratio(current["total_guests"], base["total_guests"]),
                "demand_yoy_pct": demand_yoy,
                "occupancy_yoy_pp": current["average_occupancy_rate"] - previous["average_occupancy_rate"],
                "facility_yoy_pct": facility_yoy,
                "absorption_gap_pct": demand_yoy - facility_yoy,
                "foreign_share_yoy_pp": current_foreign_share - previous_foreign_share,
                "monthly_cv": monthly_cv,
                "peak_month_share_pct": peak_month_share,
                "monthly_total_guests": demand,
                "data_quality_note": "",
            }
            reasons = _watch_reasons(metrics, config)
            metrics["market_state"] = _classify(metrics, config)
            metrics["watch_reasons"] = reasons
            metrics["is_watch"] = bool(reasons)
            metrics["observed_fact"] = _observed_fact(metrics)
            metrics["interpretation"] = "地域市場の変化を示す一次スクリーニング結果であり、個別ホテルの収益性や担保価値を直接示さない。"
            metrics["next_action"] = "対象ホテルのADR・RevPAR・GOP、競合施設の開業・閉館、商圏別需要を追加確認する。"
            output.append(metrics)
        return output
    finally:
        connection.close()


def _observed_fact(metrics: dict) -> str:
    return (
        f"延べ宿泊者数は前年比{metrics['demand_yoy_pct']:+.1f}%、"
        f"{metrics['base_year']}年比{metrics['demand_vs_base_pct']:.1f}%。"
        f"平均稼働率は前年比{metrics['occupancy_yoy_pp']:+.1f}pt、"
        f"平均施設数は前年比{metrics['facility_yoy_pct']:+.1f}%。"
    )


def config_as_dict(config: AnalysisConfig) -> dict:
    return asdict(config)
