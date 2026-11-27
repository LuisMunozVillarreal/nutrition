"""Label photo extraction contract tests."""

import base64
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from PIL import Image

from config.schema import schema

MUTATION = """mutation Draft($photos: [String!]!) {
  extractProductLabel(photos: $photos) { draftJson }
}"""


def extract(photos, user=None):
    """Execute the mutation with request variables."""
    return schema.execute_sync(
        MUTATION,
        variable_values={"photos": photos},
        context_value=SimpleNamespace(user=user),
    )


def test_requires_authentication():
    """Reject anonymous callers before processing photos."""
    assert extract([]).errors[0].message == "Authentication required"


USER = SimpleNamespace(pk=17, is_authenticated=True)
PREFIX = "data:image/jpeg;base64,"


def jpeg(size=(12, 8)):
    """Make a real JPEG without touching storage."""
    out = BytesIO()
    Image.new("RGB", size).save(out, "JPEG")
    return out.getvalue()


def url(blob):
    """Encode bytes as a browser data URL."""
    return PREFIX + base64.b64encode(blob).decode("ascii")


@pytest.mark.parametrize(
    "case",
    [
        "none",
        "five",
        "remote",
        "encoding",
        "fake",
        "truncated",
        "large",
        "padding",
        "aggregate",
        "pixels",
    ],
)
def test_rejects_invalid_upload_before_provider(case, mocker):
    """Reject malformed and oversized inputs without a Gemini client."""
    # Given a batch violating one independent limit
    blob = jpeg()
    photos = {
        "none": [],
        "five": [url(blob)] * 5,
        "remote": ["not-inline"],
        "encoding": [PREFIX + "%"],
        "fake": [url(b"not jpeg")],
        "truncated": [url(blob[:-20])],
        "large": [url(bytes(1048580))],
        "padding": [url(bytes(1048577))],
        "aggregate": [url(blob + bytes(800000))] * 2,
        "pixels": [url(jpeg((3000, 3000)))],
    }[case]
    client = mocker.patch("google.genai.Client")
    # When an authenticated caller submits it
    result = extract(photos, USER)
    # Then input validation rejects it without spending quota
    assert result.errors and "label photos" in result.errors[0].message
    client.assert_not_called()


@pytest.fixture
def provider(mocker):
    """Replace only the outbound Gemini client."""
    return mocker.patch("google.genai.Client")


def padded_jpeg(length):
    """Add legal JPEG comment segments to reach the requested byte size."""
    blob = jpeg()
    extra = bytearray()
    while remaining := length - len(blob) - len(extra):
        chunk = min(remaining, 64000)
        extra.extend(b"\xff\xfe" + (chunk - 2).to_bytes(2) + bytes(chunk - 4))
    return blob[:2] + extra + blob[2:]


@pytest.mark.django_db
def test_four_photos_at_combined_limit_through_graphql(
    client, django_user_model, provider, settings
):
    """Fit the largest supported envelope through Django without raising its limit."""
    # Given four JPEGs and one structured provider response for a prepared serving
    user = django_user_model.objects.create_user(
        email="label@example.com",
        password="***",
        date_of_birth="2000-01-01",
        height=170,
    )
    client.force_login(user)
    settings.GEMINI_LABEL_MODEL = "test-label-model"
    blobs = [padded_jpeg(n) for n in (1048576, 262144, 131072, 131072)]
    call = provider.return_value.__enter__.return_value.models.generate_content
    call.return_value.text = json.dumps(
        {
            "name": "  Soup  ",
            "barcode": "03017620422003",
            "basis": "250 ml",
            "package": "1 L",
            "numServings": "4",
            "notes": "As prepared with water",
            "energyKcal": "85 kcal",
            "fatG": "0 g",
            "saltG": "200 mg",
        }
    )
    body = json.dumps(
        {"query": MUTATION, "variables": {"photos": list(map(url, blobs))}}
    )
    assert len(body) < settings.DATA_UPLOAD_MAX_MEMORY_SIZE == 2621440
    # When the same JSON used by the web proxy reaches the real view
    result = client.post(
        "/graphql/", body, content_type="application/json"
    ).json()
    # Then return only form fields; retain explicit zero and leave others unknown
    assert json.loads(result["data"]["extractProductLabel"]["draftJson"]) == {
        "name": "Soup",
        "brand": None,
        "barcode": "3017620422003",
        "notes": "As prepared with water",
        "size": "1",
        "sizeUnit": "l",
        "numServings": "4",
        "nutritionalInfoSize": "250",
        "nutritionalInfoUnit": "ml",
        "energyKcal": "85",
        "fatG": "0",
        "saltG": "0.2",
        "proteinG": None,
        "carbsG": None,
        "saturatedFatG": None,
        "sugarsG": None,
        "fibreG": None,
    }
    call.assert_called_once()
    options = provider.call_args.kwargs["http_options"]
    assert 0 < options.timeout <= 30000 and options.retry_options.attempts == 1
    args = call.call_args.kwargs
    assert args["model"] == "test-label-model"
    assert [part.inline_data.data for part in args["contents"].parts] == blobs
    assert args["config"].response_mime_type == "application/json"
    assert args["config"].response_json_schema["properties"]["basis"]
    assert args["config"].max_output_tokens <= 2048


@pytest.mark.parametrize("mode", ["upstream", "empty", "malformed", "array"])
def test_provider_errors_are_private(provider, mode, caplog):
    """Never reflect provider exceptions or unparseable output."""
    # Given an exception that could echo a request, or an invalid reply
    call = provider.return_value.__enter__.return_value.models.generate_content
    if mode == "upstream":
        call.side_effect = RuntimeError("private-provider-content")
    else:
        call.return_value.text = {
            "empty": None,
            "malformed": "private-provider-content",
            "array": "[]",
        }[mode]
    # When Gemini cannot supply an object
    result = extract([url(jpeg())], USER)
    # Then expose only a stable local error
    assert result.errors[0].message == "Label extraction unavailable"
    assert "private-provider-content" not in caplog.text


def test_graphql_coercion_does_not_log_variable_values(caplog):
    """Coercion can fail before the resolver sees malformed variables."""
    # Given a variable of the wrong type carrying private data
    invalid = {"photo": "private-variable-content"}
    # When GraphQL rejects it before dispatch
    result = extract([invalid], USER)
    # Then the application log contains no variable payload
    assert result.errors
    assert "private-variable-content" not in caplog.text


@pytest.fixture(autouse=True)
def isolated_quota(settings):
    """Use an isolated cache for every label quota test."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-label-extraction",
        }
    }
    cache.clear()
    yield
    cache.clear()


@pytest.mark.parametrize("scope", ["user", "global", "offline"])
def test_quota_bounds_calls(provider, scope, mocker):
    """Enforce per-user and shared limits and fail closed on cache outages."""
    # Given valid data and either repeated users, distinct users, or an outage
    photos = [url(jpeg())]
    call = provider.return_value.__enter__.return_value.models.generate_content
    call.return_value.text = "{}"
    limit = {"user": 6, "global": 30, "offline": 0}[scope]
    if scope == "offline":
        mocker.patch.object(
            cache, "add", side_effect=ConnectionError("private-cache")
        )
    # When another request arrives in the same window
    for index in range(limit + 1):
        user = SimpleNamespace(
            pk=index if scope == "global" else 1, is_authenticated=True
        )
        result = extract(photos, user)
        if index < limit:
            assert not result.errors
    # Then no provider call is made beyond the admitted budget
    assert result.errors and result.errors[0].message in {
        "Label extraction limit reached",
        "Label extraction unavailable",
    }
    assert call.call_count == limit


@pytest.mark.parametrize(
    "facts, expected",
    [
        (
            {
                "basis": "30 g",
                "energyKcal": "110 kJ",
                "proteinG": "<0.5 g",
                "fatG": True,
                "saltG": "1 mg",
                "fibreG": "1,25 g",
                "carbsG": "300000000 g",
                "brand": " ",
                "barcode": "1234",
                "sizeUnit": "g",
            },
            {
                "nutritionalInfoSize": "30",
                "energyKcal": None,
                "proteinG": None,
                "fatG": None,
                "saltG": None,
                "fibreG": "1.25",
                "carbsG": None,
                "brand": None,
                "barcode": None,
                "sizeUnit": None,
            },
        ),
        (
            {
                "basis": "100",
                "proteinG": "4 g",
                "package": "0 kg",
                "numServings": "0",
            },
            {
                "nutritionalInfoSize": None,
                "nutritionalInfoUnit": None,
                "proteinG": None,
                "size": None,
                "sizeUnit": None,
                "numServings": None,
            },
        ),
        (
            {
                "basis": "1 serving",
                "proteinG": "4 g",
                "package": "235 g",
                "notes": "After draining",
            },
            {
                "nutritionalInfoUnit": "serving",
                "proteinG": "4",
                "size": None,
                "sizeUnit": None,
                "notes": "After draining. Label package: 235 g.",
            },
        ),
        (
            {"basis": "100 ml", "package": "20 g"},
            {"size": None, "sizeUnit": None, "notes": "Label package: 20 g."},
        ),
    ],
)
def test_preserves_only_representable_facts(provider, facts, expected):
    """Keep a labelled basis; never invent equivalent weights or nutrients."""
    # Given one column, some fields may not fit the form
    call = provider.return_value.__enter__.return_value.models.generate_content
    call.return_value.text = json.dumps(facts)
    # When the returned JSON is normalized
    result = extract([url(jpeg())], USER)
    draft = json.loads(result.data["extractProductLabel"]["draftJson"])
    # Then values without a usable unit, basis or precision are not prefilled
    assert {key: draft[key] for key in expected} == expected


def test_graphql_proxy_budget_and_access_logs():
    """Keep the GraphQL POST body in memory on the backend proxy path."""
    # Given the templates used by the backend image
    roles = (
        Path(__file__).resolve().parents[2] / "platform/docker/ansible/roles"
    )
    nginx = (roles / "nginx/templates/project_nginx.conf.j2").read_text()
    gunicorn = (roles / "gunicorn/templates/gunicorn.conf.j2").read_text()
    # When checking the GraphQL location, not the unrelated admin routes
    location = nginx.partition("location ~ ^/graphql/?$ {")[2].partition("}")[
        0
    ]
    # Then bound the buffered request at the Django limit without spooling it
    assert "client_max_body_size 2560k;" in location
    assert "client_body_buffer_size 3m;" in location
    assert "access_log off;" in location
    assert "proxy_pass" in location
    # Gunicorn's default request line and referer can include GraphQL variables
    assert (
        "%(U)s" in gunicorn
        and "%(r)s" not in gunicorn
        and "%(f)s" not in gunicorn
    )
