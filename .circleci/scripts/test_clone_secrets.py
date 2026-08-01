"""Tests for the clone_preview_secrets script."""

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from clone_preview_secrets import (
    OPTIONAL_SECRETS,
    REQUIRED_SECRETS,
    clone_secrets,
    main,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _secret_references(value):
    """Recursively collect Secret references and their optionality."""
    references = []
    if isinstance(value, dict):
        reference = value.get("secretKeyRef")
        if isinstance(reference, dict) and reference.get("name"):
            references.append(
                (reference["name"], bool(reference.get("optional", False)))
            )
        secret = value.get("secret")
        if isinstance(secret, dict) and secret.get("secretName"):
            references.append(
                (secret["secretName"], bool(secret.get("optional", False)))
            )
        for nested in value.values():
            references.extend(_secret_references(nested))
    elif isinstance(value, list):
        for nested in value:
            references.extend(_secret_references(nested))
    return references


def test_preview_secret_inventory_matches_rendered_workload_optionality():
    """Preview inventory exactly matches base workload Secret semantics."""
    references = {}
    for manifest_path in (REPOSITORY_ROOT / "platform/k8s/base").glob("*.yaml"):
        for document in yaml.safe_load_all(manifest_path.read_text()):
            for name, optional in _secret_references(document):
                references.setdefault(name, []).append(optional)

    rendered_required = {
        name for name, optionality in references.items() if not all(optionality)
    }
    rendered_optional = {
        name for name, optionality in references.items() if all(optionality)
    }

    assert set(REQUIRED_SECRETS) == rendered_required
    assert set(OPTIONAL_SECRETS) == rendered_optional
    assert rendered_optional == {"nutrition-garmin-config"}


@pytest.fixture
def mock_run(mocker):
    """Fixture to mock subprocess.run."""
    return mocker.patch("clone_preview_secrets.subprocess.run")


def _secret_result(mocker, *, name="example-secret"):
    result = mocker.MagicMock(returncode=0)
    result.stdout = json.dumps(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name, "namespace": "nutrition-staging"},
            "data": {"key": "value"},
        }
    ).encode("utf-8")
    return result


def test_optional_secret_absence_is_skipped_cleanly(mock_run, mocker):
    """An absent optional Garmin Secret does not block preview rollout."""
    present = _secret_result(mocker)
    absent = mocker.MagicMock(returncode=0, stdout=b"")
    applied = mocker.MagicMock(returncode=0)
    mock_run.side_effect = [present, applied] * len(REQUIRED_SECRETS) + [
        absent
    ]

    clone_secrets("preview-example")

    assert mock_run.call_count == len(REQUIRED_SECRETS) * 2 + 1


def test_optional_secret_present_is_cloned(mock_run, mocker):
    """A present optional Garmin Secret is applied to the preview namespace."""
    present = _secret_result(mocker)
    applied = mocker.MagicMock(returncode=0)
    mock_run.side_effect = [present, applied] * (
        len(REQUIRED_SECRETS) + len(OPTIONAL_SECRETS)
    )

    clone_secrets("preview-example")

    assert mock_run.call_count == 2 * (
        len(REQUIRED_SECRETS) + len(OPTIONAL_SECRETS)
    )


@pytest.mark.parametrize("returncode", [1, 126])
def test_optional_secret_lookup_errors_fail(mock_run, mocker, returncode):
    """Forbidden and other lookup errors are never treated as absence."""
    present = _secret_result(mocker)
    failed = mocker.MagicMock(returncode=returncode, stdout=b"")
    applied = mocker.MagicMock(returncode=0)
    mock_run.side_effect = [present, applied] * len(REQUIRED_SECRETS) + [
        failed
    ]

    with pytest.raises(SystemExit) as raised:
        clone_secrets("preview-example")

    assert raised.value.code == 1


def test_required_secret_absence_fails(mock_run, mocker):
    """An absent required Secret remains a hard preview failure."""
    mock_run.return_value = mocker.MagicMock(returncode=0, stdout=b"")

    with pytest.raises(SystemExit) as raised:
        clone_secrets("preview-example")

    assert raised.value.code == 1


def test_main_skip_main_branch(mock_run):
    """Test that secret cloning is skipped on the main branch."""
    # Given we have a CLI runner
    runner = CliRunner()

    # When we run the script for the 'main' branch
    result = runner.invoke(main, ["main"])

    # Then it should exit with code 0 and not run any subprocesses
    assert result.exit_code == 0
    assert "Branch is main. Skipping secret cloning." in result.output
    mock_run.assert_not_called()


def test_main_success(mock_run, mocker):
    """Test successful cloning of secrets."""
    # Given we have a CLI runner and our subprocess mocks succeed
    runner = CliRunner()
    mocker.patch("time.sleep")  # Avoid sleeping in tests

    # Mock responses for kubectl get namespace, secrets, and apply
    mock_get_ns = mocker.MagicMock()
    mock_get_ns.returncode = 0

    mock_get_secret = mocker.MagicMock()
    mock_get_secret.returncode = 0
    mock_get_secret.stdout = json.dumps(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "my-secret",
                "namespace": "nutrition-staging",
                "uid": "1234",
                "resourceVersion": "5678",
                "creationTimestamp": "2026-07-05T00:00:00Z",
            },
            "data": {"key": "value"},
        }
    ).encode("utf-8")

    mock_apply = mocker.MagicMock()
    mock_apply.returncode = 0

    mock_run.side_effect = [mock_get_ns] + [
        mock_get_secret,
        mock_apply,
    ] * (len(REQUIRED_SECRETS) + len(OPTIONAL_SECRETS))

    # When we run the script for a preview branch
    result = runner.invoke(main, ["feature/test-branch"])

    # Then the script should succeed and wait for target namespace
    assert result.exit_code == 0
    msg_ns = (
        "Waiting for namespace "
        + "nutrition-staging--feature-test-branch to exist..."
    )
    assert msg_ns in result.output
    msg_exists = (
        "Namespace nutrition-staging--" + "feature-test-branch exists."
    )
    assert msg_exists in result.output
    assert "Copying nutrition-webapp-nextauth-secret" in result.output

    # And it should call kubectl get namespace once, plus get+apply per secret.
    secret_count = len(REQUIRED_SECRETS) + len(OPTIONAL_SECRETS)
    assert mock_run.call_count == 1 + (secret_count * 2)

    # And it should remove unwanted metadata fields
    last_apply_call = mock_run.call_args_list[-1]
    applied_json = json.loads(last_apply_call[1]["input"].decode("utf-8"))
    assert "namespace" not in applied_json["metadata"]
    assert "uid" not in applied_json["metadata"]
    assert "resourceVersion" not in applied_json["metadata"]
    assert "creationTimestamp" not in applied_json["metadata"]
