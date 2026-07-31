"""Common utilities for CircleCI scripts."""

import hashlib
import re
import sys

MAX_LENGTH = 34
HASH_LENGTH = 7
DNS_LABEL_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


def _normalize_branch_name(branch_name: str) -> str:
    """Normalize Git branch names to lowercase DNS-label safe characters.

    Replaces invalid characters with '-' and collapses consecutive separators.
    """
    normalized = re.sub(r"[^a-z0-9-]", "-", branch_name.lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        normalized = "branch"
    return normalized


def _append_stable_hash(normalized_branch: str, branch_name: str) -> str:
    """Append a stable hash to a normalized branch identifier."""
    branch_hash = hashlib.sha1(
        branch_name.encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:HASH_LENGTH]
    suffix = f"-{branch_hash}"
    max_base_length = MAX_LENGTH - len(suffix)

    base = normalized_branch[:max_base_length].strip("-")
    if not base:
        base = "branch"

    return f"{base}{suffix}"


def sanitise_branch_name(branch_name: str) -> str:
    """Sanitise the branch name to be K8s/DNS compatible.

    Args:
        branch_name (str): The raw branch name (e.g., 'feature/foo_bar').

    Returns:
        str: A sanitized string safe for K8s resource names.

    Raises:
        ValueError: If the normalised and hashed name is not a valid DNS label.
    """
    normalised = _normalize_branch_name(branch_name)
    sanitized = _append_stable_hash(normalised, branch_name)

    if not DNS_LABEL_RE.fullmatch(sanitized):
        raise ValueError(f"Could not normalise branch name: {branch_name}")

    return sanitized


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(sanitise_branch_name(sys.argv[1]))
