"""Safe and repeatable downloader for official XLSX files."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from .estat_client import _verified_ssl_context
from .sources import Source


class FetchError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_xlsx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise FetchError(f"not a valid XLSX file: {path.name}") from exc
    required = {"[Content_Types].xml", "xl/workbook.xml"}
    if not required.issubset(names):
        raise FetchError(f"XLSX structure is incomplete: {path.name}")


def _read_manifest(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "files": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FetchError(f"invalid manifest: {path}") from exc
    if value.get("schema_version") != 1 or not isinstance(value.get("files"), list):
        raise FetchError(f"unsupported manifest: {path}")
    return value


def fetch_sources(sources: list[Source], raw_dir: Path, timeout: float = 60) -> list[dict]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "manifest.json"
    manifest = _read_manifest(manifest_path)
    entries = {(item["year"], item["release_type"]): item for item in manifest["files"]}
    results: list[dict] = []
    for source in sources:
        destination = raw_dir / source.filename
        previous = entries.get((source.year, source.release_type))
        if destination.exists() and previous:
            validate_xlsx(destination)
            digest = sha256_file(destination)
            if digest == previous.get("sha256") and source.url == previous.get("url"):
                previous.setdefault("period_start", f"{source.year}-01")
                previous.setdefault("period_end", f"{source.year}-12")
                previous["published_on"] = source.published_on
                results.append({**previous, "status": "skipped"})
                continue

        request = Request(source.url, headers={"User-Agent": "hotel-supply-demand-etl/0.1"})
        temp_name: str | None = None
        try:
            with urlopen(request, timeout=timeout, context=_verified_ssl_context()) as response:
                content_type = response.headers.get_content_type()
                if content_type not in {
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "application/octet-stream",
                }:
                    raise FetchError(f"unexpected content type for {source.year}: {content_type}")
                with tempfile.NamedTemporaryFile(dir=raw_dir, delete=False) as temp:
                    temp_name = temp.name
                    while chunk := response.read(1024 * 1024):
                        temp.write(chunk)
            temp_path = Path(temp_name)
            validate_xlsx(temp_path)
            digest = sha256_file(temp_path)
            duplicate = next((item for item in entries.values() if item.get("sha256") == digest), None)
            if duplicate and destination.exists():
                temp_path.unlink()
            else:
                os.replace(temp_path, destination)
            entry = {
                "year": source.year,
                "release_type": source.release_type,
                "url": source.url,
                "filename": source.filename,
                "period_start": f"{source.year}-01",
                "period_end": f"{source.year}-12",
                "published_on": source.published_on,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "sha256": digest,
                "size_bytes": destination.stat().st_size,
            }
            entries[(source.year, source.release_type)] = entry
            results.append({**entry, "status": "downloaded"})
        except Exception:
            if temp_name and Path(temp_name).exists():
                Path(temp_name).unlink()
            raise
    manifest["files"] = sorted(entries.values(), key=lambda item: item["year"])
    temp_manifest = manifest_path.with_suffix(".json.tmp")
    temp_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_manifest, manifest_path)
    return results
