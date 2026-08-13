import tempfile
import unittest
from pathlib import Path

from hotel_supply_demand.analysis import analyze_database, load_analysis_config
from hotel_supply_demand.database import build_database
from hotel_supply_demand.models import MonthlyRecord
from hotel_supply_demand.report import generate_reports


class AnalysisTest(unittest.TestCase):
    def test_metrics_watchlist_and_reports(self):
        records = []
        inputs = {
            2019: (1000, 60.0, 100),
            2024: (1100, 60.0, 100),
            2025: (990, 50.0, 110),
        }
        for year, (guests, occupancy, facilities) in inputs.items():
            for month in range(1, 13):
                for code in range(1, 48):
                    records.append(
                        MonthlyRecord(
                            year=year,
                            month=month,
                            prefecture_code=code,
                            prefecture_name=f"地域{code}県",
                            total_guests=guests,
                            japanese_guests=guests - 100,
                            foreign_guests=100,
                            occupancy_rate=occupancy,
                            facilities=facilities,
                        )
                    )
        manifest = [
            {
                "year": year,
                "release_type": "final",
                "url": f"https://www.mlit.go.jp/{year}.xlsx",
                "filename": f"{year}.xlsx",
                "retrieved_at": "2026-01-01T00:00:00+00:00",
                "sha256": str(year) * 16,
                "size_bytes": 1,
            }
            for year in inputs
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "market.sqlite3"
            build_database(database, records, manifest)
            config = load_analysis_config(Path("analysis.toml"))
            rows = analyze_database(database, config)
            self.assertEqual(len(rows), 47)
            self.assertAlmostEqual(rows[0]["demand_vs_base_pct"], 99.0)
            self.assertAlmostEqual(rows[0]["demand_yoy_pct"], -10.0)
            self.assertAlmostEqual(rows[0]["occupancy_yoy_pp"], -10.0)
            self.assertEqual(rows[0]["market_state"], "需要悪化兆候")
            self.assertTrue(rows[0]["is_watch"])

            reports = root / "reports"
            result = generate_reports(database, reports, config)
            self.assertEqual(result["market_sheets"], 47)
            self.assertEqual(result["watch_count"], 47)
            self.assertTrue((reports / "index.html").is_file())
            self.assertTrue((reports / "market-sheets" / "01.html").is_file())
            self.assertIn("需要悪化兆候", (reports / "index.html").read_text(encoding="utf-8"))
