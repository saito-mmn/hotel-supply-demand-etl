import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from openpyxl import Workbook, load_workbook

from hotel_supply_demand.database import build_database
from hotel_supply_demand.fetcher import sha256_file
from hotel_supply_demand.models import MonthlyRecord
from hotel_supply_demand.municipality.database import load_municipality_records
from hotel_supply_demand.municipality.fetcher import fetch_municipality_sources
from hotel_supply_demand.municipality.parser import (
    MunicipalityWorkbookFormatError,
    parse_municipality_workbook,
)
from hotel_supply_demand.municipality.sources import MunicipalitySource
from hotel_supply_demand.municipality.pipeline import run_municipality_pipeline
from hotel_supply_demand.municipality.report import _line_chart, generate_municipality_reports
from hotel_supply_demand.municipality.validation import (
    MunicipalityDataQualityError,
    validate_municipality_records,
)


def make_municipality_workbook(path: Path, *, omit_table: int | None = None) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    locations = ["北海道札幌市", "沖縄県石垣市"]
    for table in (5, 6, 8, 11, 12):
        if table == omit_table:
            continue
        sheet = workbook.create_sheet(f"参考第{table}表(5月)")
        sheet.cell(1, 1, f"参考第{table}表　施設所在地(主な市区町村)のテスト")
        sheet.cell(4, 1, "施設所在地\n（主な市区町村）")
        for offset, location in enumerate(locations, 7):
            sheet.cell(offset, 1, location)
        if table == 5:
            sheet.append([])
            values = [
                [2, "-", 3, "-", 4, 4],
                [5, 5, 2, "-", 10, 8],
            ]
            for row, row_values in zip(range(7, 9), values, strict=True):
                for column, value in enumerate(row_values, 2):
                    sheet.cell(row, column, value)
        else:
            values_by_table = {
                6: [[100, "-", "-", 100], [200, 20, "-", 180]],
                8: [[25, "-", "-", 25], [60, 5, "-", 55]],
                11: [[50, "-", "-", 50], [80, 8, "-", 72]],
                12: [[60.5, "-", "-", 60.5], [70.0, 20.0, "-", 72.0]],
            }
            for row, row_values in zip(range(7, 9), values_by_table[table], strict=True):
                for column, value in enumerate(row_values, 2):
                    sheet.cell(row, column, value)
    workbook.save(path)


class MunicipalityParserTest(unittest.TestCase):
    def test_join_reference_tables_by_location_and_room_class(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "monthly.xlsx"
            make_municipality_workbook(path)
            records = parse_municipality_workbook(path, 2026, 5)

        self.assertEqual(len(records), 8)
        sapporo = next(
            record
            for record in records
            if record.municipality_name == "札幌市" and record.room_size_class == "total"
        )
        self.assertEqual(sapporo.prefecture_code, 1)
        self.assertEqual(sapporo.prefecture_name, "北海道")
        self.assertEqual(sapporo.total_guests, 100)
        self.assertEqual(sapporo.japanese_guests, 75)
        self.assertEqual(sapporo.foreign_guests, 25)
        self.assertEqual(sapporo.occupied_rooms, 50)
        self.assertEqual(sapporo.occupancy_rate, 60.5)
        self.assertEqual(sapporo.population_facilities, 9)
        self.assertIsNone(sapporo.responding_facilities)

        ishigaki_small = next(
            record
            for record in records
            if record.municipality_name == "石垣市" and record.room_size_class == "1_to_9"
        )
        self.assertEqual(ishigaki_small.total_guests, 20)
        self.assertEqual(ishigaki_small.responding_facilities, 5)
        self.assertIsNone(
            next(
                record
                for record in records
                if record.municipality_name == "石垣市"
                and record.room_size_class == "10_to_19"
            ).total_guests
        )

    def test_missing_reference_table_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "monthly.xlsx"
            make_municipality_workbook(path, omit_table=12)
            with self.assertRaisesRegex(
                MunicipalityWorkbookFormatError, "missing worksheet: 参考第12表"
            ):
                parse_municipality_workbook(path, 2026, 5)

    def test_metric_specific_missing_municipality_becomes_null(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "monthly.xlsx"
            make_municipality_workbook(path)
            workbook = load_workbook(path)
            for sheet_name in ("参考第11表(5月)", "参考第12表(5月)"):
                workbook[sheet_name].delete_rows(7)
            workbook.save(path)
            records = parse_municipality_workbook(path, 2026, 5)
        sapporo = next(
            record
            for record in records
            if record.municipality_name == "札幌市"
            and record.room_size_class == "total"
        )
        self.assertEqual(sapporo.total_guests, 100)
        self.assertIsNone(sapporo.occupied_rooms)
        self.assertIsNone(sapporo.occupancy_rate)

    def test_validate_and_idempotently_load_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workbook = root / "monthly.xlsx"
            database = root / "market.sqlite3"
            make_municipality_workbook(workbook)
            records = parse_municipality_workbook(workbook, 2026, 5)
            quality = validate_municipality_records(records)
            self.assertEqual(quality["rows"], 8)
            self.assertEqual(quality["municipalities"], 2)
            source = MunicipalitySource(
                year=2026,
                month=5,
                release_type="second_preliminary",
                stat_inf_id="000040482630",
                published_on="2026-07-31",
                url="https://www.e-stat.go.jp/stat-search/file-download?statInfId=000040482630&fileKind=0",
                filename="2026-05_second_preliminary.xlsx",
            )
            provenance = {
                "retrieved_at": "2026-08-15T00:00:00+00:00",
                "sha256": "a" * 64,
                "size_bytes": workbook.stat().st_size,
            }
            load_municipality_records(database, records, source, provenance)
            load_municipality_records(database, records, source, provenance)
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(
                    connection.execute(
                        "SELECT count(*) FROM monthly_municipality_market"
                    ).fetchone()[0],
                    8,
                )
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM municipalities").fetchone()[0],
                    2,
                )
                self.assertEqual(
                    connection.execute(
                        """SELECT total_guests FROM monthly_municipality_market AS f
                           JOIN municipalities AS m ON m.id=f.municipality_id
                           WHERE m.municipality_name='札幌市' AND room_size_class='total'"""
                    ).fetchone()[0],
                    100,
                )
            finally:
                connection.close()

            prefecture_record = MonthlyRecord(
                year=2025,
                month=1,
                prefecture_code=1,
                prefecture_name="北海道",
                total_guests=1,
                japanese_guests=1,
                foreign_guests=0,
                occupancy_rate=50.0,
                facilities=1,
            )
            build_database(
                database,
                [prefecture_record],
                [
                    {
                        "year": 2025,
                        "release_type": "final",
                        "url": "https://www.mlit.go.jp/2025.xlsx",
                        "filename": "2025.xlsx",
                        "published_on": "2026-07-06",
                        "retrieved_at": "2026-08-15T00:00:00+00:00",
                        "sha256": "b" * 64,
                        "size_bytes": 1,
                    }
                ],
            )
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(
                    connection.execute(
                        "SELECT count(*) FROM monthly_municipality_market"
                    ).fetchone()[0],
                    8,
                )
            finally:
                connection.close()

    def test_duplicate_record_fails_quality_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "monthly.xlsx"
            make_municipality_workbook(path)
            records = parse_municipality_workbook(path, 2026, 5)
            duplicate = replace(records[0])
            with self.assertRaisesRegex(
                MunicipalityDataQualityError, "duplicate municipality record keys"
            ):
                validate_municipality_records([*records, duplicate])

    def test_cached_fetch_and_build_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_dir = root / "raw"
            raw_dir.mkdir()
            workbook = raw_dir / "2026-05_second_preliminary.xlsx"
            database = root / "hotel_market.sqlite3"
            sources_path = root / "municipality_sources.toml"
            make_municipality_workbook(workbook)
            source = MunicipalitySource(
                year=2026,
                month=5,
                release_type="second_preliminary",
                stat_inf_id="000040482630",
                published_on="2026-07-31",
                url="https://www.e-stat.go.jp/stat-search/file-download?statInfId=000040482630&fileKind=0",
                filename=workbook.name,
            )
            sources_path.write_text(
                """[[municipality_sources]]
year = 2026
month = 5
release_type = "second_preliminary"
stat_inf_id = "000040482630"
published_on = "2026-07-31"
url = "https://www.e-stat.go.jp/stat-search/file-download?statInfId=000040482630&fileKind=0"
filename = "2026-05_second_preliminary.xlsx"
""",
                encoding="utf-8",
            )
            entry = {
                "year": 2026,
                "month": 5,
                "release_type": "second_preliminary",
                "stat_inf_id": source.stat_inf_id,
                "url": source.url,
                "filename": source.filename,
                "period_start": "2026-05",
                "period_end": "2026-05",
                "published_on": source.published_on,
                "retrieved_at": "2026-08-15T00:00:00+00:00",
                "sha256": sha256_file(workbook),
                "size_bytes": workbook.stat().st_size,
            }
            (raw_dir / "manifest.json").write_text(
                json.dumps({"schema_version": 1, "files": [entry]}), encoding="utf-8"
            )
            fetch_result = fetch_municipality_sources([source], raw_dir)
            self.assertEqual(fetch_result[0]["status"], "skipped")
            result = run_municipality_pipeline(
                sources_path, raw_dir, database, fetch=False
            )
            self.assertEqual(result["periods"], 1)
            self.assertEqual(result["rows"], 8)
            self.assertEqual(result["municipalities"], {"2026-05": 2})
            reports = root / "reports"
            report_result = generate_municipality_reports(database, reports)
            self.assertEqual(report_result["market_sheets"], 2)
            self.assertEqual(report_result["periods"], ["2026-05"])
            self.assertTrue((reports / "index.html").is_file())
            index_html = (reports / "index.html").read_text(encoding="utf-8")
            self.assertIn("Municipality Hotel Market Monitor", index_html)
            self.assertIn("札幌市", index_html)
            self.assertIn('data-column="4" data-type="number"', index_html)
            self.assertIn("warning-badge", index_html)
            detail_html = (reports / "market-sheets" / "1.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("札幌市 Market Sheet", detail_html)
            self.assertIn("客室規模別内訳", detail_html)
            self.assertIn("2026年5月単月（最新掲載月）", detail_html)

    def test_line_chart_keeps_missing_month_as_a_gap(self):
        history = [
            {"year": 2025, "month": 11, "total_guests": 10},
            {"year": 2025, "month": 12, "total_guests": 20},
            {"year": 2026, "month": 2, "total_guests": 30},
            {"year": 2026, "month": 3, "total_guests": 40},
        ]
        chart = _line_chart(history, "total_guests", "人", "#2563eb")
        self.assertIn(">26/01<", chart)
        self.assertEqual(chart.count("<polyline"), 2)
