from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from .database import build_database
from .fetcher import fetch_sources, sha256_file, validate_xlsx
from .parser import parse_national_occupancy, parse_workbook
from .sources import Source, load_sources
from .validation import validate_records


def build_prefecture_database(
    sources: list[Source],
    raw_dir: Path,
    database_path: Path,
    progress: Callable[[str], None] | None = None,
) -> dict:
    notify = progress or (lambda _message: None)
    manifest_path = raw_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    indexed = {(item["year"], item["release_type"]): item for item in manifest["files"]}
    records = []
    national_occupancy = []
    used_entries = []
    for source in sources:
        notify(f"{source.year}年のExcelを変換しています")
        path = raw_dir / source.filename
        validate_xlsx(path)
        entry = {
            **indexed[(source.year, source.release_type)],
            "published_on": source.published_on,
        }
        if sha256_file(path) != entry["sha256"]:
            raise ValueError(f"hash mismatch: {path}")
        records.extend(parse_workbook(path, source.year, source.release_type))
        national_occupancy.extend(
            parse_national_occupancy(path, source.year, source.release_type)
        )
        used_entries.append(entry)
    notify(f"{len(records):,}行の品質を検証しています")
    quality = validate_records(records, {source.year for source in sources})
    notify("SQLiteを生成しています")
    build_database(database_path, records, used_entries, national_occupancy)
    return {**quality, "database": str(database_path), "source_files": len(used_entries)}


def run_pipeline(
    sources_path: Path,
    raw_dir: Path,
    database_path: Path,
    years: set[int] | None = None,
    fetch: bool = True,
    progress: Callable[[str], None] | None = None,
) -> dict:
    notify = progress or (lambda _message: None)
    sources = load_sources(sources_path, years)
    if fetch:
        notify(f"公式Excelを確認しています（{len(sources)}ファイル）")
        fetch_sources(sources, raw_dir)
    return build_prefecture_database(sources, raw_dir, database_path, progress)
