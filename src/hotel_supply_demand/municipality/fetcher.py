"""Repeatable downloader and manifest writer for municipality e-Stat XLSX files."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from ..estat_client import _verified_ssl_context
from ..fetcher import FetchError, sha256_file, validate_xlsx
from .sources import MunicipalitySource


def _read_manifest(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "files": []}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FetchError(f"invalid municipality manifest: {path}") from exc
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), list):
        raise FetchError(f"unsupported municipality manifest: {path}")
    return manifest


def fetch_municipality_sources(
    sources: list[MunicipalitySource], raw_dir: Path, timeout: float = 60
) -> list[dict]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "manifest.json"
    manifest = _read_manifest(manifest_path)
    entries = {
        (int(item["year"]), int(item["month"]), str(item["release_type"])): item
        for item in manifest["files"]
    }
    results: list[dict] = []
    for source in sources:
        key = (source.year, source.month, source.release_type)
        destination = raw_dir / source.filename
        previous = entries.get(key)
        if destination.exists() and previous:
            validate_xlsx(destination)
            digest = sha256_file(destination)
            if (
                digest == previous.get("sha256")
                and source.url == previous.get("url")
                and source.stat_inf_id == previous.get("stat_inf_id")
            ):
                previous["published_on"] = source.published_on
                previous["provider"] = source.provider
                results.append({**previous, "status": "skipped"})
                continue

        request = Request(source.url, headers={"User-Agent": "hotel-supply-demand-etl/0.1"})
        temp_name: str | None = None
        try:
            with urlopen(
                request, timeout=timeout, context=_verified_ssl_context()
            ) as response:
                content_type = response.headers.get_content_type()
                if content_type not in {
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "application/octet-stream",
                    "application/force-download",
                }:
                    raise FetchError(
                        f"unexpected content type for {source.year}-{source.month:02d}: "
                        f"{content_type}"
                    )
                with tempfile.NamedTemporaryFile(dir=raw_dir, delete=False) as temp:
                    temp_name = temp.name
                    while chunk := response.read(1024 * 1024):
                        temp.write(chunk)
            temp_path = Path(temp_name)
            validate_xlsx(temp_path)
            digest = sha256_file(temp_path)
            os.replace(temp_path, destination)
            entry = {
                "year": source.year,
                "month": source.month,
                "release_type": source.release_type,
                "stat_inf_id": source.stat_inf_id,
                "provider": source.provider,
                "url": source.url,
                "filename": source.filename,
                "period_start": f"{source.year}-{source.month:02d}",
                "period_end": f"{source.year}-{source.month:02d}",
                "published_on": source.published_on,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "sha256": digest,
                "size_bytes": destination.stat().st_size,
            }
            entries[key] = entry
            results.append({**entry, "status": "downloaded"})
        except Exception:
            if temp_name and Path(temp_name).exists():
                Path(temp_name).unlink()
            raise
    manifest["files"] = sorted(
        entries.values(), key=lambda item: (item["year"], item["month"])
    )
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary_manifest, manifest_path)
    return results
