"""Load and validate the fixed list of official Excel sources."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class SourceConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Source:
    year: int
    release_type: str
    url: str
    filename: str
    published_on: str


def load_sources(path: Path, years: set[int] | None = None) -> list[Source]:
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    result: list[Source] = []
    seen: set[tuple[int, str]] = set()
    for raw in document.get("sources", []):
        source = Source(
            year=int(raw["year"]),
            release_type=str(raw["release_type"]),
            url=str(raw["url"]),
            filename=str(raw["filename"]),
            published_on=str(raw["published_on"]),
        )
        key = (source.year, source.release_type)
        parsed = urlparse(source.url)
        if key in seen:
            raise SourceConfigurationError(f"duplicate source: {key}")
        trusted_mlit = parsed.netloc == "www.mlit.go.jp"
        query = parse_qs(parsed.query)
        trusted_estat = (
            parsed.netloc == "www.e-stat.go.jp"
            and parsed.path == "/stat-search/file-download"
            and len(query.get("statInfId", [])) == 1
            and query.get("fileKind") == ["0"]
        )
        if parsed.scheme != "https" or not (trusted_mlit or trusted_estat):
            raise SourceConfigurationError(f"untrusted source URL: {source.url}")
        if Path(source.filename).name != source.filename or not source.filename.endswith(".xlsx"):
            raise SourceConfigurationError(f"unsafe source filename: {source.filename}")
        try:
            date.fromisoformat(source.published_on)
        except ValueError as exc:
            raise SourceConfigurationError(
                f"invalid publication date for {source.year}: {source.published_on}"
            ) from exc
        seen.add(key)
        if years is None or source.year in years:
            result.append(source)
    if not result:
        raise SourceConfigurationError("no matching sources")
    return sorted(result, key=lambda item: item.year)
