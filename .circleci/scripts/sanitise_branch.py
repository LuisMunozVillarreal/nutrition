"""Common utilities for CircleCI scripts."""

import hashlib
import sys

# Max length for the branch part is 34 characters to strictly fit
# within the 64 char SSL CN limit. The CN format is:
# staging--<sanitized_branch>.<BASE_DOMAIN>
# 64 - 9 (staging--) - 1 (.) - 20 (~BASE_DOMAIN) = 34
MAX_LENGTH = 34


def sanitise_branch_name(branch_name: str) -> str:
    """Sanitise the branch name to be K8s/DNS compatible.

    Args:
        branch_name (str): The raw branch name (e.g., 'feature/foo_bar').

    Returns:
        str: A sanitized string safe for K8s resource names.
    """
    s = branch_name.lower()
    s = s.replace("/", "-")
    s = s.replace("_", "-")
    s = s.replace(".", "-")

    if len(s) > MAX_LENGTH:
        # Create a hash of the original branch name for uniqueness
        hasher = hashlib.sha1(
            branch_name.encode("utf-8"), usedforsecurity=False
        )
        branch_hash = hasher.hexdigest()[:7]

        # Truncate to 26 chars to leave room for the hash (26 + 1 + 7 = 34)
        s = s[:26].rstrip("-")
        s = f"{s}-{branch_hash}"

    return s


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(sanitise_branch_name(sys.argv[1]))
