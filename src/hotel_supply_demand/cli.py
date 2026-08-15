"""Command-line interface for the Excel pipeline and e-Stat audit."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Sequence

from .config import ConfigurationError, get_estat_app_id
from .analysis import AnalysisError, load_analysis_config
from .estat_client import EstatApiError, EstatClient
from .fetcher import FetchError, fetch_sources
from .parser import WorkbookFormatError
from .pipeline import run_pipeline
from .report import generate_reports
from .sources import SourceConfigurationError, load_sources
from .validation import DataQualityError
from .municipality.fetcher import fetch_municipality_sources
from .municipality.parser import MunicipalityWorkbookFormatError
from .municipality.pipeline import run_municipality_pipeline
from .municipality.report import generate_municipality_reports
from .municipality.sources import (
    MunicipalitySourceConfigurationError,
    load_municipality_sources,
)
from .municipality.validation import MunicipalityDataQualityError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hotel-etl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search-tables", help="Search e-Stat statistical tables")
    search.add_argument("--query", default="宿泊旅行統計調査")
    search.add_argument("--stats-code")
    search.add_argument("--survey-years")
    search.add_argument("--limit", type=int, default=20)

    metadata = subparsers.add_parser("show-metadata", help="Show table dimensions")
    metadata.add_argument("--stats-data-id", required=True)

    sample = subparsers.add_parser("fetch-sample", help="Fetch a small unfiltered sample")
    sample.add_argument("--stats-data-id", required=True)
    sample.add_argument("--limit", type=int, default=10)

    fetch = subparsers.add_parser("fetch", help="Download configured official Excel files")
    _add_pipeline_paths(fetch, include_database=False)

    build = subparsers.add_parser("build-db", help="Build SQLite from previously downloaded files")
    _add_pipeline_paths(build)

    pipeline = subparsers.add_parser("pipeline", help="Download, build SQLite, and generate reports")
    _add_pipeline_paths(pipeline)
    _add_report_options(pipeline, allow_skip=True)

    monitor = subparsers.add_parser("monitor", help="Generate national and prefecture market reports")
    monitor.add_argument("--database", type=Path, default=Path("data/processed/hotel_market.sqlite3"))
    _add_report_options(monitor)

    municipality_fetch = subparsers.add_parser(
        "municipality-fetch", help="Download configured municipality second-preliminary Excel files"
    )
    _add_municipality_paths(municipality_fetch, include_database=False)

    municipality_build = subparsers.add_parser(
        "municipality-build-db",
        help="Load downloaded municipality Excel files into SQLite",
    )
    _add_municipality_paths(municipality_build)

    municipality_pipeline = subparsers.add_parser(
        "municipality-pipeline",
        help="Download, validate, and load municipality monthly statistics",
    )
    _add_municipality_paths(municipality_pipeline)
    municipality_pipeline.add_argument(
        "--report-dir", type=Path, default=Path("reports/latest/municipalities")
    )
    municipality_pipeline.add_argument("--skip-report", action="store_true")

    municipality_report = subparsers.add_parser(
        "municipality-report", help="Generate municipality market reports from SQLite"
    )
    municipality_report.add_argument(
        "--database", type=Path, default=Path("data/processed/hotel_market.sqlite3")
    )
    municipality_report.add_argument(
        "--report-dir", type=Path, default=Path("reports/latest/municipalities")
    )

    return parser


def _add_pipeline_paths(parser: argparse.ArgumentParser, include_database: bool = True) -> None:
    parser.add_argument("--sources", type=Path, default=Path("sources.toml"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--years", type=int, nargs="+")
    if include_database:
        parser.add_argument("--database", type=Path, default=Path("data/processed/hotel_market.sqlite3"))


def _add_report_options(parser: argparse.ArgumentParser, allow_skip: bool = False) -> None:
    parser.add_argument("--analysis-config", type=Path, default=Path("analysis.toml"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports/latest"))
    parser.add_argument("--target-year", type=int)
    parser.add_argument("--base-year", type=int)
    if allow_skip:
        parser.add_argument("--skip-report", action="store_true")


def _add_municipality_paths(
    parser: argparse.ArgumentParser, include_database: bool = True
) -> None:
    parser.add_argument(
        "--sources", type=Path, default=Path("municipality_sources.toml")
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/municipality"))
    parser.add_argument("--periods", nargs="+", metavar="YYYY-MM")
    if include_database:
        parser.add_argument(
            "--database", type=Path, default=Path("data/processed/hotel_market.sqlite3")
        )


def _municipality_periods(values: list[str] | None) -> set[tuple[int, int]] | None:
    if not values:
        return None
    periods = set()
    for value in values:
        try:
            year_text, month_text = value.split("-", 1)
            year, month = int(year_text), int(month_text)
        except ValueError as exc:
            raise ValueError(f"invalid municipality period: {value}") from exc
        if len(year_text) != 4 or not 1 <= month <= 12:
            raise ValueError(f"invalid municipality period: {value}")
        periods.add((year, month))
    return periods


def _table_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload["GET_STATS_LIST"].get("DATALIST_INF", {})
    tables = data.get("TABLE_INF", [])
    if isinstance(tables, dict):
        tables = [tables]
    return [
        {
            "stats_data_id": table.get("@id"),
            "stat_name": table.get("STAT_NAME"),
            "title": table.get("TITLE"),
            "survey_date": table.get("SURVEY_DATE"),
            "open_date": table.get("OPEN_DATE"),
            "updated_date": table.get("UPDATED_DATE"),
        }
        for table in tables
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "fetch":
            result = fetch_sources(load_sources(args.sources, set(args.years) if args.years else None), args.raw_dir)
        elif args.command in {"build-db", "pipeline"}:
            result = run_pipeline(
                args.sources,
                args.raw_dir,
                args.database,
                set(args.years) if args.years else None,
                fetch=args.command == "pipeline",
                progress=lambda message: print(f"[hotel-etl] {message}", file=sys.stderr),
            )
            if args.command == "pipeline" and not args.skip_report:
                print("[hotel-etl] 分析レポートを生成しています", file=sys.stderr)
                config = load_analysis_config(args.analysis_config, target_year=args.target_year, base_year=args.base_year)
                result["analysis"] = generate_reports(args.database, args.report_dir, config)
        elif args.command == "monitor":
            config = load_analysis_config(args.analysis_config, target_year=args.target_year, base_year=args.base_year)
            result = generate_reports(args.database, args.report_dir, config)
        elif args.command == "municipality-fetch":
            periods = _municipality_periods(args.periods)
            result = fetch_municipality_sources(
                load_municipality_sources(args.sources, periods), args.raw_dir
            )
        elif args.command in {"municipality-build-db", "municipality-pipeline"}:
            result = run_municipality_pipeline(
                args.sources,
                args.raw_dir,
                args.database,
                _municipality_periods(args.periods),
                fetch=args.command == "municipality-pipeline",
                progress=lambda message: print(f"[hotel-etl] {message}", file=sys.stderr),
            )
            if args.command == "municipality-pipeline" and not args.skip_report:
                print("[hotel-etl] 市区町村レポートを生成しています", file=sys.stderr)
                result["analysis"] = generate_municipality_reports(
                    args.database, args.report_dir
                )
        elif args.command == "municipality-report":
            result = generate_municipality_reports(args.database, args.report_dir)
        else:
            client = EstatClient(app_id=get_estat_app_id())
            if args.command == "search-tables":
                result = _table_summaries(
                    client.get_stats_list(
                        search_word=args.query,
                        stats_code=args.stats_code,
                        survey_years=args.survey_years,
                        limit=args.limit,
                    )
                )
            elif args.command == "show-metadata":
                result = client.get_meta_info(stats_data_id=args.stats_data_id)
            else:
                result = client.get_stats_data(
                    stats_data_id=args.stats_data_id,
                    limit=args.limit,
                )
    except (
        ConfigurationError,
        EstatApiError,
        FetchError,
        SourceConfigurationError,
        MunicipalitySourceConfigurationError,
        WorkbookFormatError,
        MunicipalityWorkbookFormatError,
        DataQualityError,
        MunicipalityDataQualityError,
        AnalysisError,
        OSError,
        KeyError,
        ValueError,
        sqlite3.Error,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
