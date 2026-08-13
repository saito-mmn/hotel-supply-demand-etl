import sqlite3
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from hotel_supply_demand.database import build_database
from hotel_supply_demand.fetcher import FetchError, sha256_file, validate_xlsx
from hotel_supply_demand.parser import parse_workbook
from hotel_supply_demand.validation import DataQualityError, validate_records


def make_workbook(path: Path, year: int = 2025) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for month in range(1, 13):
        for table in (1, 4, 8):
            sheet = workbook.create_sheet(f"第{table}表({month}月)")
            sheet["A7"] = f"令和{year - 2018}年{month}月"
            for code in range(1, 48):
                row = 7 + code
                sheet.cell(row, 1, f"{code:02d}地域{code}県")
                sheet.cell(row, 2, 50 if table == 8 else 100 + code)
                if table == 4:
                    sheet.cell(row, 9, 10 + code)
    workbook.save(path)


class PipelineComponentsTest(unittest.TestCase):
    def test_parse_validate_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xlsx = root / "source.xlsx"
            database = root / "result.sqlite3"
            make_workbook(xlsx)
            records = parse_workbook(xlsx, 2025)
            self.assertEqual(validate_records(records, {2025})["rows"], 564)
            manifest = [{"year": 2025, "release_type": "final", "url": "https://www.mlit.go.jp/source.xlsx", "filename": "source.xlsx", "retrieved_at": "2026-01-01T00:00:00+00:00", "sha256": sha256_file(xlsx), "size_bytes": xlsx.stat().st_size}]
            build_database(database, records, manifest)
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(connection.execute("SELECT count(*) FROM monthly_demand").fetchone()[0], 564)
                self.assertEqual(connection.execute("SELECT count(*) FROM monthly_supply").fetchone()[0], 564)
            finally:
                connection.close()

    def test_invalid_xlsx_and_incomplete_records_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.xlsx"
            path.write_text("not an xlsx")
            with self.assertRaises(FetchError):
                validate_xlsx(path)
        with self.assertRaises(DataQualityError):
            validate_records([], {2025})
