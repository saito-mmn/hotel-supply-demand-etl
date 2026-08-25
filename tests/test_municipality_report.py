import tempfile
import unittest
from pathlib import Path

from municipality_fixtures import make_municipality_report_database

from hotel_supply_demand.municipality.report import (
    _annual_demand_chart,
    _annual_facilities_chart,
    _occupancy_axis_max,
    _seasonality_chart,
    generate_municipality_reports,
)


class MunicipalityReportTest(unittest.TestCase):
    def test_index_exposes_core_exploration_features(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            result = generate_municipality_reports(
                make_municipality_report_database(root), reports, base_year=2020
            )
            self.assertEqual(result["market_sheets"], 2)
            html = (reports / "index.html").read_text(encoding="utf-8")
            for text in (
                "市区町村別ホテルマーケットレポート",
                "← 都道府県別ホテルマーケットレポート",
                "札幌市",
                "自治体属性",
                "需給",
                "インバウンド",
                "延べ宿泊者数",
                "調査対象施設数",
                "外国人比率",
                'id="search"',
                'class="sortable',
                'id="municipality-export"',
                "municipality-hotel-market.csv",
            ):
                self.assertIn(text, html)
            self.assertNotIn("要注意", html)

    def test_market_sheet_shows_domain_specific_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            result = generate_municipality_reports(
                make_municipality_report_database(root), reports, base_year=2020
            )
            html = (reports / "market-sheets" / "1.html").read_text(encoding="utf-8")
            self.assertEqual(result["base_year"], 2020)
            for text in (
                "札幌市 Market Sheet",
                "2026年5月単月（最新掲載月）",
                "1. 客室稼働率",
                "比較基準の2020年（破線）",
                "2. 延べ宿泊者数（需要）",
                "3. 宿泊施設数（供給）",
                "4. 利用上の注意",
                "年間比較に必要な12か月分",
                "年次比較に必要な12月時点",
            ):
                self.assertIn(text, html)
            self.assertNotIn("客室規模別内訳", html)

    def test_annual_charts_require_comparable_observations(self):
        history = [
            {
                "year": year,
                "month": month,
                "total_guests": 100 + month,
                "japanese_guests": 80,
                "foreign_guests": 20 + month,
                "population_facilities": 10 + year - 2023,
            }
            for year in (2023, 2024, 2025)
            for month in range(1, 13)
        ]
        history.append(
            {
                "year": 2019,
                "month": 12,
                "total_guests": 90,
                "japanese_guests": 80,
                "foreign_guests": 10,
                "population_facilities": 8,
            }
        )
        demand = _annual_demand_chart(history, [2023, 2024, 2025])
        facilities = _annual_facilities_chart(history, [2019, 2023, 2024, 2025])
        self.assertIn('fill="#0369a1">100%</text>', demand)
        self.assertIn("2019年12月 8施設", facilities)
        incomplete = [row for row in history if not (row["year"] == 2025 and row["month"] == 1)]
        self.assertIn(
            "年間比較に必要な12か月分",
            _annual_demand_chart(incomplete, [2023, 2024, 2025]),
        )

    def test_seasonality_chart_uses_calendar_months_and_keeps_gaps(self):
        history = [
            {"year": 2025, "month": month, "occupancy_rate": 50.0 + month} for month in (1, 2, 4, 5)
        ]
        chart = _seasonality_chart(history, "occupancy_rate", "%", [2025])
        self.assertIn(">1月<", chart)
        self.assertIn(">12月<", chart)
        self.assertEqual(chart.count("<polyline"), 2)

    def test_percentage_domain_and_reference_year(self):
        history = [
            {"year": year, "month": month, "occupancy_rate": 50.0 + month}
            for year in (2019, 2023, 2024, 2025)
            for month in range(1, 13)
        ]
        chart = _seasonality_chart(
            history,
            "occupancy_rate",
            "%",
            [2019, 2023, 2024, 2025],
            reference_year=2019,
            y_domain=(0.0, 100.0),
        )
        for tick in ("0.0%", "25.0%", "50.0%", "75.0%", "100.0%"):
            self.assertIn(f">{tick}</text>", chart)
        self.assertIn('stroke="#64748b" stroke-width="2" stroke-dasharray="7 5"', chart)

    def test_occupancy_axis_is_common_and_extends_above_100(self):
        histories = {1: [{"occupancy_rate": 95.8}], 2: [{"occupancy_rate": None}]}
        self.assertEqual(_occupancy_axis_max(histories), 100.0)
        histories[2].append({"occupancy_rate": 104.3})
        self.assertEqual(_occupancy_axis_max(histories), 110.0)
