"""Common utilities for CircleCI scripts."""


def sanitize_branch_name(branch_name: str) -> str:
    """Sanitise the branch name to be K8s/DNS compatible.

    Args:
        branch_name (str): The raw branch name (e.g., 'feature/foo_bar').

    Returns:
        str: A sanitized string safe for K8s resource names.
    """
    s = branch_name.lower()
    s = s.replace("/", "-")
    s = s.replace("_", "-")
    return s
