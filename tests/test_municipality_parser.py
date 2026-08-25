import tempfile
import unittest
from pathlib import Path

from municipality_fixtures import make_municipality_workbook
from openpyxl import load_workbook

from hotel_supply_demand.municipality.parser import (
    MunicipalityWorkbookFormatError,
    parse_municipality_workbook,
)


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
            if record.municipality_name == "札幌市" and record.room_size_class == "total"
        )
        self.assertEqual(sapporo.total_guests, 100)
        self.assertIsNone(sapporo.occupied_rooms)
        self.assertIsNone(sapporo.occupancy_rate)
