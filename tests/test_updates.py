import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hotel_supply_demand.municipality.discovery import parse_source_page as parse_estat
from hotel_supply_demand.municipality.sources import MunicipalitySource
from hotel_supply_demand.prefecture.discovery import parse_source_page as parse_mlit
from hotel_supply_demand.update import (
    _merge_municipality_sources,
    _promote,
    update_municipality,
)


ESTAT_PAGE = """
<article class="stat-resource_list-item stat-resource_list-item-dataset">
  <li>宿泊旅行統計調査（第2次速報値）</li><li>2026年6月</li>
  <li>公開（更新）日 2026-08-31</li>
  <a href="/stat-search/file-download?statInfId=000040500001&amp;fileKind=0">EXCEL</a>
  <a href="/stat-search/file-download?statInfId=000040500001&amp;fileKind=4">閲覧用</a>
</article>
<article class="stat-resource_list-item stat-resource_list-item-dataset">
  <li>宿泊旅行統計調査（第1次速報値）</li><li>2026年7月</li>
  <li>公開（更新）日 2026-08-31</li>
  <a href="/stat-search/file-download?statInfId=000040500002&amp;fileKind=0">EXCEL</a>
</article>
"""

MLIT_PAGE = """
<a href="/kankocho/content/002010340.xlsx">
  <span>2025年（令和7年）1月～12月分（年の確定値）集計結果［Excel］</span>
</a>
<a href="/kankocho/content/002014388.xlsx">
  <span>2026年5月分（第2次速報値）集計結果［Excel］</span>
</a>
<a href="/kankocho/content/002015008.xlsx">
  <span>2025年1月～12月（年の確定値）［Excel］</span>
</a>
"""


def municipality_source(provider: str = "estat") -> MunicipalitySource:
    if provider == "estat":
        stat_inf_id = "000040500001"
        url = (
            "https://www.e-stat.go.jp/stat-search/file-download?"
            "statInfId=000040500001&fileKind=0"
        )
    else:
        stat_inf_id = "mlit:002010412"
        url = "https://www.mlit.go.jp/kankocho/content/002010412.xlsx"
    return MunicipalitySource(
        year=2026,
        month=6,
        release_type="second_preliminary",
        stat_inf_id=stat_inf_id,
        published_on="2026-08-31",
        url=url,
        filename="2026-06_second_preliminary.xlsx",
        provider=provider,
    )


class UpdateTest(unittest.TestCase):
    def _write_sources(self, path: Path) -> None:
        path.write_text(
            'source_page = "https://www.e-stat.go.jp/stat-search/files?'
            'tstat=000001079597"\n\n'
            '[[municipality_sources]]\n'
            'year = 2026\nmonth = 6\nrelease_type = "second_preliminary"\n'
            'stat_inf_id = "000040500001"\npublished_on = "2026-08-31"\n'
            'url = "https://www.e-stat.go.jp/stat-search/file-download?'
            'statInfId=000040500001&fileKind=0"\n'
            'filename = "2026-06_second_preliminary.xlsx"\n',
            encoding="utf-8",
        )

    def test_estat_parser_accepts_only_second_preliminary_original_excel(self) -> None:
        sources = parse_estat(ESTAT_PAGE)

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].stat_inf_id, "000040500001")
        self.assertEqual(sources[0].published_on, "2026-08-31")
        self.assertIn("fileKind=0", sources[0].url)

    def test_mlit_parser_accepts_only_annual_final_aggregate_result(self) -> None:
        candidates = parse_mlit(
            MLIT_PAGE,
            "https://www.mlit.go.jp/kankocho/tokei_hakusyo/shukuhakutokei.html",
        )

        self.assertEqual(candidates[0].year, 2025)
        self.assertEqual(
            candidates[0].url,
            "https://www.mlit.go.jp/kankocho/content/002010340.xlsx",
        )
        self.assertEqual(len(candidates), 1)

    def test_mlit_exception_requires_approval_before_estat_replacement(self) -> None:
        configured = municipality_source("mlit")
        discovered = municipality_source("estat")

        merged, changes, approvals = _merge_municipality_sources(
            [configured], [discovered]
        )

        self.assertEqual(merged, [configured])
        self.assertEqual(changes, [])
        self.assertEqual(approvals[0]["kind"], "exception_conflict")

    def test_promote_restores_previous_outputs_when_later_item_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.txt"
            second = root / "second.txt"
            staged_first = root / "staged-first.txt"
            missing = root / "missing.txt"
            first.write_text("old-first", encoding="utf-8")
            second.write_text("old-second", encoding="utf-8")
            staged_first.write_text("new-first", encoding="utf-8")

            with self.assertRaises(FileNotFoundError):
                _promote([(staged_first, first), (missing, second)])

            self.assertEqual(first.read_text(encoding="utf-8"), "old-first")
            self.assertEqual(second.read_text(encoding="utf-8"), "old-second")

    def test_no_change_keeps_database_and_report_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources_path = root / "sources.toml"
            self._write_sources(sources_path)
            database = root / "market.sqlite3"
            report = root / "reports"
            database.write_bytes(b"original database")
            report.mkdir()
            (report / "index.html").write_text("original report", encoding="utf-8")

            with (
                patch(
                    "hotel_supply_demand.update.discover_municipality_sources",
                    return_value=[municipality_source()],
                ),
                patch(
                    "hotel_supply_demand.update.fetch_municipality_sources",
                    return_value=[
                        {"year": 2026, "month": 6, "status": "unchanged"}
                    ],
                ),
            ):
                result = update_municipality(
                    sources_path, root / "raw", database, report
                )

            self.assertFalse(result["updated"])
            self.assertEqual(database.read_bytes(), b"original database")
            self.assertEqual(
                (report / "index.html").read_text(encoding="utf-8"),
                "original report",
            )

    def test_load_failure_keeps_database_report_and_config_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources_path = root / "sources.toml"
            self._write_sources(sources_path)
            original_sources = sources_path.read_bytes()
            database = root / "market.sqlite3"
            report = root / "reports"
            database.write_bytes(b"original database")
            report.mkdir()
            (report / "index.html").write_text("original report", encoding="utf-8")

            with (
                patch(
                    "hotel_supply_demand.update.discover_municipality_sources",
                    return_value=[municipality_source()],
                ),
                patch(
                    "hotel_supply_demand.update.fetch_municipality_sources",
                    return_value=[
                        {"year": 2026, "month": 6, "status": "downloaded"}
                    ],
                ),
                patch(
                    "hotel_supply_demand.update.load_municipality_source_records",
                    side_effect=ValueError("invalid workbook"),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "invalid workbook"):
                    update_municipality(
                        sources_path, root / "raw", database, report
                    )

            self.assertEqual(database.read_bytes(), b"original database")
            self.assertEqual(sources_path.read_bytes(), original_sources)
            self.assertEqual(
                (report / "index.html").read_text(encoding="utf-8"),
                "original report",
            )


if __name__ == "__main__":
    unittest.main()
