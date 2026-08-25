import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_pages import prepare_pages


class PreparePagesTest(unittest.TestCase):
    def _source(self, root: Path) -> Path:
        source = root / "reports"
        (source / "market-sheets").mkdir(parents=True)
        (source / "municipalities" / "market-sheets").mkdir(parents=True)
        (source / "index.html").write_text(
            '<a href="market-sheets/01.html">Prefecture</a>'
            '<a href="municipalities/index.html">Municipalities</a>',
            encoding="utf-8",
        )
        (source / "market-sheets" / "01.html").write_text(
            '<a href="../index.html">Back</a>', encoding="utf-8"
        )
        (source / "municipalities" / "index.html").write_text(
            '<a href="market-sheets/1.html">Municipality</a>', encoding="utf-8"
        )
        (source / "municipalities" / "market-sheets" / "1.html").write_text(
            '<a href="../index.html">Back</a>', encoding="utf-8"
        )
        (source / "report-metadata.json").write_text(
            json.dumps({"rows": 1}), encoding="utf-8"
        )
        (source / "municipalities" / "report-metadata.json").write_text(
            json.dumps({"municipalities": 1}), encoding="utf-8"
        )
        return source

    def test_stages_only_public_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            (source / "prefecture-market.csv").write_text("not public", encoding="utf-8")
            (source / "municipalities" / "report-metadata.json").write_text(
                json.dumps({"municipalities": 1}), encoding="utf-8"
            )

            copied, prefectures, municipalities = prepare_pages(source, root / "pages")

            self.assertEqual((copied, prefectures, municipalities), (4, 1, 1))
            self.assertFalse((root / "pages" / "prefecture-market.csv").exists())
            self.assertFalse((root / "pages" / "report-metadata.json").exists())

    def test_rejects_broken_internal_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            (source / "index.html").write_text(
                '<a href="missing.html">Missing</a>', encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "broken link"):
                prepare_pages(source, root / "pages")

    def test_rejects_sensitive_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            (source / "market-sheets" / "01.html").write_text(
                "/Users/example/private", encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "sensitive marker"):
                prepare_pages(source, root / "pages")

    def test_rejects_output_that_contains_source_without_deleting_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)

            with self.assertRaisesRegex(ValueError, "must be independent"):
                prepare_pages(source, root)

            self.assertTrue(source.is_dir())
            self.assertTrue((source / "index.html").is_file())

    def test_rejects_output_inside_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)

            with self.assertRaisesRegex(ValueError, "must be independent"):
                prepare_pages(source, source / "pages")


if __name__ == "__main__":
    unittest.main()
