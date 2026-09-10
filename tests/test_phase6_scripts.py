import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_update_result import find_blockers, validate_update_result


class UpdateResultTest(unittest.TestCase):
    def test_empty_review_fields_are_accepted(self) -> None:
        payload = {
            "prefecture": {"updated": False, "configuration_required": []},
            "municipality": {"updated": True, "approval_required": []},
        }
        self.assertEqual(find_blockers(payload), [])

    def test_nested_review_requirement_blocks_publication(self) -> None:
        payload = {
            "prefecture": {
                "updated": False,
                "configuration_required": [{"year": 2026}],
            }
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "configuration_required"):
                validate_update_result(path)


class DeploymentWorkflowTest(unittest.TestCase):
    def test_pages_regenerates_from_latest_successful_database(self) -> None:
        workflow = Path(".github/workflows/pages.yml").read_text(encoding="utf-8")
        restore = workflow.index("actions/cache/restore@v4")
        require_database = workflow.index("test -f data/processed/hotel_market.sqlite3")
        prefecture_report = workflow.index("hotel-etl monitor")
        municipality_report = workflow.index("hotel-etl municipality-report")
        stage = workflow.index("python3 scripts/prepare_pages.py")
        self.assertLess(restore, require_database)
        self.assertLess(require_database, prefecture_report)
        self.assertLess(prefecture_report, municipality_report)
        self.assertLess(municipality_report, stage)

    def test_update_regenerates_both_reports_before_staging(self) -> None:
        workflow = Path(".github/workflows/update-and-deploy.yml").read_text(encoding="utf-8")
        result_gate = workflow.index("scripts/check_update_result.py update-result.json")
        prefecture_report = workflow.index("hotel-etl monitor")
        municipality_report = workflow.index("hotel-etl municipality-report")
        stage = workflow.index("python scripts/prepare_pages.py")
        self.assertLess(result_gate, prefecture_report)
        self.assertLess(prefecture_report, municipality_report)
        self.assertLess(municipality_report, stage)


if __name__ == "__main__":
    unittest.main()
