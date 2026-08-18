"""Validate and stage the generated static reports for GitHub Pages."""

from __future__ import annotations

import argparse
import json
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


PUBLIC_SUFFIXES = {
    ".css",
    ".html",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".png",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
}
PUBLIC_ROOT_FILES = {"index.html"}
PUBLIC_DIRECTORIES = {"market-sheets", "municipalities"}
SENSITIVE_MARKERS = ("/Users/", "/home/", "ESTAT_APP_ID", "appId=")


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        attribute = "href" if tag in {"a", "link"} else "src" if tag == "script" else None
        if attribute and attributes.get(attribute):
            self.links.append(attributes[attribute] or "")


def _metadata_count(path: Path, field: str) -> int:
    if not path.is_file():
        raise ValueError(f"metadata not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8")).get(field)
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"metadata field must be a positive integer: {path}:{field}")
    return value


def _validate_source(source: Path) -> tuple[int, int]:
    required = (source / "index.html", source / "municipalities" / "index.html")
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"required report missing: {', '.join(missing)}")

    prefectures = _metadata_count(source / "report-metadata.json", "rows")
    municipalities = _metadata_count(
        source / "municipalities" / "report-metadata.json", "municipalities"
    )
    actual_prefectures = len(list((source / "market-sheets").glob("*.html")))
    actual_municipalities = len(
        list((source / "municipalities" / "market-sheets").glob("*.html"))
    )
    if actual_prefectures != prefectures:
        raise ValueError(
            f"prefecture sheet count mismatch: metadata={prefectures}, actual={actual_prefectures}"
        )
    if actual_municipalities != municipalities:
        raise ValueError(
            "municipality sheet count mismatch: "
            f"metadata={municipalities}, actual={actual_municipalities}"
        )
    return prefectures, municipalities


def _copy_public_files(source: Path, output: Path) -> int:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    copied = 0
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symbolic links are not allowed in the Pages artifact: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        is_public_root_file = relative.as_posix() in PUBLIC_ROOT_FILES
        if relative.parts[0] not in PUBLIC_DIRECTORIES and not is_public_root_file:
            continue
        if path.suffix.lower() not in PUBLIC_SUFFIXES:
            continue
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        copied += 1
    return copied


def _validate_public_files(output: Path) -> None:
    root = output.resolve()
    errors: list[str] = []
    for path in output.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in PUBLIC_SUFFIXES:
            errors.append(f"unsupported public file: {path.relative_to(output)}")
            continue
        if path.suffix.lower() not in {".html", ".css", ".js", ".svg"}:
            continue
        text = path.read_text(encoding="utf-8")
        for marker in SENSITIVE_MARKERS:
            if marker in text:
                errors.append(f"sensitive marker {marker!r}: {path.relative_to(output)}")
        if path.suffix.lower() != ".html":
            continue
        parser = LinkCollector()
        parser.feed(text)
        for link in parser.links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (path.parent / unquote(parsed.path)).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                errors.append(f"link escapes site root: {path.relative_to(output)} -> {link}")
                continue
            if target.is_dir():
                target /= "index.html"
            if not target.is_file():
                errors.append(f"broken link: {path.relative_to(output)} -> {link}")
    if errors:
        preview = "\n".join(f"- {error}" for error in errors[:20])
        remainder = f"\n- ... and {len(errors) - 20} more" if len(errors) > 20 else ""
        raise ValueError(f"static site validation failed:\n{preview}{remainder}")


def prepare_pages(source: Path, output: Path) -> tuple[int, int, int]:
    source = source.resolve()
    output = output.resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("source and output directories must be independent")
    prefectures, municipalities = _validate_source(source)
    copied = _copy_public_files(source, output)
    _validate_public_files(output)
    return copied, prefectures, municipalities


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("reports/latest"))
    parser.add_argument("--output", type=Path, default=Path(".pages"))
    args = parser.parse_args()

    copied, prefectures, municipalities = prepare_pages(args.source, args.output)
    print(
        f"Pages artifact ready: {copied} files, "
        f"{prefectures} prefectures, {municipalities} municipalities"
    )


if __name__ == "__main__":
    main()
