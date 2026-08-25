"""Load fixed e-Stat Excel sources for municipality-level monthly statistics."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class MunicipalitySourceConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class MunicipalitySource:
    year: int
    month: int
    release_type: str
    stat_inf_id: str
    published_on: str
    url: str
    filename: str
    provider: str = "estat"


def load_municipality_sources(
    path: Path, periods: set[tuple[int, int]] | None = None
) -> list[MunicipalitySource]:
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    result: list[MunicipalitySource] = []
    seen: set[tuple[int, int, str]] = set()
    for raw in document.get("municipality_sources", []):
        source = MunicipalitySource(
            year=int(raw["year"]),
            month=int(raw["month"]),
            release_type=str(raw["release_type"]),
            stat_inf_id=str(raw["stat_inf_id"]),
            published_on=str(raw["published_on"]),
            url=str(raw["url"]),
            filename=str(raw["filename"]),
            provider=str(raw.get("provider", "estat")),
        )
        key = (source.year, source.month, source.release_type)
        parsed = urlparse(source.url)
        query = parse_qs(parsed.query)
        if key in seen:
            raise MunicipalitySourceConfigurationError(f"duplicate municipality source: {key}")
        if not 1 <= source.month <= 12:
            raise MunicipalitySourceConfigurationError(f"invalid month: {source.month}")
        if source.release_type != "second_preliminary":
            raise MunicipalitySourceConfigurationError(
                f"unsupported municipality release type: {source.release_type}"
            )
        estat_url = (
            source.provider == "estat"
            and re.fullmatch(r"\d{12}", source.stat_inf_id)
            and parsed.scheme == "https"
            and parsed.netloc == "www.e-stat.go.jp"
            and parsed.path == "/stat-search/file-download"
            and query.get("statInfId") == [source.stat_inf_id]
            and query.get("fileKind") == ["0"]
        )
        mlit_url = (
            source.provider == "mlit"
            and re.fullmatch(r"mlit:\d{9}", source.stat_inf_id)
            and parsed.scheme == "https"
            and parsed.netloc == "www.mlit.go.jp"
            and parsed.path
            == f'/kankocho/content/{source.stat_inf_id.split(":", 1)[1]}.xlsx'
            and not query
        )
        if not (estat_url or mlit_url):
            raise MunicipalitySourceConfigurationError(
                f"untrusted municipality source URL: {source.url}"
            )
        try:
            date.fromisoformat(source.published_on)
        except ValueError as exc:
            raise MunicipalitySourceConfigurationError(
                f"invalid publication date: {source.published_on}"
            ) from exc
        expected_filename = f"{source.year}-{source.month:02d}_second_preliminary.xlsx"
        if source.filename != expected_filename:
            raise MunicipalitySourceConfigurationError(
                f"unexpected municipality filename: {source.filename}"
            )
        seen.add(key)
        if periods is None or (source.year, source.month) in periods:
            result.append(source)
    if not result:
        raise MunicipalitySourceConfigurationError("no matching municipality sources")
    return sorted(result, key=lambda item: (item.year, item.month))
