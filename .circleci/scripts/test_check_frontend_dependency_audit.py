"""Tests for the frontend npm audit checker helper."""

import json
from pathlib import Path

from check_frontend_dependency_audit import _load_allowlist, evaluate_frontend_audit, _load_audit_report


def _run(tmp_path: Path, report: object, allowlist: list[str], exit_code: int = 1) -> int:
    report_path = tmp_path / "npm-audit-report.json"
    allowlist_path = tmp_path / "allowlist.txt"

    report_path.write_text(json.dumps(report), encoding="utf-8")
    allowlist_path.write_text("\n".join(allowlist), encoding="utf-8")

    return evaluate_frontend_audit(
        _load_audit_report(report_path),
        _load_allowlist(allowlist_path),
        exit_code,
    )


def test_transport_error_payload_fails(tmp_path: Path):
    exit_code = _run(
        tmp_path,
        {"error": "ENOTFOUND: Unable to reach registry"},
        [],
        exit_code=1,
    )
    assert exit_code == 1


def test_invalid_schema_fails(tmp_path: Path):
    exit_code = _run(tmp_path, [], [], exit_code=0)
    assert exit_code == 1


def test_clean_report_passes(tmp_path: Path):
    exit_code = _run(
        tmp_path,
        {
            "auditReportVersion": 3,
            "vulnerabilities": {},
            "metadata": {"vulnerabilities": {"high": 0, "critical": 0}},
        },
        [],
        exit_code=0,
    )
    assert exit_code == 0


def test_unwaived_high_or_critical_report_fails(tmp_path: Path):
    exit_code = _run(
        tmp_path,
        {
            "auditReportVersion": 3,
            "vulnerabilities": {
                "lodash": {
                    "name": "lodash",
                    "severity": "high",
                    "isDirect": True,
                    "via": ["GHSA-xxxx-yyyy-zzzz"],
                }
            },
            "metadata": {"vulnerabilities": {"high": 1, "critical": 0}},
        },
        [],
        exit_code=1,
    )
    assert exit_code == 1


def test_all_issues_waived_when_status_one_passes(tmp_path: Path):
    exit_code = _run(
        tmp_path,
        {
            "auditReportVersion": 3,
            "vulnerabilities": {
                "lodash": {
                    "name": "lodash",
                    "severity": "high",
                    "isDirect": True,
                    "via": ["GHSA-xxxx-yyyy-zzzz"],
                }
            },
            "metadata": {"vulnerabilities": {"high": 1, "critical": 0}},
        },
        ["GHSA-xxxx-yyyy-zzzz"],
        exit_code=1,
    )
    assert exit_code == 0


def test_partial_waiver_fails(tmp_path: Path):
    exit_code = _run(
        tmp_path,
        {
            "auditReportVersion": 3,
            "vulnerabilities": {
                "package-a": {
                    "name": "package-a",
                    "severity": "high",
                    "via": ["GHSA-aaa-bbbb-cccc"],
                },
                "package-b": {
                    "name": "package-b",
                    "severity": "critical",
                    "via": ["GHSA-ddd-eeee-ffff"],
                },
            },
            "metadata": {"vulnerabilities": {"high": 1, "critical": 1}},
        },
        ["GHSA-aaa-bbbb-cccc"],
        exit_code=1,
    )
    assert exit_code == 1


def test_indirect_vulnerability_is_evaluated(tmp_path: Path):
    exit_code = _run(
        tmp_path,
        {
            "auditReportVersion": 3,
            "vulnerabilities": {
                "indirect-vuln": {
                    "name": "indirect-vuln",
                    "severity": "critical",
                    "isDirect": False,
                    "via": ["GHSA-indirect-aaaa-bbbb-cccc"],
                }
            },
            "metadata": {"vulnerabilities": {"high": 0, "critical": 1}},
        },
        ["GHSA-indirect-aaaa-bbbb-cccc"],
        exit_code=1,
    )
    assert exit_code == 0


def test_no_identifier_uses_package_name_fallback(tmp_path: Path):
    exit_code = _run(
        tmp_path,
        {
            "auditReportVersion": 3,
            "vulnerabilities": {
                "legacy-pkg": {
                    "name": "legacy-pkg",
                    "severity": "high",
                    "via": [],
                }
            },
            "metadata": {"vulnerabilities": {"high": 1, "critical": 0}},
        },
        ["legacy-pkg"],
        exit_code=1,
    )
    assert exit_code == 0


def test_non_vulnerability_nonzero_status_fails(tmp_path: Path):
    exit_code = _run(
        tmp_path,
        {
            "auditReportVersion": 3,
            "vulnerabilities": {
                "lodash": {
                    "name": "lodash",
                    "severity": "high",
                    "via": ["GHSA-xxxx-yyyy-zzzz"],
                }
            },
            "metadata": {"vulnerabilities": {"high": 1, "critical": 0}},
        },
        [],
        exit_code=2,
    )
    assert exit_code == 1
