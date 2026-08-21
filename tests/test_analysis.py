import tempfile
import unittest
from pathlib import Path

from hotel_supply_demand.prefecture.analysis import analyze_database, load_analysis_config
from hotel_supply_demand.prefecture.database import build_database
from hotel_supply_demand.prefecture.models import MonthlyRecord, NationalOccupancyRecord
from hotel_supply_demand.prefecture.report import generate_reports


class AnalysisTest(unittest.TestCase):
    def test_metrics_and_reports(self):
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
            config = load_analysis_config(Path("config/analysis.toml"))
            rows = analyze_database(database, config)
            self.assertEqual(len(rows), 47)
            self.assertAlmostEqual(rows[0]["demand_vs_base_pct"], 99.0)
            self.assertAlmostEqual(rows[0]["occupancy_vs_base_pp"], -10.0)
            self.assertAlmostEqual(rows[0]["foreign_vs_base_pct"], 100.0)
            self.assertAlmostEqual(rows[0]["demand_ltm_yoy_pct"], -10.0)
            self.assertAlmostEqual(rows[0]["japanese_ltm_yoy_pct"], -11.0)
            self.assertAlmostEqual(rows[0]["occupancy_ltm_yoy_pp"], -10.0)
            self.assertAlmostEqual(rows[0]["recent_demand_yoy_pct"], -10.0)
            self.assertEqual(rows[0]["seasonal_occupancy_cv"], 0.0)
            self.assertEqual(rows[0]["occupancy_seasonal_range_pp"], 0.0)
            self.assertAlmostEqual(rows[0]["top3_demand_share_pct"], 25.0)
            self.assertEqual(len(rows[0]["monthly_japanese_guests"]), 12)
            self.assertEqual(len(rows[0]["monthly_foreign_guests"]), 12)
            reports = root / "reports"
            result = generate_reports(database, reports, config)
            self.assertEqual(result["market_sheets"], 47)
            self.assertTrue((reports / "index.html").is_file())
            self.assertTrue((reports / "market-sheets" / "01.html").is_file())
            index_html = (reports / "index.html").read_text(encoding="utf-8")
            self.assertIn("都道府県別ホテルマーケットレポート", index_html)
            self.assertIn(">市区町村別ホテルマーケットレポート →</a>", index_html)
            self.assertIn("対象年：2025年確定値", index_html)
            self.assertIn("データ公表日 2026/07/01", index_html)
            for heading in ("1. 全国のホテル市況", "2. 都道府県一覧"):
                self.assertIn(heading, index_html)
            self.assertNotIn("2. インバウンド", index_html)
            self.assertNotIn("3. 季節変動ランキング", index_html)
            self.assertNotIn("<h2>2. 市場回復の広がり</h2>", index_html)
            self.assertNotIn("稼働率前年比：上昇", index_html)
            self.assertNotIn("広がりは都道府県別LTM平均差", index_html)
            self.assertIn('colspan="6" class="th-group th-supply-demand">需給', index_html)
            self.assertIn('colspan="2" class="th-group th-inbound">インバウンド', index_html)
            self.assertIn('colspan="3" class="th-group th-seasonality">季節変動', index_html)
            self.assertIn("LTM平均稼働率", index_html)
            self.assertIn('class="sortable numeric th-diff"', index_html)
            self.assertIn("稼働率 前年差", index_html)
            self.assertIn("延べ宿泊者数", index_html)
            self.assertIn("宿泊者数 前年比", index_html)
            self.assertIn('class="numeric" data-sort="11880.0">11,880人泊', index_html)
            self.assertIn("施設数 前年比", index_html)
            self.assertIn("外国人客数 前年比", index_html)
            self.assertIn("Seasonal CV", index_html)
            self.assertIn("ピーク月 / ボトム月", index_html)
            self.assertIn("宿泊施設数", index_html)
            self.assertIn('id="prefecture-search"', index_html)
            self.assertIn('id="prefecture-export"', index_html)
            self.assertIn('id="prefecture-table"', index_html)
            self.assertIn('class="scroll prefecture-scroll"', index_html)
            self.assertIn("#prefecture-table thead{position:sticky", index_html)
            self.assertIn("#prefecture-table tbody td:first-child", index_html)
            self.assertIn("prefecture-hotel-market-2025.csv", index_html)
            self.assertNotIn('class="bar-cell', index_html)
            self.assertIn('class="numeric" data-sort="10.1010101010101">10.1%', index_html)
            self.assertIn('class="numeric td-diff change-negative" data-sort="-10.0">-10.0pt', index_html)
            self.assertIn('class="numeric td-diff change-positive"', index_html)
            self.assertIn('>+10.0%</td>', index_html)
            self.assertIn("標準偏差（σ） ÷ 年間平均客室稼働率（μ）", index_html)
            self.assertIn("最高値（ピーク月）と最低値（ボトム月）", index_html)
            self.assertLess(
                index_html.index("標準偏差（σ） ÷ 年間平均客室稼働率（μ）"),
                index_html.index('id="prefecture-search"'),
            )
            self.assertIn("全国の利用客室数 ÷ 全国の総客室数", index_html)
            self.assertIn("都道府県別稼働率の単純平均ではありません", index_html)
            self.assertIn("2025年 月次全国値の平均", index_html)
            self.assertIn("月次公表値12か月の単純平均", index_html)
            for tick in ("0.0%", "25.0%", "50.0%", "75.0%", "100.0%"):
                self.assertIn(f">{tick}</text>", index_html)
            self.assertNotIn("利用上の注意", index_html)
            detail_html = (reports / "market-sheets" / "01.html").read_text(encoding="utf-8")
            detail_headings = (
                "1. 客室稼働率",
                "2. 延べ宿泊者数（需要）",
                "3. 宿泊施設数（供給）",
            )
            for heading in detail_headings:
                self.assertIn(heading, detail_html)
            positions = [detail_html.index(heading) for heading in detail_headings]
            self.assertEqual(positions, sorted(positions))
            self.assertIn("LTM総延べ宿泊者数", detail_html)
            self.assertIn('id="fact-summary-title">比較サマリー', detail_html)
            self.assertIn(
                "LTM平均客室稼働率は50.0%。前年差は-10.0pt、"
                "2019年差は-10.0pt、全国平均との差は+0.0ptです。",
                detail_html,
            )
            self.assertIn(
                "LTM延べ宿泊者数は11,880人泊。前年比は-10.0%、"
                "2019年水準の99.0%です。",
                detail_html,
            )
            self.assertIn(
                "外国人延べ宿泊者比率は10.1%で、前年差は+1.0pt。"
                "2025年12月の調査対象施設数は110施設で、前年比は+10.0%です。",
                detail_html,
            )
            for interpretation in ("好調", "不調", "有望", "供給過剰"):
                self.assertNotIn(interpretation, detail_html)
            self.assertIn("対象年：2025年確定値", detail_html)
            self.assertIn(">0.0%</text>", detail_html)
            self.assertIn(">100.0%</text>", detail_html)
            self.assertNotIn("利用上の注意", detail_html)
            self.assertIn("宿泊施設数（2025年12月）", detail_html)
            self.assertIn("直近3年の月次総需要トレンドと、年次での需要構造（日本人・外国人比率）の変化", detail_html)
            self.assertIn("総延べ宿泊者数・月次推移（直近3年）", detail_html)
            self.assertIn("年次需要構造と外国人比率（直近3年）", detail_html)
            self.assertIn('class="demand-charts"', detail_html)
            self.assertIn("調査対象施設数の年次推移", detail_html)
            self.assertIn("2019年12月 100施設", detail_html)
            self.assertIn("2025年12月 110施設", detail_html)
            self.assertNotIn(">月</text>", detail_html)
            self.assertNotIn(">客室稼働率</text>", detail_html)
            self.assertIn("11,880人泊", detail_html)
