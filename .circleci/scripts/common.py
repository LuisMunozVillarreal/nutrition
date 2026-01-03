def sanitize_branch_name(branch_name):
    """Sanitizes the branch name to be K8s/DNS compatible."""
    s = branch_name.lower()
    s = s.replace('/', '-')
    s = s.replace('_', '-')
    return s
