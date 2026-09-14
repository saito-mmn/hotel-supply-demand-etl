import tempfile
import unittest
from pathlib import Path

from hotel_supply_demand.sheets_sync import (
    DATASETS,
    SheetsSyncError,
    load_credentials_info,
    sync_tableau_sheets,
)


class FakeWorksheet:
    def __init__(self) -> None:
        self.cleared = False
        self.updated_values: list[list[str]] | None = None
        self.value_input_option: str | None = None

    def clear(self) -> None:
        self.cleared = True

    def update(self, values: list[list[str]], value_input_option: str) -> None:
        self.updated_values = values
        self.value_input_option = value_input_option


class FakeSpreadsheet:
    def __init__(self) -> None:
        self.worksheets: dict[str, FakeWorksheet] = {name: FakeWorksheet() for name in DATASETS}

    def worksheet(self, title: str) -> FakeWorksheet:
        return self.worksheets[title]


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    path.write_text("\n".join(",".join(row) for row in rows) + "\n", encoding="utf-8")


def _write_all_dataset_csvs(csv_dir: Path) -> None:
    """Write a minimal valid CSV for every dataset sync_tableau_sheets expects."""
    for name in DATASETS:
        _write_csv(
            csv_dir / f"{name}.csv",
            [["date", "prefecture_code", "value"], ["2025-01-01", "01", "1"]],
        )


class SheetsSyncTest(unittest.TestCase):
    def test_load_credentials_info_parses_json(self) -> None:
        self.assertEqual(
            load_credentials_info('{"type": "service_account"}'), {"type": "service_account"}
        )

    def test_load_credentials_info_rejects_invalid_json(self) -> None:
        with self.assertRaises(SheetsSyncError):
            load_credentials_info("not json")

    def test_sync_replaces_each_worksheet_with_its_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            csv_dir = Path(directory)
            _write_all_dataset_csvs(csv_dir)

            fake_spreadsheet = FakeSpreadsheet()
            result = sync_tableau_sheets(
                csv_dir,
                "sheet-id",
                {"type": "service_account"},
                open_spreadsheet_fn=lambda spreadsheet_id, credentials_info: fake_spreadsheet,
            )

            self.assertEqual(result["spreadsheet_id"], "sheet-id")
            for name in DATASETS:
                worksheet = fake_spreadsheet.worksheets[name]
                self.assertTrue(worksheet.cleared)
                self.assertEqual(worksheet.value_input_option, "USER_ENTERED")
                self.assertIsNotNone(worksheet.updated_values)
            self.assertEqual(result["datasets"]["prefecture_monthly"]["rows"], 1)

    def test_sync_quotes_identifier_columns_as_literal_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            csv_dir = Path(directory)
            _write_all_dataset_csvs(csv_dir)

            fake_spreadsheet = FakeSpreadsheet()
            sync_tableau_sheets(
                csv_dir,
                "sheet-id",
                {},
                open_spreadsheet_fn=lambda spreadsheet_id, credentials_info: fake_spreadsheet,
            )

            prefecture_values = fake_spreadsheet.worksheets["prefecture_monthly"].updated_values
            self.assertEqual(prefecture_values[1], ["2025-01-01", "'01", "1"])

    def test_sync_requires_every_dataset_csv_to_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            csv_dir = Path(directory)
            _write_csv(csv_dir / "prefecture_monthly.csv", [["date"], ["2025-01-01"]])
            with self.assertRaises(SheetsSyncError):
                sync_tableau_sheets(
                    csv_dir,
                    "sheet-id",
                    {},
                    open_spreadsheet_fn=lambda spreadsheet_id, credentials_info: FakeSpreadsheet(),
                )
