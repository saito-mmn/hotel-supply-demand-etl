import tempfile
import unittest
from pathlib import Path

from hotel_supply_demand.analysis import analyze_database, load_analysis_config
from hotel_supply_demand.database import build_database
from hotel_supply_demand.models import MonthlyRecord, NationalOccupancyRecord
from hotel_supply_demand.report import generate_reports


class AnalysisTest(unittest.TestCase):
    def test_metrics_watchlist_and_reports(self):
        records = []
        inputs = {
            2019: (1000, 60.0, 100),
            2023: (1050, 58.0, 100),
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
                "published_on": f"{year + 1}-07-01",
                "retrieved_at": "2026-01-01T00:00:00+00:00",
                "sha256": str(year) * 16,
                "size_bytes": 1,
            }
            for year in inputs
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "market.sqlite3"
            national = [
                NationalOccupancyRecord(year=year, month=month, occupancy_rate=occupancy)
                for year, (_, occupancy, _) in inputs.items()
                for month in range(1, 13)
            ]
            build_database(database, records, manifest, national)
            config = load_analysis_config(Path("analysis.toml"))
            rows = analyze_database(database, config)
            self.assertEqual(len(rows), 47)
            self.assertAlmostEqual(rows[0]["demand_vs_base_pct"], 99.0)
            self.assertAlmostEqual(rows[0]["occupancy_vs_base_pp"], -10.0)
            self.assertAlmostEqual(rows[0]["foreign_vs_base_pct"], 100.0)
            self.assertAlmostEqual(rows[0]["demand_ltm_yoy_pct"], -10.0)
            self.assertAlmostEqual(rows[0]["japanese_ltm_yoy_pct"], -11.0)
            self.assertAlmostEqual(rows[0]["occupancy_ltm_yoy_pp"], -10.0)
            self.assertAlmostEqual(rows[0]["recent_demand_yoy_pct"], -10.0)
            self.assertTrue(rows[0]["recent_all_demand_yoy_negative"])
            self.assertEqual(rows[0]["demand_ltm_yoy_pct_relative"], "全国中位50%")
            self.assertEqual(rows[0]["seasonal_occupancy_cv"], 0.0)
            self.assertEqual(rows[0]["occupancy_seasonal_range_pp"], 0.0)
            self.assertAlmostEqual(rows[0]["top3_demand_share_pct"], 25.0)
            self.assertEqual(len(rows[0]["monthly_japanese_guests"]), 12)
            self.assertEqual(len(rows[0]["monthly_foreign_guests"]), 12)
            self.assertEqual(rows[0]["market_state"], "需要減速・中期縮小")
            self.assertEqual(rows[0]["recovery_signals"], ["2019年需要水準未達"])
            self.assertEqual(rows[0]["supply_demand_pattern"], "需要減少・施設数増加")
            self.assertTrue(rows[0]["is_watch"])

            reports = root / "reports"
            result = generate_reports(database, reports, config)
            self.assertEqual(result["market_sheets"], 47)
            self.assertTrue((reports / "index.html").is_file())
            self.assertTrue((reports / "market-sheets" / "01.html").is_file())
            self.assertFalse((reports / "watchlist.csv").exists())
            index_html = (reports / "index.html").read_text(encoding="utf-8")
            self.assertIn("データ公表日 2026/07/01", index_html)
            for heading in ("全国のホテル市況", "インバウンド", "季節変動ランキング", "都道府県一覧"):
                self.assertIn(heading, index_html)
            self.assertNotIn("<h2>2. 市場回復の広がり</h2>", index_html)
            self.assertIn("稼働率前年比：上昇", index_html)
            self.assertIn("Seasonal CV（変動係数）", index_html)
            self.assertIn("ピーク月 / ボトム月", index_html)
            self.assertIn("宿泊施設数（前年比）", index_html)
            self.assertIn('id="prefecture-search"', index_html)
            self.assertIn('id="prefecture-table"', index_html)
            self.assertNotIn('class="bar-cell', index_html)
            self.assertIn('class="numeric">10.1%</span>', index_html)
            self.assertIn('class="numeric">+0.0%</span>', index_html)
            self.assertNotIn('class="numeric">+10.1%</span>', index_html)
            self.assertIn("標準偏差（σ） ÷ 年間平均客室稼働率（μ）", index_html)
            self.assertIn("47都道府県の単純平均ではありません", index_html)
            self.assertIn("外国人宿泊者数成長率 TOP10", index_html)
            self.assertIn("上昇", index_html)
            self.assertNotIn("需要減速・中期縮小", index_html)
            detail_html = (reports / "market-sheets" / "01.html").read_text(encoding="utf-8")
            for heading in ("延べ宿泊者数", "客室稼働率"):
                self.assertIn(heading, detail_html)
            self.assertNotIn("<h2>宿泊施設数</h2>", detail_html)
            self.assertIn("LTM総延べ宿泊者数", detail_html)
            self.assertIn("宿泊施設数（2025年12月）", detail_html)
            self.assertIn("直近3年の月次総需要トレンドと、年次での需要構造（日本人・外国人比率）の変化", detail_html)
            self.assertIn("総延べ宿泊者数・月次推移（直近3年）", detail_html)
            self.assertIn("年次需要構造と外国人比率（2023–2025年）", detail_html)
            self.assertIn('class="demand-charts"', detail_html)
            self.assertNotIn(">月</text>", detail_html)
            self.assertNotIn(">客室稼働率</text>", detail_html)
            self.assertIn("11,880人泊", detail_html)
