"""Rendered Helm contracts for the Garmin synchronization workload."""

import copy
import re
import shutil
import subprocess  # nosec: B404
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHART_ROOT = REPOSITORY_ROOT / "backend/platform/kube"
BASE_BACKEND = REPOSITORY_ROOT / "platform/k8s/base/backend.yaml"
SETTINGS = REPOSITORY_ROOT / "backend/config/settings.py"


def _local_chart(tmp_path: Path) -> Path:
    """Copy the local chart without its unrelated remote database dependency."""
    chart = tmp_path / "chart"
    shutil.copytree(CHART_ROOT, chart)
    chart_data = yaml.safe_load((chart / "Chart.yaml").read_text())
    chart_data.pop("dependencies", None)
    (chart / "Chart.yaml").write_text(yaml.safe_dump(chart_data))
    (chart / "Chart.lock").unlink(missing_ok=True)
    return chart


def _render(chart: Path, values: dict | None = None) -> list[dict]:
    """Render a chart and return non-empty Kubernetes documents."""
    command = ["helm", "template", "contract", str(chart)]
    if values is not None:
        values_path = chart.parent / "contract-values.yaml"
        values_path.write_text(yaml.safe_dump(values))
        command.extend(["--values", str(values_path)])
    result = subprocess.run(  # nosec: B603, B607
        command,
        capture_output=True,
        check=False,
        text=True,
    )
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


def test_helm_default_does_not_render_garmin_scheduler(tmp_path):
    """The supported Helm scheduler is disabled unless runtime values opt in."""
    documents = _render(_local_chart(tmp_path))

    assert not any(
        document.get("kind") == "CronJob"
        and document.get("metadata", {}).get("name", "").endswith("garmin-sync")
        for document in documents
    )


def test_helm_enabled_scheduler_matches_backend_runtime_contract(tmp_path):
    """Enabled rendering has exact Garmin env parity and safe job controls."""
    base = list(yaml.safe_load_all(BASE_BACKEND.read_text()))[0]
    environment = copy.deepcopy(base["spec"]["template"]["spec"]["containers"][0]["env"])
    values = {
        "env": environment,
        "garminSync": {
            "enabled": True,
            "suspend": False,
            "schedule": "7,37 * * * *",
            "timeZone": "Etc/UTC",
            "concurrencyPolicy": "Forbid",
            "startingDeadlineSeconds": 321,
            "successfulJobsHistoryLimit": 2,
            "failedJobsHistoryLimit": 4,
            "activeDeadlineSeconds": 654,
            "backoffLimit": 2,
            "ttlSecondsAfterFinished": 987,
        },
    }

    documents = _render(_local_chart(tmp_path), values)
    deployment = next(document for document in documents if document["kind"] == "Deployment")
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
    assert job["template"]["spec"]["serviceAccountName"] == deployment["spec"][
        "template"
    ]["spec"]["serviceAccountName"]
    assert _container(scheduler)["image"] == _container(deployment)["image"]
    assert _container(scheduler)["command"] == [
        "python",
        "manage.py",
        "sync_garmin",
    ]
