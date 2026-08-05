"""Tests for frontend dependency audit CircleCI command sequencing."""

from __future__ import annotations

from pathlib import Path


def _extract_frontend_dependency_audit_command() -> list[str]:
    """Extract the CircleCI frontend audit shell block from config."""
    config_path = Path(__file__).resolve().parent.parent / "config.yml"
    lines = config_path.read_text(encoding="utf-8").splitlines()

    step_start = None
    for index, line in enumerate(lines):
        if "name: Run Frontend Production Dependency Audit" in line:
            step_start = index
            break
    if step_start is None:
        raise AssertionError(
            "Frontend dependency audit step not found in CircleCI config"
        )

    command_line = None
    for index in range(step_start, len(lines)):
        if lines[index].strip() == "command: |":
            command_line = index
            break
    if command_line is None:
        raise AssertionError(
            "Frontend audit command block not found in CircleCI config"
        )

    body_indent: int | None = None
    command_lines: list[str] = []

    audit_block_start = command_line + 1
    for raw_line in lines[audit_block_start:]:
        if raw_line.strip() == "":
            if body_indent is None:
                continue
            command_lines.append("")
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if body_indent is None:
            body_indent = indent

        if indent < body_indent:
            break

        command_lines.append(raw_line[body_indent:])

    if not command_lines:
        raise AssertionError("Unable to parse frontend audit shell command")

    return command_lines


def _line_indices_in_order(
    command_lines: list[str], expected: list[str]
) -> None:
    """Assert each expected line appears in the command in order."""
    normalized = [line.strip() for line in command_lines if line.strip()]
    cursor = -1

    for token in expected:
        for index in range(cursor + 1, len(normalized)):
            if normalized[index] == token:
                cursor = index
                break
        else:
            raise AssertionError(
                f"Expected command token not found in order: {token}"
            )


def test_frontend_audit_shell_command_sequence() -> None:
    """Ensure audit command preserves exit-code capture under CircleCI errexit.

    Raises:
        AssertionError: If the parsed command sequence is missing expected tokens
            or the parser invocation does not propagate AUDIT_EXIT_CODE.
    """
    command_lines = _extract_frontend_dependency_audit_command()

    _line_indices_in_order(
        command_lines,
        [
            "set +e",
            (
                "npm audit --omit=dev --audit-level=high "
                "--json > /tmp/npm-audit-report.json"
            ),
            "AUDIT_EXIT_CODE=$?",
            "set -e",
            "python3 ../.circleci/scripts/check_frontend_dependency_audit.py \\",
        ],
    )

    normalized = [line.strip() for line in command_lines if line.strip()]

    if not any(
        '--exit-code "$AUDIT_EXIT_CODE"' in line for line in normalized
    ):
        raise AssertionError(
            "Expected parser invocation to pass AUDIT_EXIT_CODE"
        )
