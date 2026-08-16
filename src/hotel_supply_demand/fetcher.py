"""Shared file integrity helpers for official XLSX downloads."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path


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
