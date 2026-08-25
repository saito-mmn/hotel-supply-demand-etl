"""Discover second-preliminary municipality XLSX files from the official e-Stat page."""

from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from ..estat_client import _verified_ssl_context
from .sources import MunicipalitySource, MunicipalitySourceConfigurationError


_ARTICLE = re.compile(
    r'<article\b[^>]*class="[^"]*stat-resource_list-item[^>]*>(.*?)</article>', re.S
)
_PERIOD = re.compile(r"(20\d{2})年\s*(1[0-2]|[1-9])月")
_PUBLISHED = re.compile(r"(20\d{2}-\d{2}-\d{2})")
_DOWNLOAD = re.compile(
    r'href="([^"]*/stat-search/file-download\?[^"#]*\bfileKind=0(?:&[^"#]*)?)"'
)


def source_page_from_config(path: Path) -> str:
    import tomllib

    with path.open("rb") as handle:
        value = str(tomllib.load(handle).get("source_page", ""))
    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.e-stat.go.jp"
        or parsed.path != "/stat-search/files"
        or query.get("tstat") != ["000001079597"]
    ):
        raise MunicipalitySourceConfigurationError(
            f"untrusted municipality source page: {value}"
        )
    return value


def parse_source_page(document: str) -> list[MunicipalitySource]:
    """Extract only original-Excel links from second-preliminary dataset rows."""
    discovered: dict[tuple[int, int], MunicipalitySource] = {}
    for article in _ARTICLE.findall(document):
        text = html.unescape(re.sub(r"<[^>]+>", " ", article))
        text = " ".join(text.split())
        if "宿泊旅行統計調査（第2次速報値）" not in text:
            continue
        period = _PERIOD.search(text)
        published = _PUBLISHED.search(text)
        download = _DOWNLOAD.search(html.unescape(article))
        if not (period and published and download):
            continue
        year, month = int(period.group(1)), int(period.group(2))
        relative_url = html.unescape(download.group(1))
        parsed = urlparse(relative_url)
        query = parse_qs(parsed.query)
        stat_inf_ids = query.get("statInfId", [])
        if len(stat_inf_ids) != 1 or not re.fullmatch(r"\d{12}", stat_inf_ids[0]):
            continue
        stat_inf_id = stat_inf_ids[0]
        source = MunicipalitySource(
            year=year,
            month=month,
            release_type="second_preliminary",
            stat_inf_id=stat_inf_id,
            published_on=published.group(1),
            url=(
                "https://www.e-stat.go.jp/stat-search/file-download?"
                + urlencode({"statInfId": stat_inf_id, "fileKind": "0"})
            ),
            filename=f"{year}-{month:02d}_second_preliminary.xlsx",
            provider="estat",
        )
        key = (year, month)
        previous = discovered.get(key)
        if previous and previous.stat_inf_id != source.stat_inf_id:
            raise MunicipalitySourceConfigurationError(
                f"conflicting e-Stat sources for {year}-{month:02d}"
            )
        discovered[key] = source
    return sorted(discovered.values(), key=lambda item: (item.year, item.month))


def discover_municipality_sources(
    source_page: str, *, timeout: float = 60, max_pages: int = 10
) -> list[MunicipalitySource]:
    """Read all result pages and return the unique official original-Excel sources."""
    parsed_page = urlparse(source_page)
    base_query = parse_qs(parsed_page.query)
    if (
        parsed_page.scheme != "https"
        or parsed_page.netloc != "www.e-stat.go.jp"
        or parsed_page.path != "/stat-search/files"
        or base_query.get("tstat") != ["000001079597"]
    ):
        raise MunicipalitySourceConfigurationError(
            f"untrusted municipality source page: {source_page}"
        )
    discovered: dict[tuple[int, int], MunicipalitySource] = {}
    for page in range(1, max_pages + 1):
        query = {key: values[-1] for key, values in base_query.items()}
        query["page"] = str(page)
        url = urlunparse(parsed_page._replace(query=urlencode(query)))
        request = Request(url, headers={"User-Agent": "hotel-supply-demand-etl/0.1"})
        with urlopen(
            request, timeout=timeout, context=_verified_ssl_context()
        ) as response:
            page_sources = parse_source_page(response.read().decode("utf-8"))
        if not page_sources:
            break
        for source in page_sources:
            key = (source.year, source.month)
            previous = discovered.get(key)
            if previous and previous.stat_inf_id != source.stat_inf_id:
                raise MunicipalitySourceConfigurationError(
                    f"conflicting e-Stat sources for {source.year}-{source.month:02d}"
                )
            discovered[key] = source
        if len(page_sources) < 50:
            break
    if not discovered:
        raise MunicipalitySourceConfigurationError(
            "no second-preliminary original Excel links found on e-Stat"
        )
    return sorted(discovered.values(), key=lambda item: (item.year, item.month))
