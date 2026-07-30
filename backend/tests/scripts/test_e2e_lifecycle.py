"""Tests for secure E2E lifecycle input."""

import io

from scripts.e2e_lifecycle import LifecyclePayload, read_lifecycle_payload


def test_read_lifecycle_payload_reads_structured_stdin():
    """Lifecycle data is decoded from stdin without environment variables."""
    stream = io.StringIO(
        '{"regular_email":"regular@example.com",'
        '"regular_password":"regular-sentinel",'
        '"staff_email":"staff@example.com",'
        '"staff_password":"staff-sentinel"}'
    )

    payload = read_lifecycle_payload(stream)

    assert payload.regular_email == "regular@example.com"
    assert payload.regular_password == "regular-sentinel"
    assert payload.staff_email == "staff@example.com"
    assert payload.staff_password == "staff-sentinel"


def test_lifecycle_payload_repr_redacts_passwords():
    """Diagnostic representations do not expose either generated password."""
    payload = LifecyclePayload(
        regular_email="regular@example.com",
        regular_password="regular-sentinel",
        staff_email="staff@example.com",
        staff_password="staff-sentinel",
    )

    representation = repr(payload)

    assert "regular-sentinel" not in representation
    assert "staff-sentinel" not in representation
