import tempfile
import unittest
from pathlib import Path

from hotel_supply_demand.prefecture.sources import SourceConfigurationError, load_sources


class SourcesTest(unittest.TestCase):
    def test_accepts_estat_original_excel(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.toml"
            path.write_text(
                '[[sources]]\nyear=2025\nrelease_type="final"\n'
                'url="https://www.e-stat.go.jp/stat-search/file-download?'
                'statInfId=000040475399&fileKind=0"\n'
                'filename="2025_final.xlsx"\npublished_on="2026-07-06"\n',
                encoding="utf-8",
            )

            sources = load_sources(path)

            self.assertEqual(len(sources), 1)
            self.assertIn("fileKind=0", sources[0].url)

    def test_load_and_filter(self):
        sources = load_sources(Path("sources.toml"), {2019, 2025})
        self.assertEqual([item.year for item in sources], [2019, 2025])
        self.assertEqual(sources[-1].published_on, "2026-07-06")

    def test_rejects_untrusted_host(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.toml"
            path.write_text('[[sources]]\nyear=2025\nrelease_type="final"\nurl="https://example.com/a.xlsx"\nfilename="a.xlsx"\npublished_on="2026-07-06"\n')
            with self.assertRaises(SourceConfigurationError):
                load_sources(path)
