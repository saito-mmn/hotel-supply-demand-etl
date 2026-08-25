from __future__ import annotations

import io
import json
import unittest
from typing import Any
from urllib.parse import parse_qs, urlparse

from hotel_supply_demand.estat_client import EstatClient


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class EstatClientTest(unittest.TestCase):
    def test_search_encodes_query(self) -> None:
        captured_url = ""

        def opener(request: Any, **_: Any) -> FakeResponse:
            nonlocal captured_url
            captured_url = request.full_url
            body = {
                "GET_STATS_LIST": {
                    "RESULT": {"STATUS": 0},
                    "DATALIST_INF": {"TABLE_INF": []},
                }
            }
            return FakeResponse(json.dumps(body).encode())

        client = EstatClient(app_id="secret-test-id", opener=opener)
        payload = client.get_stats_list(
            search_word="宿泊旅行統計調査",
            stats_code="00601020",
            survey_years="2025",
            limit=5,
        )

        query = parse_qs(urlparse(captured_url).query)
        self.assertEqual(query["appId"], ["secret-test-id"])
        self.assertEqual(query["searchWord"], ["宿泊旅行統計調査"])
        self.assertEqual(query["statsCode"], ["00601020"])
        self.assertEqual(query["surveyYears"], ["2025"])
        self.assertEqual(payload["GET_STATS_LIST"]["RESULT"]["STATUS"], 0)


if __name__ == "__main__":
    unittest.main()
