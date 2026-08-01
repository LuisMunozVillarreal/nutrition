"""Tests for the frontend npm audit checker helper."""

# pylint: disable=missing-raises-doc

from __future__ import annotations

import json
from pathlib import Path

import check_frontend_dependency_audit as audit_parser


def _run(
    tmp_path: Path,
    report: object,
    allowlist: list[str],
    exit_code: int = 1,
) -> int:
    """Write temporary inputs and run the audit parser CLI.

    :param tmp_path: Temporary directory fixture path.
    :param report: JSON payload to write into the temporary report file.
    :param allowlist: List of waiver identifiers.
    :param exit_code: Simulated `npm audit` exit code.

    :return: The parser CLI exit status.
    """
    report_path = tmp_path / "npm-audit-report.json"
    allowlist_path = tmp_path / "allowlist.txt"

    report_path.write_text(json.dumps(report), encoding="utf-8")
    allowlist_path.write_text("\n".join(allowlist), encoding="utf-8")

    result = audit_parser.main(
        [
            "--audit-report",
            str(report_path),
            "--allowlist",
            str(allowlist_path),
            "--exit-code",
            str(exit_code),
        ]
    )
    return result


def test_transport_error_payload_fails(tmp_path: Path) -> None:
    """Transport-level failures must fail audit evaluation.

    Args:
        tmp_path: Temporary directory fixture path.
    """
    exit_code = _run(
        tmp_path,
        {"error": "ENOTFOUND: Unable to reach registry"},
        [],
        exit_code=1,
    )
    if exit_code != 1:
        raise AssertionError("Expected audit exit code 1")


def test_invalid_schema_fails(tmp_path: Path) -> None:
    """Invalid schemas should fail audit evaluation.

    Args:
        tmp_path: Temporary directory fixture path.
    """
    exit_code = _run(tmp_path, [], [], exit_code=0)
    if exit_code != 1:
        raise AssertionError("Expected audit exit code 1")


def test_clean_report_passes(tmp_path: Path) -> None:
    """A report with no high/critical issues should pass.

    Args:
        tmp_path: Temporary directory fixture path.
    """
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
    if exit_code != 0:
        raise AssertionError("Expected audit exit code 0")


def test_clean_report_non_vulnerability_failure_status_fails(
    tmp_path: Path,
) -> None:
    """A clean report with non-vulnerability exit code must still fail.

    Args:
        tmp_path: Temporary directory fixture path.
    """
    exit_code = _run(
        tmp_path,
        {
            "auditReportVersion": 3,
            "vulnerabilities": {},
            "metadata": {"vulnerabilities": {"high": 0, "critical": 0}},
        },
        [],
        exit_code=2,
    )
    if exit_code != 1:
        raise AssertionError("Expected audit exit code 1")


def test_unwaived_high_or_critical_report_fails(tmp_path: Path) -> None:
    """Unwaived high/critical issues should fail audit evaluation.

    Args:
        tmp_path: Temporary directory fixture path.
    """
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
    if exit_code != 1:
        raise AssertionError("Expected audit exit code 1")


def test_all_issues_waived_when_status_one_passes(tmp_path: Path) -> None:
    """Waived findings should pass when npm reports high/critical status.

    Args:
        tmp_path: Temporary directory fixture path.
    """
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
    if exit_code != 0:
        raise AssertionError("Expected audit exit code 0")


def test_partial_waiver_fails(tmp_path: Path) -> None:
    """Partially waived findings should still fail.

    Args:
        tmp_path: Temporary directory fixture path.
    """
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
    if exit_code != 1:
        raise AssertionError("Expected audit exit code 1")


def test_indirect_vulnerability_is_evaluated(tmp_path: Path) -> None:
    """Indirect vulnerabilities must still be evaluated and waivered.

    Args:
        tmp_path: Temporary directory fixture path.
    """
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
    if exit_code != 0:
        raise AssertionError("Expected audit exit code 0")


def test_no_identifier_uses_package_name_fallback(tmp_path: Path) -> None:
    """Fallback to package name should apply when advisories are missing.

    Args:
        tmp_path: Temporary directory fixture path.
    """
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
    if exit_code != 0:
        raise AssertionError("Expected audit exit code 0")


def test_non_vulnerability_nonzero_status_fails(tmp_path: Path) -> None:
    """Non-vulnerability nonzero npm exit codes must fail the gate.

    Args:
        tmp_path: Temporary directory fixture path.
    """
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
    if exit_code != 1:
        raise AssertionError("Expected audit exit code 1")
