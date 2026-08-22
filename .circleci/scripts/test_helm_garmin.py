"""Rendered Helm contracts for the Garmin synchronization workload."""

import copy
import re
import shutil
import subprocess  # nosec: B404
from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHART_ROOT = REPOSITORY_ROOT / "backend/platform/kube"
CACHED_HELM = CHART_ROOT / "tests/.cache/helm/helm"
HELM_BINARY = (
    str(CACHED_HELM)
    if CACHED_HELM.is_file()
    else shutil.which("helm") or str(CACHED_HELM)
)
BASE_BACKEND = REPOSITORY_ROOT / "platform/k8s/base/backend.yaml"
SETTINGS = REPOSITORY_ROOT / "backend/config/settings.py"
ACTIVE_GARMIN_URL_SETTINGS = (
    "GARMIN_AUTHORIZATION_URL",
    "GARMIN_TOKEN_URL",
    "GARMIN_ACTIVITIES_URL",
    "GARMIN_REVOKE_TOKEN_URL",
    "GARMIN_CALLBACK_URL",
    "GARMIN_PROVIDER_ORIGINS",
    "GARMIN_CALLBACK_ALLOWED_ORIGINS",
)


def _local_chart(tmp_path: Path) -> Path:
    """Copy the local chart without its unrelated remote database dependency."""
    chart = tmp_path / "chart"
    shutil.copytree(CHART_ROOT, chart)
    chart_data = yaml.safe_load((chart / "Chart.yaml").read_text())
    chart_data.pop("dependencies", None)
    (chart / "Chart.yaml").write_text(yaml.safe_dump(chart_data))
    (chart / "Chart.lock").unlink(missing_ok=True)
    return chart


def _render_result(
    chart: Path,
    values: dict | None = None,
    set_strings: tuple[tuple[str, str], ...] = (),
) -> subprocess.CompletedProcess[str]:
    """Render a chart and return the Helm process result."""
    command = [HELM_BINARY, "template", "contract", str(chart)]
    if values is not None:
        values_path = chart.parent / "contract-values.yaml"
        values_path.write_text(yaml.safe_dump(values))
        command.extend(["--values", str(values_path)])
    for name, value in set_strings:
        command.extend(["--set-string", f"{name}={value}"])
    return subprocess.run(  # nosec: B603, B607
        command,
        capture_output=True,
        check=False,
        text=True,
    )


def _render(chart: Path, values: dict | None = None) -> list[dict]:
    """Render a chart and return non-empty Kubernetes documents."""
    result = _render_result(chart, values)
    assert result.returncode == 0, "Helm rendering failed"
    return [
        document
        for document in yaml.safe_load_all(result.stdout)
        if isinstance(document, dict)
    ]


def _container(workload: dict) -> dict:
    if workload["kind"] == "Deployment":
        return workload["spec"]["template"]["spec"]["containers"][0]
    return workload["spec"]["jobTemplate"]["spec"]["template"]["spec"][
        "containers"
    ][0]


def _garmin_env(workload: dict) -> dict[str, dict]:
    return {
        entry["name"]: entry
        for entry in _container(workload)["env"]
        if entry["name"].startswith("GARMIN_")
    }


def _configured_garmin_names() -> set[str]:
    source = SETTINGS.read_text()
    return set(
        re.findall(
            r'ENV\.(?:bool|str|int|list)\(\s*["\'](GARMIN_[A-Z0-9_]+)["\']',
            source,
        )
    )


def _set_env_value(environment: list[dict], name: str, value: str) -> None:
    """Set one direct environment value in a synthetic Helm contract."""
    entry = next(item for item in environment if item["name"] == name)
    entry.clear()
    entry.update({"name": name, "value": value})


def _active_values() -> dict:
    """Return complete active scheduler values using non-real test origins."""
    base = list(yaml.safe_load_all(BASE_BACKEND.read_text()))[0]
    environment = copy.deepcopy(
        base["spec"]["template"]["spec"]["containers"][0]["env"]
    )
    complete_values = {
        "GARMIN_ENABLED": "true",
        "GARMIN_AUTHORIZATION_URL": (
            "https://authorize.runtime.internal/oauth/authorize"
        ),
        "GARMIN_TOKEN_URL": "https://token.runtime.internal/oauth/token",
        "GARMIN_ACTIVITIES_URL": "https://activities.runtime.internal/activities",
        "GARMIN_REVOKE_TOKEN_URL": "https://revoke.runtime.internal/oauth/revoke",
        "GARMIN_CALLBACK_URL": (
            "https://application.runtime.internal/settings/garmin-callback"
        ),
        "GARMIN_PROVIDER_ORIGINS": "https://provider.runtime.internal",
        "GARMIN_CALLBACK_ALLOWED_ORIGINS": "https://application.runtime.internal",
    }
    for name, value in complete_values.items():
        _set_env_value(environment, name, value)
    return {
        "env": environment,
        "garminSync": {
            "enabled": True,
            "suspend": False,
        },
    }


def test_helm_default_does_not_render_garmin_scheduler(tmp_path: Path) -> None:
    """The supported Helm scheduler is disabled unless runtime values opt in."""
    documents = _render(_local_chart(tmp_path))

    assert not any(
        document.get("kind") == "CronJob"
        and document.get("metadata", {})
        .get("name", "")
        .endswith("garmin-sync")
        for document in documents
    )


def test_helm_enabled_scheduler_matches_backend_runtime_contract(
    tmp_path: Path,
) -> None:
    """Enabled rendering has exact Garmin env parity and safe job controls."""
    values = _active_values()
    values["garminSync"].update(
        {
            "schedule": "7,37 * * * *",
            "timeZone": "Etc/UTC",
            "concurrencyPolicy": "Forbid",
            "startingDeadlineSeconds": 321,
            "successfulJobsHistoryLimit": 2,
            "failedJobsHistoryLimit": 4,
            "activeDeadlineSeconds": 654,
            "backoffLimit": 2,
            "ttlSecondsAfterFinished": 987,
        }
    )

    documents = _render(_local_chart(tmp_path), values)
    deployment = next(
        document for document in documents if document["kind"] == "Deployment"
    )
    scheduler = next(
        document
        for document in documents
        if document["kind"] == "CronJob"
        and document["metadata"]["name"].endswith("garmin-sync")
    )

    assert set(_garmin_env(deployment)) == _configured_garmin_names()
    assert _garmin_env(scheduler) == _garmin_env(deployment)
    assert scheduler["spec"] == {
        **scheduler["spec"],
        "schedule": "7,37 * * * *",
        "timeZone": "Etc/UTC",
        "suspend": False,
        "concurrencyPolicy": "Forbid",
        "startingDeadlineSeconds": 321,
        "successfulJobsHistoryLimit": 2,
        "failedJobsHistoryLimit": 4,
    }
    job = scheduler["spec"]["jobTemplate"]["spec"]
    assert job["activeDeadlineSeconds"] == 654
    assert job["backoffLimit"] == 2
    assert job["ttlSecondsAfterFinished"] == 987
    assert job["template"]["spec"]["restartPolicy"] == "Never"
    assert (
        job["template"]["spec"]["serviceAccountName"]
        == deployment["spec"]["template"]["spec"]["serviceAccountName"]
    )
    assert _container(scheduler)["image"] == _container(deployment)["image"]
    assert _container(scheduler)["command"] == [
        "python",
        "manage.py",
        "sync_garmin",
    ]


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("garminSync.enabled", "true"),
        ("garminSync.enabled", "false"),
        ("garminSync.suspend", "true"),
        ("garminSync.suspend", "false"),
    ],
)
def test_helm_rejects_string_scheduler_booleans(
    tmp_path: Path,
    setting: str,
    value: str,
) -> None:
    """Scheduler flags must remain booleans even when strings look boolean."""
    result = _render_result(
        _local_chart(tmp_path),
        _active_values(),
        ((setting, value),),
    )

    assert result.returncode != 0
    assert f"{setting} must be a boolean" in result.stderr


@pytest.mark.parametrize(
    ("setting", "invalid_value"),
    [
        ("GARMIN_ENABLED", "false"),
        ("GARMIN_TOKEN_URL", ""),
        ("GARMIN_TOKEN_URL", "https://example.com/oauth/token"),
        ("GARMIN_TOKEN_URL", "https://provider.invalid/oauth/token"),
        ("GARMIN_TOKEN_URL", "${GARMIN_TOKEN_URL}"),
        ("GARMIN_TOKEN_URL", "not-a-url"),
        ("GARMIN_TOKEN_URL", "http://token.runtime.internal/oauth/token"),
        (
            "GARMIN_TOKEN_URL",
            "https://token.runtime.internal/oauth/token#fragment",
        ),
        (
            "GARMIN_TOKEN_URL",
            "https://user:password@token.runtime.internal/oauth/token",
        ),
        ("GARMIN_PROVIDER_ORIGINS", "https://provider.runtime.internal/path"),
        (
            "GARMIN_CALLBACK_ALLOWED_ORIGINS",
            "https://application.runtime.internal?query=1",
        ),
    ],
)
def test_helm_active_scheduler_rejects_incomplete_configuration(
    tmp_path: Path,
    setting: str,
    invalid_value: str,
) -> None:
    """Active render fails closed on disabled, placeholder, or malformed config."""
    values = _active_values()
    _set_env_value(values["env"], setting, invalid_value)

    result = _render_result(_local_chart(tmp_path), values)

    assert result.returncode != 0
    assert "active Garmin scheduler requires" in result.stderr


@pytest.mark.parametrize("setting", ACTIVE_GARMIN_URL_SETTINGS)
def test_helm_active_scheduler_rejects_each_blank_required_url(
    tmp_path: Path,
    setting: str,
) -> None:
    """Every provider/application URL and origin is activation-required."""
    values = _active_values()
    _set_env_value(values["env"], setting, "")

    result = _render_result(_local_chart(tmp_path), values)

    assert result.returncode != 0


def test_helm_suspended_scheduler_keeps_disabled_safe_defaults_renderable(
    tmp_path: Path,
) -> None:
    """Validation applies only when the scheduler is enabled and unsuspended."""
    values = _active_values()
    values["garminSync"]["suspend"] = True
    _set_env_value(values["env"], "GARMIN_ENABLED", "false")
    _set_env_value(
        values["env"], "GARMIN_TOKEN_URL", "https://example.com/token"
    )

    documents = _render(_local_chart(tmp_path), values)

    scheduler = next(
        document
        for document in documents
        if document["kind"] == "CronJob"
        and document["metadata"]["name"].endswith("garmin-sync")
    )
    assert scheduler["spec"]["suspend"] is True
