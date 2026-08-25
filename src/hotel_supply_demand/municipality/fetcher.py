"""Repeatable downloader and manifest writer for municipality e-Stat XLSX files."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
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


def _response_header(response: object, name: str) -> str | None:
    getter = getattr(getattr(response, "headers", None), "get", None)
    return getter(name) if getter else None


def _revision(previous: dict) -> dict:
    return {
        key: previous[key]
        for key in (
            "stat_inf_id",
            "provider",
            "url",
            "published_on",
            "retrieved_at",
            "sha256",
            "size_bytes",
        )
        if key in previous
    }


def fetch_municipality_sources(
    sources: list[MunicipalitySource],
    raw_dir: Path,
    timeout: float = 60,
    *,
    check_remote: bool = False,
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
        local_digest: str | None = None
        if destination.exists() and previous:
            validate_xlsx(destination)
            local_digest = sha256_file(destination)
            if (
                not check_remote
                and local_digest == previous.get("sha256")
                and source.url == previous.get("url")
                and source.stat_inf_id == previous.get("stat_inf_id")
            ):
                previous["published_on"] = source.published_on
                previous["provider"] = source.provider
                results.append({**previous, "status": "skipped"})
                continue

        headers = {"User-Agent": "hotel-supply-demand-etl/0.1"}
        if (
            check_remote
            and previous
            and source.url == previous.get("url")
            and source.stat_inf_id == previous.get("stat_inf_id")
        ):
            if previous.get("etag"):
                headers["If-None-Match"] = previous["etag"]
            if previous.get("last_modified"):
                headers["If-Modified-Since"] = previous["last_modified"]
        request = Request(source.url, headers=headers)
        temp_name: str | None = None
        try:
            try:
                response_context = urlopen(
                    request, timeout=timeout, context=_verified_ssl_context()
                )
            except HTTPError as exc:
                if exc.code == 304 and previous:
                    previous["checked_at"] = datetime.now(UTC).isoformat()
                    results.append({**previous, "status": "unchanged"})
                    continue
                raise
            with response_context as response:
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
                etag = _response_header(response, "ETag")
                last_modified = _response_header(response, "Last-Modified")
            temp_path = Path(temp_name)
            validate_xlsx(temp_path)
            digest = sha256_file(temp_path)
            checked_at = datetime.now(UTC).isoformat()
            if (
                previous
                and digest == previous.get("sha256")
                and local_digest == digest
                and source.url == previous.get("url")
                and source.stat_inf_id == previous.get("stat_inf_id")
            ):
                temp_path.unlink()
                previous["checked_at"] = checked_at
                previous["published_on"] = source.published_on
                if etag:
                    previous["etag"] = etag
                if last_modified:
                    previous["last_modified"] = last_modified
                results.append({**previous, "status": "unchanged"})
                continue
            os.replace(temp_path, destination)
            revisions = list(previous.get("revisions", [])) if previous else []
            if previous and (
                digest != previous.get("sha256")
                or source.url != previous.get("url")
                or source.stat_inf_id != previous.get("stat_inf_id")
            ):
                revisions.append({**_revision(previous), "superseded_at": checked_at})
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
                "retrieved_at": checked_at,
                "checked_at": checked_at,
                "sha256": digest,
                "size_bytes": destination.stat().st_size,
            }
            if etag:
                entry["etag"] = etag
            if last_modified:
                entry["last_modified"] = last_modified
            if revisions:
                entry["revisions"] = revisions
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
