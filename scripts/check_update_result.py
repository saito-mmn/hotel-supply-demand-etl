"""Fail an unattended update when human configuration or approval is required."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

BLOCKING_FIELDS = {"approval_required", "configuration_required"}


def find_blockers(value: Any, path: str = "result") -> list[str]:
    blockers: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in BLOCKING_FIELDS and child:
                blockers.append(child_path)
            blockers.extend(find_blockers(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            blockers.extend(find_blockers(child, f"{path}[{index}]"))
    return blockers


def validate_update_result(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("update result must be a JSON object")
    blockers = find_blockers(payload)
    if blockers:
        raise ValueError(
            "automatic publication stopped; review required at: " + ", ".join(blockers)
        )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args()
    payload = validate_update_result(args.result)
    updated = any(
        isinstance(domain, dict) and domain.get("updated") is True for domain in payload.values()
    )
    if args.github_output:
        output = os.environ.get("GITHUB_OUTPUT")
        if not output:
            raise ValueError("GITHUB_OUTPUT is not set")
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"updated={str(updated).lower()}\n")
    print(f"Update result accepted: updated={str(updated).lower()}")


if __name__ == "__main__":
    main()
