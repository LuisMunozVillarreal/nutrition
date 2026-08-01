#!/usr/bin/env python3
"""CircleCI helper used by the frontend npm audit gate."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ADVISORY_ID_RE = re.compile(r"(GHSA-[A-Za-z0-9-]+|CVE-\d{4}-\d+)")


def _load_allowlist(path: Path) -> set[str]:
    allowlist: set[str] = set()
    if not path.exists():
        return allowlist

    for line in path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if item and not item.startswith("#"):
            allowlist.add(item)
    return allowlist


def _extract_advisory_ids(vulnerability: dict[str, object]) -> set[str]:
    advisory_ids: set[str] = set()
    details = [json.dumps(vulnerability)]

    via = vulnerability.get("via")
    if isinstance(via, list):
        for entry in via:
            if isinstance(entry, str):
                details.append(entry)
            elif isinstance(entry, dict):
                details.append(json.dumps(entry))

    for detail in details:
        advisory_ids.update(ADVISORY_ID_RE.findall(detail))

    if not advisory_ids:
        package_name = vulnerability.get("name")
        if isinstance(package_name, str) and package_name:
            advisory_ids.add(package_name)

    return advisory_ids


def _load_audit_report(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Unable to read npm audit report at {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in npm audit report at {path}") from exc


def _validate_and_extract(
    report: object,
) -> tuple[dict[str, object], dict[str, int]]:
    if not isinstance(report, dict):
        raise ValueError("Invalid npm audit schema: expected top-level JSON object.")

    if "error" in report:
        payload = report.get("error")
        if isinstance(payload, str):
            message = payload
        elif isinstance(payload, dict) and "summary" in payload:
            message = str(payload["summary"])
        else:
            message = str(payload)
        raise ValueError(f"npm audit reported an error: {message}")

    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise ValueError(
            "Invalid npm audit schema: missing or invalid top-level 'vulnerabilities' object."
        )

    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError(
            "Invalid npm audit schema: missing or invalid top-level 'metadata' object."
        )

    return vulnerabilities, metadata


def evaluate_frontend_audit(
    report: object,
    allowlist: set[str],
    audit_exit_code: int,
) -> int:
    try:
        vulnerabilities, _ = _validate_and_extract(report)
    except ValueError as exc:
        print(f"Frontend production dependency audit failed: {exc}", file=sys.stderr)
        return 1

    unwaived_advisories: set[str] = set()

    for vulnerability in vulnerabilities.values():
        if not isinstance(vulnerability, dict):
            continue

        severity = str(vulnerability.get("severity", "")).lower()
        if severity not in {"high", "critical"}:
            continue

        ids = _extract_advisory_ids(vulnerability)
        unwaived_advisories.update(ids.difference(allowlist))

    if audit_exit_code != 0 and audit_exit_code != 1:
        print(
            "Frontend production dependency audit failed: non-vulnerability npm exit code "
            f"{audit_exit_code}.",
            file=sys.stderr,
        )
        return 1

    if unwaived_advisories:
        print(
            "Frontend production dependency audit failed due to unwaived high/critical vulnerabilities:"
        )
        for advisory in sorted(unwaived_advisories):
            print(f"  - {advisory}")
        return 1

    if audit_exit_code == 1:
        print(
            "Frontend production dependency audit passed with only allowlisted high/critical vulnerabilities."
        )
    else:
        print("Frontend production dependency audit passed with no high/critical vulnerabilities.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate frontend npm audit output with waiver allowlist."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        report = _load_audit_report(args.audit_report)
        allowlist = _load_allowlist(args.allowlist)
        return evaluate_frontend_audit(report, allowlist, args.exit_code)
    except ValueError as exc:
        print(f"Frontend production dependency audit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
