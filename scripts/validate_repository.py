"""Check tracked repository files for accidental secrets, local paths, and large data."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

MAX_TRACKED_BYTES = 5 * 1024 * 1024
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".xls", ".xlsx"}
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SENSITIVE_PATTERNS = {
    "macOS personal path": re.compile(r"/Users/(?!example/)[A-Za-z0-9._-]+/"),
    "Linux personal path": re.compile(r"/home/(?!example/)[A-Za-z0-9._-]+/"),
    "e-Stat appId query": re.compile(r"(?:[?&]|&amp;)appId=[^&\s\"']+", re.IGNORECASE),
    "assigned e-Stat application ID": re.compile(
        r"ESTAT_APP_ID\s*=\s*[\"']?[A-Fa-f0-9]{24,}",
        re.IGNORECASE,
    ),
}


def tracked_files(root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item.decode() for item in completed.stdout.split(b"\0") if item]


def validate_repository(root: Path, max_bytes: int = MAX_TRACKED_BYTES) -> list[str]:
    errors: list[str] = []
    for path in tracked_files(root):
        relative = path.relative_to(root)
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > max_bytes:
            errors.append(f"tracked file exceeds {max_bytes} bytes: {relative} ({size} bytes)")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"tracked data file is not allowed: {relative}")
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"LICENSE"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"tracked text file is not UTF-8: {relative}")
            continue
        for label, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{label}: {relative}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--max-bytes", type=int, default=MAX_TRACKED_BYTES)
    args = parser.parse_args()
    errors = validate_repository(args.root.resolve(), args.max_bytes)
    if errors:
        preview = "\n".join(f"- {error}" for error in errors)
        raise SystemExit(f"repository validation failed:\n{preview}")
    print("Repository validation passed")


if __name__ == "__main__":
    main()
