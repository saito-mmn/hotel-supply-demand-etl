import json
import tempfile
import unittest
from pathlib import Path

from municipality_fixtures import make_municipality_workbook

from hotel_supply_demand.fetcher import sha256_file
from hotel_supply_demand.municipality.fetcher import fetch_municipality_sources
from hotel_supply_demand.municipality.pipeline import run_municipality_pipeline
from hotel_supply_demand.municipality.sources import MunicipalitySource


class MunicipalityPipelineTest(unittest.TestCase):
    def test_cached_fetch_and_build_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_dir = root / "raw"
            raw_dir.mkdir()
            workbook = raw_dir / "2026-05_second_preliminary.xlsx"
            database = root / "hotel_market.sqlite3"
            sources_path = root / "municipality_sources.toml"
            make_municipality_workbook(workbook)
            source = MunicipalitySource(
                2026,
                5,
                "second_preliminary",
                "000040482630",
                "2026-07-31",
                "https://www.e-stat.go.jp/stat-search/file-download?statInfId=000040482630&fileKind=0",
                workbook.name,
            )
            sources_path.write_text(
                f'''[[municipality_sources]]
year = 2026
month = 5
release_type = "second_preliminary"
stat_inf_id = "{source.stat_inf_id}"
published_on = "{source.published_on}"
url = "{source.url}"
filename = "{source.filename}"
''',
                encoding="utf-8",
            )
            entry = {
                "year": 2026,
                "month": 5,
                "release_type": "second_preliminary",
                "stat_inf_id": source.stat_inf_id,
                "url": source.url,
                "filename": source.filename,
                "period_start": "2026-05",
                "period_end": "2026-05",
                "published_on": source.published_on,
                "retrieved_at": "2026-08-15T00:00:00+00:00",
                "sha256": sha256_file(workbook),
                "size_bytes": workbook.stat().st_size,
            }
            (raw_dir / "manifest.json").write_text(
                json.dumps({"schema_version": 1, "files": [entry]}), encoding="utf-8"
            )
            self.assertEqual(fetch_municipality_sources([source], raw_dir)[0]["status"], "skipped")
            result = run_municipality_pipeline(sources_path, raw_dir, database, fetch=False)
            self.assertEqual(result["periods"], 1)
            self.assertEqual(result["rows"], 8)
            self.assertEqual(result["municipalities"], {"2026-05": 2})
