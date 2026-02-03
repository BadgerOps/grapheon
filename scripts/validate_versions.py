from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def changelog_version(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    match = re.search(r"^##\s+(\d+\.\d+\.\d+)", content, re.MULTILINE)
    if not match:
        raise ValueError(f"No version heading found in {path}")
    return match.group(1)


def check_backend() -> list[str]:
    errors: list[str] = []
    version_file = ROOT / "backend" / "VERSION"
    changelog = ROOT / "backend" / "CHANGELOG.md"
    version = version_file.read_text(encoding="utf-8").strip()
    changelog_version_value = changelog_version(changelog)
    if version != changelog_version_value:
        errors.append(
            f"Backend version mismatch: VERSION={version} CHANGELOG={changelog_version_value}"
        )
    return errors


def check_frontend() -> list[str]:
    errors: list[str] = []
    package_json = ROOT / "frontend" / "package.json"
    changelog = ROOT / "frontend" / "CHANGELOG.md"
    version = json.loads(package_json.read_text(encoding="utf-8"))["version"]
    changelog_version_value = changelog_version(changelog)
    if version != changelog_version_value:
        errors.append(
            f"Frontend version mismatch: package.json={version} CHANGELOG={changelog_version_value}"
        )
    return errors


def main() -> int:
    errors = []
    errors.extend(check_backend())
    errors.extend(check_frontend())

    if errors:
        for error in errors:
            print(error)
        return 1

    print("Version files and changelogs are in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
