import tempfile
import unittest
from pathlib import Path

from hotel_supply_demand.municipality.sources import (
    MunicipalitySourceConfigurationError,
    load_municipality_sources,
)


class MunicipalitySourcesTest(unittest.TestCase):
    def test_load_fixed_estat_source(self):
        sources = load_municipality_sources(Path("config/municipality_sources.toml"))
        periods = [(source.year, source.month) for source in sources]
        self.assertEqual(len(periods), 89)
        self.assertEqual(periods[0], (2019, 1))
        january = next(source for source in sources if (source.year, source.month) == (2026, 1))
        self.assertEqual(january.provider, "mlit")
        self.assertEqual(january.stat_inf_id, "mlit:002010412")
        self.assertEqual(periods[-1], (2026, 5))
        self.assertEqual(sources[-1].stat_inf_id, "000040482630")
        self.assertEqual(sources[-1].published_on, "2026-07-31")

    def test_rejects_viewer_excel(self):
        content = """[[municipality_sources]]
year = 2026
month = 5
release_type = "second_preliminary"
stat_inf_id = "000040482630"
published_on = "2026-07-31"
url = "https://www.e-stat.go.jp/stat-search/file-download?statInfId=000040482630&fileKind=4"
filename = "2026-05_second_preliminary.xlsx"
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.toml"
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(MunicipalitySourceConfigurationError):
                load_municipality_sources(path)
