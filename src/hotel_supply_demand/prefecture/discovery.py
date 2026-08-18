"""Discover annual-final XLSX links from the Japan Tourism Agency page."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from ..estat_client import _verified_ssl_context
from .sources import SourceConfigurationError


@dataclass(frozen=True)
class AnnualFinalCandidate:
    year: int
    url: str


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._text: list[str] = []
        self.anchors: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.anchors.append((self._href, " ".join("".join(self._text).split())))
            self._href = None
            self._text = []


def source_page_from_config(path: Path) -> str:
    import tomllib

    with path.open("rb") as handle:
        value = str(tomllib.load(handle).get("source_page", ""))
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.mlit.go.jp"
        or parsed.path != "/kankocho/tokei_hakusyo/shukuhakutokei.html"
    ):
        raise SourceConfigurationError(f"untrusted prefecture source page: {value}")
    return value


def parse_source_page(document: str, source_page: str) -> list[AnnualFinalCandidate]:
    parser = _AnchorParser()
    parser.feed(document)
    discovered: dict[int, AnnualFinalCandidate] = {}
    for href, text in parser.anchors:
        match = re.search(r"(20\d{2})年.*年の確定値.*集計結果", text)
        if not match or not href.lower().endswith(".xlsx"):
            continue
        url = urljoin(source_page, href)
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "www.mlit.go.jp":
            continue
        year = int(match.group(1))
        candidate = AnnualFinalCandidate(year=year, url=url)
        previous = discovered.get(year)
        if previous and previous.url != candidate.url:
            raise SourceConfigurationError(f"conflicting annual-final links for {year}")
        discovered[year] = candidate
    if not discovered:
        raise SourceConfigurationError("no annual-final Excel links found")
    return sorted(discovered.values(), key=lambda item: item.year)


def discover_prefecture_sources(
    source_page: str, *, timeout: float = 60
) -> list[AnnualFinalCandidate]:
    parsed = urlparse(source_page)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.mlit.go.jp"
        or parsed.path != "/kankocho/tokei_hakusyo/shukuhakutokei.html"
    ):
        raise SourceConfigurationError(f"untrusted prefecture source page: {source_page}")
    request = Request(source_page, headers={"User-Agent": "hotel-supply-demand-etl/0.1"})
    with urlopen(
        request, timeout=timeout, context=_verified_ssl_context()
    ) as response:
        return parse_source_page(response.read().decode("utf-8"), source_page)
