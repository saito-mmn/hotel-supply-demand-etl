from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hotel_supply_demand.config import ConfigurationError, get_estat_app_id


class ConfigTest(unittest.TestCase):
    def test_get_estat_app_id_rejects_missing_value(self) -> None:
        environment = {key: value for key, value in os.environ.items() if key != "ESTAT_APP_ID"}
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "ESTAT_APP_ID is not set"):
                get_estat_app_id(Path("/nonexistent/.env"))

    def test_get_estat_app_id_strips_whitespace(self) -> None:
        with patch.dict(os.environ, {"ESTAT_APP_ID": "  test-id  "}, clear=True):
            self.assertEqual(get_estat_app_id(), "test-id")

    def test_get_estat_app_id_reads_dotenv_without_mutating_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text("# local secret\nESTAT_APP_ID='dotenv-id'\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(get_estat_app_id(dotenv), "dotenv-id")
                self.assertNotIn("ESTAT_APP_ID", os.environ)


if __name__ == "__main__":
    unittest.main()
