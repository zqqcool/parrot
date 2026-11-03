from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TypedDict, cast

OVERALL_MINIMUM = 85.0
SECURITY_MINIMUM = 95.0
SECURITY_PATHS = (
    "app/api/dependencies.py",
    "app/api/routes/admin_access.py",
    "app/api/routes/admin_tenants.py",
    "app/api/routes/admin_users.py",
    "app/api/routes/auth.py",
    "app/modules/iam/",
    "app/modules/tenancy/",
)


class Summary(TypedDict):
    covered_lines: int
    num_statements: int
    covered_branches: int
    num_branches: int


class FileCoverage(TypedDict):
    summary: Summary


class CoverageReport(TypedDict):
    files: dict[str, FileCoverage]
    totals: Summary


def percentage(summaries: list[Summary]) -> float:
    covered = sum(item["covered_lines"] + item["covered_branches"] for item in summaries)
    possible = sum(item["num_statements"] + item["num_branches"] for item in summaries)
    return 100.0 if possible == 0 else covered * 100 / possible


def is_security_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in SECURITY_PATHS)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_backend_coverage.py COVERAGE_JSON", file=sys.stderr)
        return 2
    report_path = Path(sys.argv[1])
    report = cast(CoverageReport, json.loads(report_path.read_text(encoding="utf-8")))
    overall = percentage([report["totals"]])
    security = percentage(
        [item["summary"] for path, item in report["files"].items() if is_security_path(path)]
    )
    failures: list[str] = []
    if overall < OVERALL_MINIMUM:
        failures.append(f"backend overall coverage {overall:.2f}% < {OVERALL_MINIMUM:.0f}%")
    if security < SECURITY_MINIMUM:
        failures.append(f"IAM/tenancy/RBAC coverage {security:.2f}% < {SECURITY_MINIMUM:.0f}%")
    if failures:
        print("Coverage gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Coverage gate passed: overall={overall:.2f}%, IAM/tenancy/RBAC={security:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
