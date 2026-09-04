"""Tests for the clone_preview_secrets script."""

import base64
import json
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest
import yaml
from click.testing import CliRunner
from clone_preview_secrets import COPIED_SECRETS, GENERATED_SECRET_SCHEMA, main
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
        "nutrition-health-sync-secrets",
    ]:
        assert (
            f"Creating least-privilege preview secret {generated}..."
        ) in result.output
    assert (
        f"Refreshing nutrition-gcp-db-backup-credentials from nutrition-staging "
        f"in {expected_ns}..."
    ) in result.output

    # The only staging read is the backup-credentials copy; generated
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


def test_main_refreshes_existing_copied_secret_and_restarts_backend(
    mock_run, mocker
):
    """Existing preview backup credentials are refreshed before backend startup."""
    runner = CliRunner()
    mocker.patch("time.sleep")

    def existing_preview_secrets(*args, **kwargs):
        cmd = args[0]
        if cmd[:3] == ["kubectl", "get", "namespace"]:
            return CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        if cmd[:3] == ["kubectl", "get", "secret"]:
            if (
                cmd[3] == "nutrition-gcp-db-backup-credentials"
                and cmd[5] == "nutrition-staging"
            ):
                return CompletedProcess(
                    cmd,
                    0,
                    stdout=json.dumps(GCP_SOURCE_SECRET).encode("utf-8"),
                    stderr=b"",
                )
            return CompletedProcess(cmd, 0, stdout=b"{}", stderr=b"")
        return CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    mock_run.side_effect = existing_preview_secrets

    result = runner.invoke(main, ["feature/existing-preview"])

    expected_ns = f"nutrition-staging--{sanitise_branch_name('feature/existing-preview')}"
    assert result.exit_code == 0
    copied_applies = [
        call
        for call in _apply_calls(mock_run, expected_ns)
        if json.loads(call.kwargs["input"])["metadata"]["name"]
        == "nutrition-gcp-db-backup-credentials"
    ]
    assert len(copied_applies) == 1
    assert any(
        call.args[0]
        == [
            "kubectl",
            "rollout",
            "restart",
            "deployment/nutrition-backend",
            "-n",
            expected_ns,
        ]
        for call in mock_run.call_args_list
    )


def test_main_fresh_namespace_does_not_require_existing_backend(
    mock_run, mocker
):
    """Secret cloning succeeds before Flux creates the first backend deployment."""
    runner = CliRunner()
    mocker.patch("time.sleep")

    def fresh_namespace(*args, **kwargs):
        cmd = args[0]
        if cmd[:3] == ["kubectl", "get", "namespace"]:
            return CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        if cmd[:3] == ["kubectl", "get", "deployment"]:
            return CompletedProcess(cmd, 1, stdout=b"", stderr=b"NotFound")
        if cmd[:3] == ["kubectl", "rollout", "restart"]:
            return CompletedProcess(cmd, 1, stdout=b"", stderr=b"NotFound")
        return _fake_kubectl(*args, **kwargs)

    mock_run.side_effect = fresh_namespace

    result = runner.invoke(main, ["feature/fresh-preview"])

    assert result.exit_code == 0
    assert not any(
        call.args[0][:3] == ["kubectl", "rollout", "restart"]
        for call in mock_run.call_args_list
    )


def test_main_apply_payload(mock_run, mocker):
    """Test that each preview secret is applied with the expected shape."""
    runner = CliRunner()
    mocker.patch("time.sleep")
    mock_run.side_effect = _fake_kubectl

    runner.invoke(main, ["feature/test"])

    expected_ns = f"nutrition-staging--{sanitise_branch_name('feature/test')}"
    apply_calls = _apply_calls(mock_run, expected_ns)
    assert len(apply_calls) == 6

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

    assert generated_seen == 5
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
    generated_tokens = [
        "token-1",
        "token-2",
        "token-3",
        "token-4",
        "token-5",
    ]
    mocker.patch(
        "clone_preview_secrets.secrets.token_urlsafe",
        side_effect=lambda _n: generated_tokens.pop(0),
    )
    mock_run.side_effect = _fake_kubectl

    result = runner.invoke(main, ["feature/test"])
    expected_ns = f"nutrition-staging--{sanitise_branch_name('feature/test')}"

    assert result.exit_code == 0
    apply_calls = _apply_calls(mock_run, expected_ns)
    assert len(apply_calls) == 6

    generated_values: list[str] = []
    for call in apply_calls:
        payload: dict[str, Any] = json.loads(
            call.kwargs["input"].decode("utf-8")
        )
        if "stringData" in payload:
            assert payload["stringData"]
            generated_values.extend(payload["stringData"].values())

    assert sorted(generated_values) == sorted(
        [
            "token-1",
            "token-2",
            "token-3",
            "token-4",
            "token-5",
            "10.0.0.0/8",
        ]
    )


def test_preview_generates_every_secret_referenced_by_base_workloads():
    """Preview namespaces generate every Secret required by base workloads."""
    repository = Path(__file__).resolve().parents[2]
    required: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            secret_ref = value.get("secretKeyRef")
            if isinstance(secret_ref, dict) and "name" in secret_ref:
                required.add(secret_ref["name"])
            secret_volume = value.get("secret")
            if (
                isinstance(secret_volume, dict)
                and "secretName" in secret_volume
            ):
                required.add(secret_volume["secretName"])
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for manifest_name in ("backend.yaml", "webapp.yaml"):
        manifest = repository / "platform/k8s/base" / manifest_name
        for document in yaml.safe_load_all(manifest.read_text()):
            collect(document)

    available = set(GENERATED_SECRET_SCHEMA) | set(COPIED_SECRETS)
    assert required <= available
