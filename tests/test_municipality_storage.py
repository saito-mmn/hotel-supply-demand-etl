import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from municipality_fixtures import make_municipality_workbook

from hotel_supply_demand.municipality.database import load_municipality_records
from hotel_supply_demand.municipality.parser import parse_municipality_workbook
from hotel_supply_demand.municipality.sources import MunicipalitySource
from hotel_supply_demand.municipality.validation import (
    MunicipalityDataQualityError,
    validate_municipality_records,
)
from hotel_supply_demand.prefecture.database import build_database
from hotel_supply_demand.prefecture.models import MonthlyRecord


class MunicipalityStorageTest(unittest.TestCase):
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
                2026,
                5,
                "second_preliminary",
                "000040482630",
                "2026-07-31",
                "https://example.com/monthly.xlsx",
                "2026-05_second_preliminary.xlsx",
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
            finally:
                connection.close()

            build_database(
                database,
                [
                    MonthlyRecord(
                        year=2025,
                        month=1,
                        prefecture_code=1,
                        prefecture_name="北海道",
                        total_guests=1,
                        foreign_guests=0,
                        japanese_guests=1,
                        occupancy_rate=50.0,
                        facilities=1,
                    )
                ],
                [
                    {
                        "year": 2025,
                        "release_type": "final",
                        "url": "https://example.com/2025.xlsx",
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
            with self.assertRaisesRegex(
                MunicipalityDataQualityError, "duplicate municipality record keys"
            ):
                validate_municipality_records([*records, replace(records[0])])
