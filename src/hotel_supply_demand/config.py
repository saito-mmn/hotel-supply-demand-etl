"""Application configuration."""

from __future__ import annotations

import os
from pathlib import Path


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing."""


def _read_app_id_from_dotenv(path: Path) -> str:
    """Read only ESTAT_APP_ID from a local dotenv file."""
    if not path.is_file():
        return ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "ESTAT_APP_ID":
            return value.strip().strip('"').strip("'")
    return ""


def get_estat_app_id(dotenv_path: Path | None = None) -> str:
    """Return the e-Stat application ID without logging or displaying it.

    The process environment takes precedence. If it is absent, the function
    reads only ``ESTAT_APP_ID`` from the project-local ``.env`` file.
    """
    app_id = os.environ.get("ESTAT_APP_ID", "").strip()
    if not app_id:
        app_id = _read_app_id_from_dotenv(dotenv_path or Path.cwd() / ".env")
    if not app_id:
        raise ConfigurationError(
            "ESTAT_APP_ID is not set. Export it or save it in the gitignored "
            "project-local .env file before running an API command."
        )
    return app_id
