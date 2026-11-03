from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARD_LIMIT = 600
SOFT_LIMIT = 400
REACT_LIMIT = 250
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".css"}
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "skyler",
    "deepseek-harness",
}
GENERATED_MARKERS = {"frontend/src/shared/api/generated"}
EXCEPTIONS_PATH = ROOT / "docs" / "standards" / "file-size-exceptions.txt"


def main() -> int:
    exceptions = _load_exceptions()
    violations: list[str] = []
    warnings: list[str] = []

    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(ROOT)
        if _is_excluded(relative) or _is_generated(relative):
            continue
        line_count = _line_count(path)
        limit = REACT_LIMIT if path.suffix == ".tsx" else SOFT_LIMIT
        if line_count > HARD_LIMIT and relative.as_posix() not in exceptions:
            violations.append(f"{relative}: {line_count} lines (limit {HARD_LIMIT})")
        elif line_count > limit and relative.as_posix() not in exceptions:
            warnings.append(f"{relative}: {line_count} lines (soft limit {limit})")

    if violations:
        print("File size check failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    if warnings:
        print("File size warnings:")
        for warning in warnings:
            print(f"- {warning}")

    print("File size check passed")
    return 0


def _load_exceptions() -> set[str]:
    if not EXCEPTIONS_PATH.exists():
        return set()
    entries: set[str] = set()
    for line in EXCEPTIONS_PATH.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            entries.add(value.split("|", maxsplit=1)[0].strip())
    return entries


def _is_excluded(relative: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in relative.parts)


def _is_generated(relative: Path) -> bool:
    value = relative.as_posix()
    return any(value.startswith(marker) for marker in GENERATED_MARKERS)


def _line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as source:
        return sum(1 for _ in source)


if __name__ == "__main__":
    sys.exit(main())
