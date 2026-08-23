"""Tests for the clone_preview_secrets script."""

import base64
import json
from subprocess import CompletedProcess
from typing import Any

import pytest
from click.testing import CliRunner
from clone_preview_secrets import main
from sanitise_branch import sanitise_branch_name

GCP_SOURCE_SECRET = {
    "apiVersion": "v1",
    "kind": "Secret",
    "metadata": {
        "name": "nutrition-gcp-db-backup-credentials",
        "namespace": "nutrition-staging",
        "uid": "staging-uid",
        "resourceVersion": "12345",
        "creationTimestamp": "2026-01-01T00:00:00Z",
    },
    "type": "Opaque",
    "data": {
        "nutrition-gcp-db-backup-credentials.json": base64.b64encode(
            b'{"client_email": "backup@example.com", "private_key": "key"}'
        ).decode("utf-8"),
    },
}


@pytest.fixture
def mock_run(mocker):
    """Fixture to mock subprocess.run."""
    return mocker.patch("clone_preview_secrets.subprocess.run")


def _fake_kubectl(*args, **kwargs):
    """Return NotFound for preview existence checks, source JSON for the copy."""
    cmd = args[0]
    if cmd[:3] == ["kubectl", "get", "secret"]:
        # Read from staging is the backup-credentials copy source.
        if (
            cmd[3] == "nutrition-gcp-db-backup-credentials"
            and cmd[5] == "nutrition-staging"
        ):
            return CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=json.dumps(GCP_SOURCE_SECRET).encode("utf-8"),
                stderr=b"",
            )
        # Any other secret read is a create-if-absent existence check: NotFound.
        return CompletedProcess(args=cmd, returncode=1, stdout=b"", stderr=b"")
    return CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")


def _apply_calls(mock_run, expected_ns: str) -> list:
    return [
        call
        for call in mock_run.call_args_list
        if call.args[0][0:3] == ["kubectl", "apply", "-n"]
        and call.args[0][3] == expected_ns
    ]


def test_main_skip_main_branch(mock_run):
    """Test that secret cloning is skipped on the main branch."""
    runner = CliRunner()

    result = runner.invoke(main, ["main"])

    assert result.exit_code == 0
    assert "Branch is main. Skipping secret cloning." in result.output
    mock_run.assert_not_called()


def test_main_success(mock_run, mocker):
    """Test that generated secrets are created and the backup creds copied."""
    runner = CliRunner()
    mocker.patch("time.sleep")
    mock_run.side_effect = _fake_kubectl

    result = runner.invoke(main, ["feature/test-branch"])

    assert result.exit_code == 0
    expected_ns = (
        f"nutrition-staging--{sanitise_branch_name('feature/test-branch')}"
    )
    assert f"Waiting for namespace {expected_ns} to exist..." in result.output
    for generated in [
        "nutrition-webapp-nextauth-secret",
        "nutrition-postgresql",
        "nutrition-django-secret-key",
        "nutrition-gemini-api-key",
    ]:
        assert (
            f"Creating least-privilege preview secret {generated}..."
        ) in result.output
    assert (
        f"Copying nutrition-gcp-db-backup-credentials from nutrition-staging "
        f"to {expected_ns}..."
    ) in result.output

    # The only staging read is the backup-credentials copy; the four generated
    # secrets never read from staging.
    staging_reads = [
        call.args[0]
        for call in mock_run.call_args_list
        if call.args[0][:2] == ["kubectl", "get"]
        and "-n" in call.args[0]
        and call.args[0][-1] != expected_ns
        and call.args[0][call.args[0].index("-n") + 1] == "nutrition-staging"
    ]
    assert staging_reads == [
        [
            "kubectl",
            "get",
            "secret",
            "nutrition-gcp-db-backup-credentials",
            "-n",
            "nutrition-staging",
            "-o",
            "json",
        ]
    ]


def test_main_apply_payload(mock_run, mocker):
    """Test that each preview secret is applied with the expected shape."""
    runner = CliRunner()
    mocker.patch("time.sleep")
    mock_run.side_effect = _fake_kubectl

    runner.invoke(main, ["feature/test"])

    expected_ns = f"nutrition-staging--{sanitise_branch_name('feature/test')}"
    apply_calls = _apply_calls(mock_run, expected_ns)
    assert len(apply_calls) == 5

    generated_seen = 0
    copied_seen = 0
    for call in apply_calls:
        payload: dict[str, Any] = json.loads(
            call.kwargs["input"].decode("utf-8")
        )
        assert payload["kind"] == "Secret"
        assert payload["type"] == "Opaque"
        assert (
            payload["metadata"]["labels"]["app.kubernetes.io/managed-by"]
            == "nutrition-preview"
        )
        assert payload["metadata"]["namespace"] == expected_ns
        if (
            payload["metadata"]["name"]
            == "nutrition-gcp-db-backup-credentials"
        ):
            # The copied secret carries the source data payload, not a stub.
            assert "stringData" not in payload
            assert payload["data"] == GCP_SOURCE_SECRET["data"]
            copied_seen += 1
        else:
            assert "stringData" in payload
            assert "data" not in payload
            generated_seen += 1

    assert generated_seen == 4
    assert copied_seen == 1


def test_main_generated_secrets_do_not_read_staging(mock_run, mocker):
    """Test that generated secrets are never sourced from staging."""
    runner = CliRunner()
    mocker.patch("time.sleep")
    mock_run.side_effect = _fake_kubectl

    result = runner.invoke(main, ["feature/test"])

    assert result.exit_code == 0

    # Every staging-namespace secret read must be for the backup credentials.
    staging_secret_reads = [
        call.args[0]
        for call in mock_run.call_args_list
        if call.args[0][:3] == ["kubectl", "get", "secret"]
        and call.args[0][5] == "nutrition-staging"
    ]
    assert len(staging_secret_reads) == 1
    assert staging_secret_reads[0][3] == "nutrition-gcp-db-backup-credentials"


def test_main_secrets_are_preview_scoped_and_non_empty(mock_run, mocker):
    """Test generated secret values are fresh and never empty/stubbed."""
    runner = CliRunner()
    mocker.patch("time.sleep")
    generated_tokens = ["token-1", "token-2", "token-3", "token-4"]
    mocker.patch(
        "clone_preview_secrets.secrets.token_urlsafe",
        side_effect=lambda _n: generated_tokens.pop(0),
    )
    mock_run.side_effect = _fake_kubectl

    result = runner.invoke(main, ["feature/test"])
    expected_ns = f"nutrition-staging--{sanitise_branch_name('feature/test')}"

    assert result.exit_code == 0
    apply_calls = _apply_calls(mock_run, expected_ns)
    assert len(apply_calls) == 5

    generated_values: list[str] = []
    for call in apply_calls:
        payload: dict[str, Any] = json.loads(
            call.kwargs["input"].decode("utf-8")
        )
        if "stringData" in payload:
            assert payload["stringData"]
            generated_values.extend(payload["stringData"].values())

    assert sorted(generated_values) == sorted(
        ["token-1", "token-2", "token-3", "token-4"]
    )
