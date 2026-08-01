"""Regression checks for backend docker release target ordering."""

import re
from pathlib import Path


def test_backend_docker_release_target_orders_contract_before_push():
    """Guard against regressions where publish order changes."""
    repo_root = Path(__file__).resolve().parents[2]
    makefile = (repo_root / "backend" / "Makefile").read_text(encoding="utf-8")
    match = re.search(
        r"^docker-build-contract-tag-push:\n(?P<body>(?:\t.*\n)+)",
        makefile,
        flags=re.MULTILINE,
    )
    assert (
        match
    ), "Expected docker-build-contract-tag-push target in backend/Makefile."

    commands = match.group("body").splitlines()
    body_text = "\n".join(commands)
    build = body_text.index("docker-build")
    contract = body_text.index("docker-contract-test")
    tag = body_text.index("docker-tag")
    push = body_text.index("docker-push")
    assert build < contract < tag < push

    circleci_config = (repo_root / ".circleci" / "config.yml").read_text(
        encoding="utf-8"
    )
    assert (
        "make docker-build-contract-tag-push" in circleci_config
    ), "Expected CircleCI backend job to use the contract-aware docker target."
