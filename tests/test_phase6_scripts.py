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


if __name__ == "__main__":
    unittest.main()
