"""Push exported Tableau CSV datasets into Google Sheets tabs.

Tableau Public can only auto-refresh a handful of connector types --
Google Sheets, OneDrive, Dropbox, and Box -- so routing the CSVs through
a Google Sheet is the automation path for keeping a Tableau Public
workbook current without a manual republish. This module replaces the
contents of the worksheet tabs that match each exported dataset; once a
Tableau Public workbook is connected to those tabs and scheduled
refresh is turned on in its settings, Tableau pulls the change on its
own schedule. Nothing here talks to Tableau itself.

The target spreadsheet must already contain one worksheet (tab) per
name in ``DATASETS``, shared as Editor with the service account whose
credentials are passed in.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Protocol

DATASETS = ["prefecture_monthly", "municipality_monthly", "metadata"]

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Columns that are identifiers/codes rather than genuine numbers or dates.
# Sheets is written with value_input_option="USER_ENTERED" so Tableau sees
# real number/date types instead of everything coming in as text, but that
# same auto-detection would mangle these columns -- e.g. prefecture_code's
# zero-padding ("01") would collapse to the number 1, and an all-digit
# source_stat_inf_id or (astronomically unlikely, but possible) source_sha256
# would silently become a number. These are force-quoted as literal text
# instead (see `_quote_as_text`).
FORCE_TEXT_COLUMNS = {"prefecture_code", "municipality_key", "source_stat_inf_id", "source_sha256"}


class SheetsSyncError(ValueError):
    pass


class WorksheetLike(Protocol):
    def clear(self) -> Any: ...

    def update(self, values: list[list[str]], value_input_option: str) -> Any: ...


class SpreadsheetLike(Protocol):
    def worksheet(self, title: str) -> WorksheetLike: ...


def _quote_as_text(value: str) -> str:
    """Force a value to stay literal text under value_input_option=USER_ENTERED.

    A leading apostrophe is Sheets' own convention for "treat this as text
    even if it looks like a number or formula" -- the same thing typing
    ``'01`` into a cell in the UI does. It is stripped from what displays.
    """
    return f"'{value}" if value else value


def _read_csv_rows(path: Path, force_text_columns: set[str]) -> list[list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return rows
    header = rows[0]
    text_indexes = {index for index, name in enumerate(header) if name in force_text_columns}
    if not text_indexes:
        return rows
    for row in rows[1:]:
        for index in text_indexes:
            row[index] = _quote_as_text(row[index])
    return rows


def load_credentials_info(raw: str) -> dict[str, Any]:
    """Parse a Google service-account JSON key from a string (e.g. an env var)."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise SheetsSyncError("credentials must be a JSON service-account key") from error


def open_spreadsheet(spreadsheet_id: str, credentials_info: dict[str, Any]) -> SpreadsheetLike:
    """Authenticate with a service account and open the target spreadsheet.

    Imports are deferred so importing this module (and the CLI) never
    requires the optional ``sheets`` extra unless this function is
    actually called.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as error:
        raise SheetsSyncError(
            'the "sheets" extra is required for this command: pip install -e ".[sheets]"'
        ) from error

    credentials = Credentials.from_service_account_info(credentials_info, scopes=SHEETS_SCOPES)
    client = gspread.authorize(credentials)
    return client.open_by_key(spreadsheet_id)


def sync_tableau_sheets(
    csv_dir: Path,
    spreadsheet_id: str,
    credentials_info: dict[str, Any],
    *,
    open_spreadsheet_fn=open_spreadsheet,
) -> dict[str, Any]:
    """Replace each dataset's worksheet tab with the matching exported CSV.

    ``open_spreadsheet_fn`` is injectable so tests can exercise this
    against a fake spreadsheet without a live Google Sheets credential.
    """
    csv_dir = Path(csv_dir)
    missing = [name for name in DATASETS if not (csv_dir / f"{name}.csv").is_file()]
    if missing:
        raise SheetsSyncError(f"missing exported CSV(s) in {csv_dir}: {', '.join(missing)}")

    spreadsheet = open_spreadsheet_fn(spreadsheet_id, credentials_info)
    synced: dict[str, Any] = {}
    for dataset_name in DATASETS:
        rows = _read_csv_rows(csv_dir / f"{dataset_name}.csv", FORCE_TEXT_COLUMNS)
        worksheet = spreadsheet.worksheet(dataset_name)
        worksheet.clear()
        # USER_ENTERED lets Sheets parse plain numbers and ISO dates into
        # real number/date types (matching what Tableau expects) instead of
        # leaving every column as text, which RAW would do.
        worksheet.update(values=rows, value_input_option="USER_ENTERED")
        synced[dataset_name] = {"worksheet": dataset_name, "rows": max(len(rows) - 1, 0)}
    return {"spreadsheet_id": spreadsheet_id, "datasets": synced}
