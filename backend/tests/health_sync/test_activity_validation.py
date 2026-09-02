"""Validation tests for the Health Connect activity upload contract."""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.health_sync.services import parse_activity_records

VALID_RECORD = {
    "source_record_id": "garmin-1",
    "source_modified_at": None,  # filled per-test with a recent timestamp
    "start_time": None,
    "end_time": None,
    "type": "walk",
    "active_kcals": 300,
    "distance_km": 5.25,
}


def _valid_record(**overrides):
    """Build a valid record with sane timestamps for the current instant."""
    now = timezone.now()
    start = now - datetime.timedelta(hours=1)
    end = start + datetime.timedelta(minutes=30)
    record = {
        "source_record_id": "garmin-1",
        "source_modified_at": now.isoformat(),
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "type": "walk",
        "active_kcals": 300,
        "distance_km": 5.25,
    }
    record.update(overrides)
    return record


def _payload(*records):
    return {"records": list(records)}


def test_parse_activity_rejects_non_object_payload():
    """Verify activity payload validation behavior."""
    with pytest.raises(ValueError, match="records must be a list"):
        parse_activity_records([])
    with pytest.raises(ValueError, match="records must be a list"):
        parse_activity_records({"records": "not-a-list"})


def test_parse_activity_rejects_more_than_100_records():
    """Verify activity payload validation behavior."""
    with pytest.raises(ValueError, match="at most 100"):
        parse_activity_records(_payload(*([{}] * 101)))


def test_parse_activity_accepts_exactly_100_records():
    """Verify activity payload validation behavior."""
    now = timezone.now()
    start = now - datetime.timedelta(hours=1)
    end = start + datetime.timedelta(minutes=5)
    records = [
        {
            "source_record_id": f"garmin-{index}",
            "source_modified_at": now.isoformat(),
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "type": "walk",
            "active_kcals": 1,
            "distance_km": None,
        }
        for index in range(100)
    ]
    parsed = parse_activity_records(_payload(*records))
    assert len(parsed) == 100


def test_parse_activity_rejects_non_object_record():
    """Verify activity payload validation behavior."""
    with pytest.raises(ValueError, match="each record must be an object"):
        parse_activity_records(_payload(None))


def test_parse_activity_rejects_duplicate_source_record_ids():
    """Verify activity payload validation behavior."""
    with pytest.raises(ValueError, match="unique source_record_id"):
        parse_activity_records(
            _payload(
                _valid_record(), _valid_record(source_record_id="garmin-1")
            )
        )


@pytest.mark.parametrize(
    "source_record_id",
    ["", "   ", "x" * 256, None, 123, True],
)
def test_parse_activity_rejects_invalid_source_record_id(source_record_id):
    """Verify activity payload validation behavior."""
    with pytest.raises(ValueError, match="source_record_id"):
        parse_activity_records(
            _payload(_valid_record(source_record_id=source_record_id))
        )


def test_parse_activity_accepts_boundary_source_record_id():
    """Verify activity payload validation behavior."""
    record = _valid_record(source_record_id="x" * 255)
    parsed = parse_activity_records(_payload(record))
    assert parsed[0].source_record_id == "x" * 255


@pytest.mark.parametrize(
    "source_modified_at",
    [
        "2026-09-01T10:00:00",  # naive
        "not-a-timestamp",
        None,
        123456,
        True,
    ],
)
def test_parse_activity_rejects_invalid_source_modified_at(source_modified_at):
    """Verify activity payload validation behavior."""
    with pytest.raises(ValueError, match="source_modified_at"):
        parse_activity_records(
            _payload(_valid_record(source_modified_at=source_modified_at))
        )


def test_parse_activity_rejects_future_source_modified_at():
    """Verify activity payload validation behavior."""
    future = timezone.now() + datetime.timedelta(minutes=6)
    with pytest.raises(
        ValueError, match="source_modified_at cannot be in the future"
    ):
        parse_activity_records(
            _payload(_valid_record(source_modified_at=future.isoformat()))
        )


@pytest.mark.parametrize("field", ["start_time", "end_time"])
@pytest.mark.parametrize(
    "value", ["2026-09-01T10:00:00", "not-a-timestamp", None, 123, True]
)
def test_parse_activity_rejects_invalid_timestamps(field, value):
    """Verify activity payload validation behavior."""
    with pytest.raises(ValueError, match=field):
        parse_activity_records(_payload(_valid_record(**{field: value})))


def test_parse_activity_rejects_start_not_before_end():
    """Verify activity payload validation behavior."""
    now = timezone.now()
    with pytest.raises(ValueError, match="start_time must be before end_time"):
        parse_activity_records(
            _payload(
                _valid_record(
                    start_time=now.isoformat(),
                    end_time=(now - datetime.timedelta(minutes=1)).isoformat(),
                )
            )
        )


def test_parse_activity_rejects_duration_over_24_hours():
    """Verify activity payload validation behavior."""
    start = timezone.now() - datetime.timedelta(hours=25)
    end = timezone.now()
    with pytest.raises(ValueError, match="duration must not exceed 24 hours"):
        parse_activity_records(
            _payload(
                _valid_record(
                    start_time=start.isoformat(), end_time=end.isoformat()
                )
            )
        )


def test_parse_activity_allows_exactly_24_hour_duration():
    """Verify activity payload validation behavior."""
    end = timezone.now()
    start = end - datetime.timedelta(hours=24)
    parsed = parse_activity_records(
        _payload(
            _valid_record(
                start_time=start.isoformat(), end_time=end.isoformat()
            )
        )
    )
    assert parsed[0].duration == datetime.timedelta(hours=24)


def test_parse_activity_derives_date_time_and_duration():
    """Verify activity payload validation behavior."""
    record = _valid_record(
        start_time="2026-09-01T09:15:00+00:00",
        end_time="2026-09-01T09:45:00+00:00",
    )
    parsed = parse_activity_records(_payload(record))[0]
    assert parsed.date == datetime.date(2026, 9, 1)
    assert parsed.time == datetime.time(9, 15)
    assert parsed.duration == datetime.timedelta(minutes=30)


def test_parse_activity_uses_start_time_offset_not_server_timezone():
    # 2026-09-01T00:30+05:00 is still 2026-08-31 in UTC; the session day and
    # wall-clock time must follow the upload's own offset, not the server zone.
    """Verify activity payload validation behavior."""
    record = _valid_record(
        start_time="2026-09-01T00:30:00+05:00",
        end_time="2026-09-01T01:00:00+05:00",
    )
    parsed = parse_activity_records(_payload(record))[0]
    assert parsed.date == datetime.date(2026, 9, 1)
    assert parsed.time == datetime.time(0, 30)
    assert parsed.duration == datetime.timedelta(minutes=30)


def test_parse_activity_does_not_trust_client_duration_or_date():
    # Extra fields are ignored; duration/date derive from timestamps only.
    """Verify activity payload validation behavior."""
    record = _valid_record(
        start_time="2026-09-01T09:15:00+00:00",
        end_time="2026-09-01T09:45:00+00:00",
        duration="9999:99:99",
        date="1900-01-01",
    )
    parsed = parse_activity_records(_payload(record))[0]
    assert parsed.duration == datetime.timedelta(minutes=30)
    assert parsed.date == datetime.date(2026, 9, 1)


@pytest.mark.parametrize("exercise_type", ["swim", "", "WALK", None, 1, True])
def test_parse_activity_rejects_invalid_type(exercise_type):
    """Verify activity payload validation behavior."""
    with pytest.raises(ValueError, match="type must be one of"):
        parse_activity_records(_payload(_valid_record(type=exercise_type)))


@pytest.mark.parametrize("kcals", [True, -1, 100001, "300", None, 1.5])
def test_parse_activity_rejects_invalid_kcals(kcals):
    """Verify activity payload validation behavior."""
    with pytest.raises(ValueError, match="active_kcals"):
        parse_activity_records(_payload(_valid_record(active_kcals=kcals)))


def test_parse_activity_accepts_kcals_boundaries():
    """Verify activity payload validation behavior."""
    assert (
        parse_activity_records(_payload(_valid_record(active_kcals=0)))[
            0
        ].active_kcals
        == 0
    )
    assert (
        parse_activity_records(_payload(_valid_record(active_kcals=100000)))[
            0
        ].active_kcals
        == 100000
    )


@pytest.mark.parametrize(
    "distance", [-0.01, -1, 100000000.0, "5", True, float("nan")]
)
def test_parse_activity_rejects_invalid_distance(distance):
    """Verify activity payload validation behavior."""
    with pytest.raises(ValueError, match="distance_km"):
        parse_activity_records(_payload(_valid_record(distance_km=distance)))


def test_parse_activity_rejects_infinite_distance():
    """Verify activity payload validation behavior."""
    with pytest.raises(ValueError, match="distance_km"):
        parse_activity_records(
            _payload(_valid_record(distance_km=float("inf")))
        )


def test_parse_activity_rounds_health_connect_distance_to_model_precision():
    """Verify activity payload validation behavior."""
    parsed = parse_activity_records(
        _payload(_valid_record(distance_km=5.123456))
    )[0]
    assert parsed.distance == Decimal("5.12")


def test_parse_activity_accepts_null_and_zero_distance():
    """Verify activity payload validation behavior."""
    assert (
        parse_activity_records(_payload(_valid_record(distance_km=None)))[
            0
        ].distance
        is None
    )
    assert parse_activity_records(_payload(_valid_record(distance_km=0)))[
        0
    ].distance == Decimal("0")


def test_parse_activity_accepts_distance_boundary():
    """Verify activity payload validation behavior."""
    parsed = parse_activity_records(
        _payload(_valid_record(distance_km=99999999.99))
    )[0]
    assert parsed.distance == Decimal("99999999.99")


def test_parse_activity_accepts_integer_distance():
    """Verify activity payload validation behavior."""
    parsed = parse_activity_records(_payload(_valid_record(distance_km=7)))[0]
    assert parsed.distance == Decimal("7")


def test_parse_activity_rejects_dates_outside_sync_window():
    """Verify activity payload validation behavior."""
    today = timezone.localdate()
    too_old = today - datetime.timedelta(days=31)
    too_far_ahead = today + datetime.timedelta(days=2)
    old_start = datetime.datetime.combine(
        too_old, datetime.time(10, 0), tzinfo=datetime.timezone.utc
    )
    ahead_start = datetime.datetime.combine(
        too_far_ahead, datetime.time(10, 0), tzinfo=datetime.timezone.utc
    )

    with pytest.raises(ValueError, match="outside the supported sync window"):
        parse_activity_records(
            _payload(
                _valid_record(
                    start_time=old_start.isoformat(),
                    end_time=(
                        old_start + datetime.timedelta(minutes=5)
                    ).isoformat(),
                )
            )
        )

    with pytest.raises(ValueError, match="cannot be in the future"):
        parse_activity_records(
            _payload(
                _valid_record(
                    start_time=ahead_start.isoformat(),
                    end_time=(
                        ahead_start + datetime.timedelta(minutes=5)
                    ).isoformat(),
                )
            )
        )


def test_parse_activity_accepts_one_day_timezone_skew():
    """Verify activity payload validation behavior."""
    today = timezone.localdate()
    tomorrow = today + datetime.timedelta(days=1)
    tomorrow_start = datetime.datetime.combine(
        tomorrow, datetime.time(10, 0), tzinfo=datetime.timezone.utc
    )
    parsed = parse_activity_records(
        _payload(
            _valid_record(
                start_time=tomorrow_start.isoformat(),
                end_time=(
                    tomorrow_start + datetime.timedelta(minutes=5)
                ).isoformat(),
            )
        )
    )[0]
    assert parsed.date == tomorrow
