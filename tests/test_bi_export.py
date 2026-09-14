import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hotel_supply_demand.bi_export import (
    MUNICIPALITY_FIELDS,
    PREFECTURE_ANNUAL_SUMMARY_FIELDS,
    PREFECTURE_FIELDS,
    BiExportError,
    export_bi_data,
)
from hotel_supply_demand.prefecture.database import SCHEMA


class BiExportTest(unittest.TestCase):
    def _database(self, root: Path) -> Path:
        database = root / "hotel.sqlite3"
        connection = sqlite3.connect(database)
        connection.executescript(SCHEMA)
        connection.executemany(
            """INSERT INTO source_files(
                   id,year,release_type,url,filename,published_on,retrieved_at,
                   sha256,size_bytes
                 ) VALUES(?,?,?,?,?,?,?,?,?)""",
            [
                (
                    1,
                    2019,
                    "final",
                    "https://example.com/2019.xlsx",
                    "2019.xlsx",
                    "2020-06-30",
                    "2020-07-01T00:00:00+00:00",
                    "a" * 64,
                    100,
                ),
                (
                    2,
                    2020,
                    "final",
                    "https://example.com/2020.xlsx",
                    "2020.xlsx",
                    "2021-06-30",
                    "2021-07-01T00:00:00+00:00",
                    "b" * 64,
                    100,
                ),
            ],
        )
        connection.execute("INSERT INTO prefectures VALUES(1,'北海道')")
        # 2019 has a full 12 months (final) so it qualifies for the annual
        # summary; 2020 deliberately stays at just January, to also exercise
        # skipping a year that is still missing months.
        annual_2019 = [
            (2019, 1, 1, "final", 100, 80, 20, 50.0, 10, 1),
            (2019, 2, 1, "final", 80, 65, 15, 30.0, 10, 1),
            (2019, 3, 1, "final", 90, 72, 18, 45.0, 10, 1),
            (2019, 4, 1, "final", 110, 88, 22, 55.0, 10, 1),
            (2019, 5, 1, "final", 120, 95, 25, 60.0, 10, 1),
            (2019, 6, 1, "final", 130, 102, 28, 65.0, 10, 1),
            (2019, 7, 1, "final", 150, 115, 35, 80.0, 10, 1),
            (2019, 8, 1, "final", 140, 108, 32, 75.0, 10, 1),
            (2019, 9, 1, "final", 125, 98, 27, 68.0, 10, 1),
            (2019, 10, 1, "final", 105, 84, 21, 58.0, 10, 1),
            (2019, 11, 1, "final", 95, 76, 19, 48.0, 10, 1),
            (2019, 12, 1, "final", 85, 69, 16, 42.0, 12, 1),
        ]
        connection.executemany(
            "INSERT INTO monthly_prefecture_market VALUES(?,?,?,?,?,?,?,?,?,?)",
            [
                *annual_2019,
                (2020, 1, 1, "final", 120, 90, 30, 60.0, 11, 2),
            ],
        )
        connection.executemany(
            "INSERT INTO national_occupancy VALUES(?,?,?,?,?)",
            [
                (2019, 1, "final", 55.0, 1),
                (2020, 1, "final", 65.0, 2),
            ],
        )
        connection.executemany(
            """INSERT INTO municipality_source_files(
                   id,year,month,release_type,stat_inf_id,url,filename,
                   published_on,retrieved_at,sha256,size_bytes
                 ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    month,
                    2019,
                    month,
                    "second_preliminary",
                    f"stat-{month}",
                    f"https://example.com/2019-{month:02d}.xlsx",
                    f"2019-{month:02d}.xlsx",
                    f"2019-{month + 2:02d}-01",
                    "2019-06-01T00:00:00+00:00",
                    str(month) * 64,
                    100,
                )
                for month in (1, 2, 3)
            ],
        )
        connection.execute("INSERT INTO municipalities VALUES(1,1,'北海道','札幌市')")
        connection.executemany(
            "INSERT INTO monthly_municipality_market VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    2019,
                    1,
                    1,
                    "total",
                    "second_preliminary",
                    50,
                    40,
                    10,
                    30.0,
                    60.0,
                    5,
                    4,
                    1,
                ),
                (
                    2019,
                    3,
                    1,
                    "total",
                    "second_preliminary",
                    80,
                    60,
                    20,
                    40.0,
                    70.0,
                    6,
                    5,
                    3,
                ),
            ],
        )
        connection.commit()
        connection.close()
        return database

    def test_export_generates_tableau_contract_and_comparisons(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = self._database(root)
            output = root / "tableau"

            result = export_bi_data(database, output)

            self.assertEqual(result["datasets"]["prefecture_monthly"]["rows"], 15)
            with (output / "prefecture_monthly.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(list(rows[0]), PREFECTURE_FIELDS)
            hokkaido = next(
                row
                for row in rows
                if row["date"] == "2020-01-01" and row["prefecture_name"] == "北海道"
            )
            self.assertEqual(hokkaido["foreign_share_pct"], "25.0")
            self.assertEqual(hokkaido["occupancy_yoy_delta_pp"], "10.0")
            self.assertEqual(hokkaido["occupancy_2019_delta_pp"], "10.0")
            self.assertEqual(hokkaido["has_yoy_comparison"], "1")
            national = next(
                row
                for row in rows
                if row["date"] == "2020-01-01" and row["geography_level"] == "national"
            )
            self.assertEqual(national["prefecture_code"], "00")
            self.assertEqual(national["guest_nights_total"], "")

    def test_annual_summary_covers_only_complete_calendar_years(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "tableau"

            result = export_bi_data(self._database(root), output)

            self.assertEqual(result["datasets"]["prefecture_annual_summary"]["rows"], 1)
            with (output / "prefecture_annual_summary.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(list(rows[0]), PREFECTURE_ANNUAL_SUMMARY_FIELDS)
            # 2020 only has January in the fixture, so only 2019 qualifies.
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["year"], "2019")
            self.assertEqual(row["prefecture_code"], "01")
            self.assertEqual(row["guest_nights_total"], "1330")
            self.assertAlmostEqual(float(row["foreign_share_pct"]), 278 / 1330 * 100)
            self.assertAlmostEqual(float(row["occupancy_rate_pct_avg"]), 676 / 12)
            self.assertEqual(row["occupancy_seasonal_range_pp"], "50.0")
            self.assertEqual(row["occupancy_peak_month"], "7")
            self.assertEqual(row["occupancy_bottom_month"], "2")
            # December's facility count (12), not January's (10).
            self.assertEqual(row["facility_count"], "12")

    def test_municipality_export_inserts_explicit_not_listed_months(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "tableau"
            export_bi_data(self._database(root), output)

            with (output / "municipality_monthly.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(list(rows[0]), MUNICIPALITY_FIELDS)
            self.assertEqual(len(rows), 3)
            missing = next(row for row in rows if row["date"] == "2019-02-01")
            self.assertEqual(missing["record_status"], "not_listed")
            self.assertEqual(missing["occupancy_rate_pct"], "")
            self.assertEqual(missing["source_published_on"], "2019-04-01")
            self.assertEqual(missing["coverage_start_date"], "2019-01-01")
            self.assertEqual(missing["coverage_end_date"], "2019-03-01")
            self.assertEqual(missing["coverage_months"], "2")

    def test_failed_export_preserves_previous_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "invalid.sqlite3"
            sqlite3.connect(database).close()
            output = root / "tableau"
            output.mkdir()
            marker = output / "existing.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(BiExportError, "requires database objects"):
                export_bi_data(database, output)

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
