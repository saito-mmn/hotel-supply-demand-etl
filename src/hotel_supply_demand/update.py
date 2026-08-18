"""Discover and safely apply official hotel-statistics updates."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

from .municipality.discovery import (
    discover_municipality_sources,
    source_page_from_config as municipality_source_page,
)
from .municipality.fetcher import fetch_municipality_sources
from .municipality.pipeline import load_municipality_source_records
from .municipality.report import generate_municipality_reports
from .municipality.sources import MunicipalitySource, load_municipality_sources
from .prefecture.analysis import load_analysis_config
from .prefecture.discovery import (
    AnnualFinalCandidate,
    discover_prefecture_sources,
    source_page_from_config as prefecture_source_page,
)
from .prefecture.fetcher import fetch_sources
from .prefecture.pipeline import build_prefecture_database
from .prefecture.report import generate_reports
from .prefecture.sources import Source, load_sources


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _write_municipality_config(
    path: Path, source_page: str, sources: list[MunicipalitySource]
) -> Path:
    temporary = path.with_suffix(path.suffix + ".update.tmp")
    lines = [f"source_page = {_quoted(source_page)}", ""]
    for source in sources:
        lines.extend(
            [
                "[[municipality_sources]]",
                f"year = {source.year}",
                f"month = {source.month}",
                f"release_type = {_quoted(source.release_type)}",
                f"stat_inf_id = {_quoted(source.stat_inf_id)}",
                f"published_on = {_quoted(source.published_on)}",
                f"url = {_quoted(source.url)}",
                f"filename = {_quoted(source.filename)}",
            ]
        )
        if source.provider != "estat":
            lines.append(f"provider = {_quoted(source.provider)}")
        lines.append("")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    return temporary


def _write_prefecture_config(path: Path, source_page: str, sources: list[Source]) -> Path:
    temporary = path.with_suffix(path.suffix + ".update.tmp")
    lines = [f"source_page = {_quoted(source_page)}", ""]
    for source in sources:
        lines.extend(
            [
                "[[sources]]",
                f"year = {source.year}",
                f"release_type = {_quoted(source.release_type)}",
                f"url = {_quoted(source.url)}",
                f"filename = {_quoted(source.filename)}",
                f"published_on = {_quoted(source.published_on)}",
                "",
            ]
        )
    temporary.write_text("\n".join(lines), encoding="utf-8")
    return temporary


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _promote(staged_paths: list[tuple[Path, Path]]) -> None:
    """Replace related files/directories and restore all originals on failure."""
    promoted: list[tuple[Path, Path | None]] = []
    try:
        for staged, destination in staged_paths:
            destination.parent.mkdir(parents=True, exist_ok=True)
            backup = None
            if destination.exists():
                backup = destination.parent / f".{destination.name}.backup-{uuid.uuid4().hex}"
                os.replace(destination, backup)
            try:
                os.replace(staged, destination)
            except Exception:
                if backup:
                    os.replace(backup, destination)
                raise
            promoted.append((destination, backup))
    except Exception:
        for destination, backup in reversed(promoted):
            _remove_path(destination)
            if backup:
                os.replace(backup, destination)
        raise
    for _destination, backup in promoted:
        if backup:
            _remove_path(backup)


def _merge_municipality_sources(
    configured: list[MunicipalitySource], discovered: list[MunicipalitySource]
) -> tuple[list[MunicipalitySource], list[dict], list[dict]]:
    merged = {(source.year, source.month): source for source in configured}
    minimum_period = min(merged)
    changes: list[dict] = []
    approvals: list[dict] = []
    for source in discovered:
        key = (source.year, source.month)
        if key < minimum_period:
            continue
        previous = merged.get(key)
        if previous is None:
            merged[key] = source
            changes.append({"period": f"{source.year}-{source.month:02d}", "kind": "new"})
        elif previous.provider != "estat" and previous.stat_inf_id != source.stat_inf_id:
            approvals.append(
                {
                    "period": f"{source.year}-{source.month:02d}",
                    "kind": "exception_conflict",
                    "configured": previous.stat_inf_id,
                    "discovered": source.stat_inf_id,
                }
            )
        elif (
            previous.stat_inf_id != source.stat_inf_id
            or previous.url != source.url
            or previous.published_on != source.published_on
        ):
            merged[key] = source
            changes.append({"period": f"{source.year}-{source.month:02d}", "kind": "revised"})
    return (
        sorted(merged.values(), key=lambda item: (item.year, item.month)),
        changes,
        approvals,
    )


def _merge_prefecture_sources(
    configured: list[Source], candidates: list[AnnualFinalCandidate]
) -> tuple[list[Source], list[dict], list[dict]]:
    merged = {source.year: source for source in configured}
    changes: list[dict] = []
    configuration_required: list[dict] = []
    for candidate in candidates:
        previous = merged.get(candidate.year)
        if previous is None:
            if candidate.year > min(merged):
                configuration_required.append(
                    {
                        "year": candidate.year,
                        "url": candidate.url,
                        "reason": "published_on cannot be inferred safely",
                    }
                )
        elif previous.url != candidate.url:
            merged[candidate.year] = Source(
                year=previous.year,
                release_type=previous.release_type,
                url=candidate.url,
                filename=previous.filename,
                published_on=previous.published_on,
            )
            changes.append({"year": candidate.year, "kind": "url_changed"})
    return (
        sorted(merged.values(), key=lambda item: item.year),
        changes,
        configuration_required,
    )


def discover_updates(prefecture_sources: Path, municipality_sources: Path) -> dict:
    configured_prefecture = load_sources(prefecture_sources)
    configured_municipality = load_municipality_sources(municipality_sources)
    prefecture_page = prefecture_source_page(prefecture_sources)
    municipality_page = municipality_source_page(municipality_sources)
    prefecture_discovered = discover_prefecture_sources(prefecture_page)
    municipality_discovered = discover_municipality_sources(municipality_page)
    _, prefecture_changes, configuration_required = _merge_prefecture_sources(
        configured_prefecture, prefecture_discovered
    )
    _, municipality_changes, approvals = _merge_municipality_sources(
        configured_municipality, municipality_discovered
    )
    return {
        "prefecture": {
            "official_sources": len(prefecture_discovered),
            "detected": prefecture_changes,
            "configuration_required": configuration_required,
        },
        "municipality": {
            "official_sources": len(municipality_discovered),
            "detected": municipality_changes,
            "approval_required": approvals,
        },
    }


def update_municipality(
    sources_path: Path,
    raw_dir: Path,
    database: Path,
    report_dir: Path,
    *,
    base_year: int = 2019,
    periods: set[tuple[int, int]] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    notify = progress or (lambda _message: None)
    configured = load_municipality_sources(sources_path)
    source_page = municipality_source_page(sources_path)
    discovered = discover_municipality_sources(source_page)
    merged, detected, approvals = _merge_municipality_sources(configured, discovered)
    selected = [
        source
        for source in merged
        if periods is None or (source.year, source.month) in periods
    ]
    if periods:
        available = {(source.year, source.month) for source in selected}
        missing = periods - available
        if missing:
            labels = ", ".join(f"{year}-{month:02d}" for year, month in sorted(missing))
            raise ValueError(f"municipality periods not found: {labels}")
    notify(
        f"市区町村原Excelの更新を確認しています（{len(selected)}ファイル）"
    )
    fetched = fetch_municipality_sources(selected, raw_dir, check_remote=True)
    changed_keys = {
        (int(item["year"]), int(item["month"]))
        for item in fetched
        if item["status"] == "downloaded"
    }
    for item in detected:
        year_text, month_text = item["period"].split("-", 1)
        changed_keys.add((int(year_text), int(month_text)))
    if periods:
        changed_keys.update(periods)
    changed_sources = [
        source for source in selected if (source.year, source.month) in changed_keys
    ]
    if not changed_sources:
        return {
            "updated": False,
            "checked": len(selected),
            "detected": detected,
            "approval_required": approvals,
        }

    database.parent.mkdir(parents=True, exist_ok=True)
    report_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="hotel-municipality-update-", dir=database.parent
    ) as temporary:
        staging = Path(temporary)
        staged_database = staging / database.name
        if database.exists():
            shutil.copy2(database, staged_database)
        load_result = load_municipality_source_records(
            changed_sources, raw_dir, staged_database, progress
        )
        staged_report = staging / "municipality-report"
        report_result = generate_municipality_reports(
            staged_database, staged_report, base_year=base_year
        )
        staged_sources = _write_municipality_config(
            staging / sources_path.name, source_page, merged
        )
        _promote(
            [
                (staged_database, database),
                (staged_report, report_dir),
                (staged_sources, sources_path),
            ]
        )
    return {
        "updated": True,
        "changed_periods": sorted(
            f"{year}-{month:02d}" for year, month in changed_keys
        ),
        "load": load_result,
        "report": report_result,
        "approval_required": approvals,
    }


def update_prefecture(
    sources_path: Path,
    raw_dir: Path,
    database: Path,
    report_dir: Path,
    analysis_config: Path,
    *,
    years: set[int] | None = None,
    target_year: int | None = None,
    base_year: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    notify = progress or (lambda _message: None)
    configured = load_sources(sources_path)
    source_page = prefecture_source_page(sources_path)
    candidates = discover_prefecture_sources(source_page)
    merged, detected, configuration_required = _merge_prefecture_sources(
        configured, candidates
    )
    selected = [source for source in merged if years is None or source.year in years]
    if years:
        missing = years - {source.year for source in selected}
        if missing:
            labels = ", ".join(str(year) for year in sorted(missing))
            raise ValueError(f"prefecture years not found: {labels}")
    file_count = len(selected)
    notify(
        "都道府県確定値Excelの更新を確認しています"
        f"（{file_count}ファイル）"
    )
    fetched = fetch_sources(selected, raw_dir, check_remote=True)
    changed_years = {
        int(item["year"])
        for item in fetched
        if item["status"] == "downloaded"
    }
    if years:
        changed_years.update(years)
    if not changed_years:
        return {
            "updated": False,
            "checked": len(selected),
            "detected": detected,
            "configuration_required": configuration_required,
        }

    database.parent.mkdir(parents=True, exist_ok=True)
    report_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="hotel-prefecture-update-", dir=database.parent
    ) as temporary:
        staging = Path(temporary)
        staged_database = staging / database.name
        build_result = build_prefecture_database(
            merged, raw_dir, staged_database, progress
        )
        staged_report = staging / "reports"
        municipality_reports = report_dir / "municipalities"
        if municipality_reports.exists():
            shutil.copytree(municipality_reports, staged_report / "municipalities")
        effective_target_year = target_year or max(source.year for source in merged)
        config = load_analysis_config(
            analysis_config,
            target_year=effective_target_year,
            base_year=base_year,
        )
        report_result = generate_reports(staged_database, staged_report, config)
        staged_sources = _write_prefecture_config(
            staging / sources_path.name, source_page, merged
        )
        _promote(
            [
                (staged_database, database),
                (staged_report, report_dir),
                (staged_sources, sources_path),
            ]
        )
    return {
        "updated": True,
        "changed_years": sorted(changed_years),
        "build": build_result,
        "report": report_result,
        "configuration_required": configuration_required,
    }
