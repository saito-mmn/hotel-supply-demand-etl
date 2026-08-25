"""Orchestrate municipality-level monthly Excel ingestion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from ..fetcher import sha256_file, validate_xlsx
from .database import load_municipality_records
from .fetcher import fetch_municipality_sources
from .parser import parse_municipality_workbook
from .sources import MunicipalitySource, load_municipality_sources


def load_municipality_source_records(
    sources: list[MunicipalitySource],
    raw_dir: Path,
    database_path: Path,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Validate downloaded workbooks and transactionally load the selected periods."""
    notify = progress or (lambda _message: None)
    manifest_path = raw_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    indexed = {
        (int(item["year"]), int(item["month"]), str(item["release_type"])): item
        for item in manifest["files"]
    }
    summaries = []
    for source in sources:
        label = f"{source.year}年{source.month}月"
        notify(f"{label}の市区町村Excelを変換しています")
        path = raw_dir / source.filename
        validate_xlsx(path)
        entry = indexed[(source.year, source.month, source.release_type)]
        if entry.get("stat_inf_id") != source.stat_inf_id:
            raise ValueError(f"source ID mismatch: {path}")
        if sha256_file(path) != entry["sha256"]:
            raise ValueError(f"hash mismatch: {path}")
        records = parse_municipality_workbook(
            path, source.year, source.month, source.release_type
        )
        notify(f"{label}の{len(records):,}行を検証・ロードしています")
        summaries.append(load_municipality_records(database_path, records, source, entry))
    return {
        "periods": len(summaries),
        "rows": sum(summary["rows"] for summary in summaries),
        "municipalities": {
            f'{summary["year"]}-{summary["month"]:02d}': summary["municipalities"]
            for summary in summaries
        },
        "database": str(database_path),
    }


def run_municipality_pipeline(
    sources_path: Path,
    raw_dir: Path,
    database_path: Path,
    periods: set[tuple[int, int]] | None = None,
    *,
    fetch: bool = True,
    progress: Callable[[str], None] | None = None,
) -> dict:
    notify = progress or (lambda _message: None)
    sources = load_municipality_sources(sources_path, periods)
    if fetch:
        notify(f"公式市区町村Excelを確認しています（{len(sources)}ファイル）")
        fetch_municipality_sources(sources, raw_dir)
    return load_municipality_source_records(sources, raw_dir, database_path, progress)
