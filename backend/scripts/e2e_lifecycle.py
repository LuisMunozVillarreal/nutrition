"""Decode E2E account lifecycle data from a process stdin stream."""

import json
from dataclasses import dataclass, field
from typing import TextIO


@dataclass(frozen=True)
class LifecyclePayload:
    """Credentials and identities scoped to one E2E lifecycle."""

    regular_email: str
    regular_password: str = field(repr=False)
    staff_email: str
    staff_password: str = field(repr=False)


def read_lifecycle_payload(stream: TextIO) -> LifecyclePayload:
    """Read and validate a structured lifecycle payload from stdin."""
    try:
        decoded = json.load(stream)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError("Invalid E2E lifecycle payload") from error

    if not isinstance(decoded, dict):
        raise RuntimeError("Invalid E2E lifecycle payload")

    field_names = (
        "regular_email",
        "regular_password",
        "staff_email",
        "staff_password",
    )
    values = {}
    for field_name in field_names:
        value = decoded.get(field_name)
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"Missing E2E lifecycle field: {field_name}")
        values[field_name] = value

    if values["regular_email"] == values["staff_email"]:
        raise RuntimeError("E2E regular and staff accounts must be distinct")

    return LifecyclePayload(**values)
