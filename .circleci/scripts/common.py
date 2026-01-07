"""Common utilities for CircleCI scripts."""

import hashlib

# Max length for the branch part is 44 characters to strictly fit
# within the 63 char limit when combined with "nutrition-staging--"
# 63 - 19 = 44
MAX_LENGTH = 44


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

    if len(s) > MAX_LENGTH:
        # Create a hash of the original branch name for uniqueness
        hasher = hashlib.sha1(
            branch_name.encode("utf-8"), usedforsecurity=False
        )
        branch_hash = hasher.hexdigest()[:7]

        # Truncate to 36 chars to leave room for the hash (36 + 1 + 7 = 44)
        s = s[:36].rstrip("-")
        s = f"{s}-{branch_hash}"

    return s
