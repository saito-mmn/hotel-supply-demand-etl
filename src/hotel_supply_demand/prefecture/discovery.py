"""Discover annual-final XLSX files from the official e-Stat dataset page."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from ..estat_client import _verified_ssl_context
from .sources import SourceConfigurationError


ANNUAL_FINAL_TSTAT = "000001079598"
ANNUAL_FINAL_SOURCE_PAGE = (
    "https://www.e-stat.go.jp/stat-search/files?"
    + urlencode({"layout": "dataset", "tstat": ANNUAL_FINAL_TSTAT})
)
_LEGACY_MLIT_SOURCE_PAGE = (
    "https://www.mlit.go.jp/kankocho/tokei_hakusyo/shukuhakutokei.html"
)
_ARTICLE = re.compile(
    r'<article\b[^>]*class="[^"]*stat-resource_list-item[^>]*>(.*?)</article>',
    re.DOTALL,
)
_YEAR = re.compile(r"調査年月\s*(20\d{2})年")
_PUBLISHED = re.compile(r"公開（更新）日\s*(20\d{2}-\d{2}-\d{2})")
_DOWNLOAD = re.compile(
    r'href="([^"]*/stat-search/file-download\?[^"#]*\bfileKind=0(?:&[^"#]*)?)"'
)


@dataclass(frozen=True)
class AnnualFinalCandidate:
    year: int
    published_on: str
    stat_inf_id: str
    url: str


def _is_annual_final_page(value: str) -> bool:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.e-stat.go.jp"
        or parsed.path != "/stat-search/files"
    ):
        return False
    query = parse_qs(parsed.query)
    return query.get("tstat") == [ANNUAL_FINAL_TSTAT] or (
        query.get("toukei") == ["00601020"] and query.get("cycle") == ["7"]
    )


def source_page_from_config(path: Path) -> str:
    import tomllib

    with path.open("rb") as handle:
        value = str(tomllib.load(handle).get("source_page", ""))
    if _is_annual_final_page(value):
        return value
    # Existing Actions caches can still contain the former MLIT discovery page.
    # Migrate it to the canonical e-Stat annual-final listing on the next update.
    if value == _LEGACY_MLIT_SOURCE_PAGE:
        return ANNUAL_FINAL_SOURCE_PAGE
    raise SourceConfigurationError(f"untrusted prefecture source page: {value}")


def parse_source_page(document: str) -> list[AnnualFinalCandidate]:
    """Extract only original-Excel links from annual-final dataset rows."""
    discovered: dict[int, AnnualFinalCandidate] = {}
    for article in _ARTICLE.findall(document):
        text = html.unescape(re.sub(r"<[^>]+>", " ", article))
        text = " ".join(text.split())
        if "宿泊旅行統計調査（年確定値）" not in text:
            continue
        year_match = _YEAR.search(text)
        published_match = _PUBLISHED.search(text)
        download_match = _DOWNLOAD.search(html.unescape(article))
        if not (year_match and published_match and download_match):
            continue
        relative_url = html.unescape(download_match.group(1))
        query = parse_qs(urlparse(relative_url).query)
        stat_inf_ids = query.get("statInfId", [])
        if len(stat_inf_ids) != 1 or not re.fullmatch(r"\d{12}", stat_inf_ids[0]):
            continue
        year = int(year_match.group(1))
        stat_inf_id = stat_inf_ids[0]
        candidate = AnnualFinalCandidate(
            year=year,
            published_on=published_match.group(1),
            stat_inf_id=stat_inf_id,
            url=(
                "https://www.e-stat.go.jp/stat-search/file-download?"
                + urlencode({"statInfId": stat_inf_id, "fileKind": "0"})
            ),
        )
        previous = discovered.get(year)
        if previous and previous.stat_inf_id != candidate.stat_inf_id:
            raise SourceConfigurationError(f"conflicting annual-final sources for {year}")
        discovered[year] = candidate
    return sorted(discovered.values(), key=lambda item: item.year)


def discover_prefecture_sources(
    source_page: str, *, timeout: float = 60, max_pages: int = 10
) -> list[AnnualFinalCandidate]:
    if not _is_annual_final_page(source_page):
        raise SourceConfigurationError(f"untrusted prefecture source page: {source_page}")
    parsed_page = urlparse(source_page)
    base_query = parse_qs(parsed_page.query)
    discovered: dict[int, AnnualFinalCandidate] = {}
    for page in range(1, max_pages + 1):
        query = {key: values[-1] for key, values in base_query.items()}
        query["page"] = str(page)
        url = urlunparse(parsed_page._replace(query=urlencode(query)))
        request = Request(url, headers={"User-Agent": "hotel-supply-demand-etl/0.1"})
        with urlopen(
            request, timeout=timeout, context=_verified_ssl_context()
        ) as response:
            page_candidates = parse_source_page(response.read().decode("utf-8"))
        if not page_candidates:
            break
        for candidate in page_candidates:
            previous = discovered.get(candidate.year)
            if previous and previous.stat_inf_id != candidate.stat_inf_id:
                raise SourceConfigurationError(
                    f"conflicting annual-final sources for {candidate.year}"
                )
            discovered[candidate.year] = candidate
        if len(page_candidates) < 50:
            break
    if not discovered:
        raise SourceConfigurationError("no annual-final original Excel links found on e-Stat")
    return sorted(discovered.values(), key=lambda item: item.year)
