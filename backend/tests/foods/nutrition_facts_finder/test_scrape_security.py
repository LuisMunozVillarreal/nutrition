"""Tests for nutrition URL scraper hardening."""

# pylint: disable=protected-access

import socket
import time

import pytest
import requests
import urllib3.connection
import urllib3.exceptions
import urllib3.util
from requests.adapters import HTTPAdapter

from apps.foods.nutrition_facts_finder import (
    MAX_RESPONSE_BYTES,
    _build_scraper_session,
    _follow_redirects,
    _request_timeout,
    _resolve_redirect_url,
    _response_bytes,
    _ScraperHTTPSAdapter,
    _validate_host,
    _validate_url,
    _validated_url,
    get_product_nutritional_info_from_url,
)


def _public_addrinfo(*_, **__):
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 443),
        )
    ]


def _mixed_addrinfo(*args, **kwargs):
    host = args[0]
    if host == "good.example.com":
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", 443),
            )
        ]
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("10.0.0.8", 443),
        )
    ]


def _private_dns_addrinfo(*_, **__):
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("10.0.0.25", 443),
        )
    ]


def _mixed_same_host_addrinfo(*_, **__):
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 443),
        ),
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("10.0.0.9", 443),
        ),
    ]


class _HeaderOnlyResponse:
    """Fake response exposing only headers for validation tests."""

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers

    def iter_content(self, _chunk_size: int = 1):
        """Yield no content for header-only validation tests."""
        return iter(())


def test_scrape_rejects_disallowed_scrape_host(monkeypatch, requests_mock):
    """Hosts outside the allowlist are rejected before network access."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"www.ocado.com", "good.example.com"},
    )

    with pytest.raises(ValueError, match="Host not in scraper allowlist"):
        get_product_nutritional_info_from_url("https://forbidden.example.test")

    assert not requests_mock.called


@pytest.mark.parametrize("url", ["https://127.0.0.1", "https://[::1]"])
def test_scrape_rejects_private_hosts(url, monkeypatch, requests_mock):
    """Non-public host literals are blocked."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"127.0.0.1", "::1"},
    )

    with pytest.raises(ValueError, match="Disallowed"):
        get_product_nutritional_info_from_url(url)

    assert not requests_mock.called


@pytest.mark.parametrize(
    "url",
    [
        "https://[::ffff:7f00:1]",
        "https://[fd00::1]",
    ],
)
def test_scrape_rejects_private_ipv6_notations(
    url, monkeypatch, requests_mock
):
    """Private and loopback IPv6 alternative notations are blocked."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"::ffff:7f00:1", "fd00::1"},
    )

    with pytest.raises(ValueError, match="Disallowed"):
        get_product_nutritional_info_from_url(url)

    assert not requests_mock.called


def test_scrape_rejects_dns_private_host(monkeypatch, requests_mock):
    """Private DNS destinations are blocked even when the host is public-looking."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _private_dns_addrinfo,
    )
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"private.example.test"},
    )

    with pytest.raises(ValueError, match="Disallowed resolved IP"):
        get_product_nutritional_info_from_url("https://private.example.test")

    assert not requests_mock.called


def test_scrape_rejects_private_redirect_target(monkeypatch, requests_mock):
    """Private targets in redirect chains are rejected before follow-up fetch."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _mixed_addrinfo,
    )
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"good.example.com", "private.example.test"},
    )

    requests_mock.get(
        "https://good.example.com/page",
        status_code=302,
        headers={"Location": "https://private.example.test/"},
    )

    with pytest.raises(ValueError, match="Disallowed resolved IP"):
        get_product_nutritional_info_from_url("https://good.example.com/page")

    assert requests_mock.call_count == 1


def test_scrape_rejects_private_ipv6_redirect_target(
    monkeypatch, requests_mock
):
    """Private IPv6 redirect targets are rejected."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"good.example.com", "private6.example.test"},
    )

    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        lambda *args, **kwargs: (
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("fe80::1", 443),
            )
            if args[0] == "private6.example.test"
            else _mixed_addrinfo(*args, **kwargs)
        ),
    )

    requests_mock.get(
        "https://good.example.com/page",
        status_code=302,
        headers={"Location": "https://private6.example.test/"},
    )

    with pytest.raises(ValueError, match="Disallowed resolved IP"):
        get_product_nutritional_info_from_url("https://good.example.com/page")

    assert requests_mock.call_count == 1


def test_scrape_rejects_redirect_to_different_host(monkeypatch, requests_mock):
    """Redirects that change hostname are rejected."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _public_addrinfo,
    )
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"good.example.com", "other.example.com"},
    )

    requests_mock.get(
        "https://good.example.com/page",
        status_code=302,
        headers={"Location": "https://other.example.com/"},
    )

    with pytest.raises(ValueError, match="Redirect host mismatch"):
        get_product_nutritional_info_from_url("https://good.example.com/page")

    assert requests_mock.call_count == 1


def test_scrape_rejects_redirect_chain_too_long(monkeypatch, requests_mock):
    """Chains that exceed the redirect limit are rejected."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _public_addrinfo,
    )

    for index in range(4):
        requests_mock.get(
            f"https://public.example.com/{index}",
            status_code=302,
            headers={"Location": f"https://public.example.com/{index + 1}"},
        )

    requests_mock.get(
        "https://public.example.com/4",
        status_code=302,
        headers={"Location": "https://public.example.com/5"},
    )

    with pytest.raises(ValueError, match="Too many redirects"):
        get_product_nutritional_info_from_url("https://public.example.com/0")

    assert requests_mock.call_count == 4


def test_scrape_rejects_oversized_body(monkeypatch, requests_mock):
    """Large HTML responses are rejected before parsing into BeautifulSoup."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _public_addrinfo,
    )
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.MAX_RESPONSE_BYTES",
        128,
    )

    requests_mock.get(
        "https://public.example.com/oversized",
        status_code=200,
        headers={"Content-Type": "text/html"},
        text="x" * 512,
    )

    with pytest.raises(ValueError, match="exceeded"):
        get_product_nutritional_info_from_url(
            "https://public.example.com/oversized"
        )


def test_validate_url_preserves_query_and_drops_fragment(monkeypatch):
    """Query values are kept while fragments are stripped from requests."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"public.example.com"},
    )
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _public_addrinfo,
    )

    sanitized_url, host, ip = _validate_url(
        "https://public.example.com/page?foo=bar&baz=1#ignored"
    )

    assert host == "public.example.com"
    assert ip == "93.184.216.34"
    assert sanitized_url == "https://public.example.com/page?foo=bar&baz=1"


def test_resolve_redirect_url_preserves_query_and_drops_fragment(monkeypatch):
    """Redirect URLs are resolved with the same query rules as initial URLs."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"good.example.com"},
    )
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _public_addrinfo,
    )

    normalized_url, host, ip = _resolve_redirect_url(
        "https://good.example.com/page?foo=bar",
        "/next?query=1#ignored",
        "good.example.com",
    )

    assert host == "good.example.com"
    assert ip == "93.184.216.34"
    assert normalized_url == "https://good.example.com/next?query=1"


def test_follow_redirect_preserves_query_between_hops(
    monkeypatch, requests_mock
):
    """Redirects should keep query parameters from redirect targets."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"good.example.com"},
    )
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _public_addrinfo,
    )

    requests_mock.get(
        "https://good.example.com/start?query=first#ignored",
        status_code=302,
        headers={"Location": "/next?query=second#ignored"},
    )
    requests_mock.get(
        "https://good.example.com/next?query=second",
        status_code=200,
        headers={"Content-Type": "text/html"},
        text="<html><body>ok</body></html>",
    )

    html = _follow_redirects(
        "https://good.example.com/start?query=first#ignored"
    )

    assert html == b"<html><body>ok</body></html>"
    assert requests_mock.call_count == 2
    assert (
        requests_mock.request_history[0].url
        == "https://good.example.com/start?query=first"
    )
    assert (
        requests_mock.request_history[1].url
        == "https://good.example.com/next?query=second"
    )


def test_dns_rebinding_is_blocked_by_single_hop_resolution(
    monkeypatch, requests_mock
):
    """Resolver is called once per hop; transport does not re-resolve.

    The adapter receives selected IPs from _validate_url validation.
    """
    calls: list[str] = []

    def rebinding_lookup(*args: object, **kwargs: object):
        host = args[0]
        calls.append(str(host))
        if len(calls) > 1:
            raise AssertionError("DNS lookup called more than once per hop")
        return _public_addrinfo()

    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        rebinding_lookup,
    )
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"good.example.com"},
    )
    requests_mock.get(
        "https://good.example.com/page",
        status_code=200,
        headers={"Content-Type": "text/html"},
        text="<html><body>ok</body></html>",
    )

    payload = _follow_redirects(
        "https://good.example.com/page#ignored-fragment"
    )

    assert payload == b"<html><body>ok</body></html>"
    assert calls == ["good.example.com"]


def test_scraper_adapter_uses_resolved_ip_and_preserves_tls_hostname(
    monkeypatch,
):
    """Adapter connects by resolved IP while still validating TLS for the host."""
    adapter = _ScraperHTTPSAdapter({"good.example.com": "203.0.113.10"})
    request = requests.Request(
        "GET", "https://good.example.com/page?x=1#frag"
    ).prepare()

    captures: dict[str, object] = {}

    def fake_build_pool_keys(self, prepared_request, verify, cert=None):
        captures["verify"] = verify
        captures["cert"] = cert
        return (
            {
                "host": "should-be-overwritten",
                "port": 443,
            },
            {},
        )

    def fake_connection_from_host(**kwargs):
        captures["pool_kwargs"] = kwargs["pool_kwargs"]
        captures["connection_host"] = kwargs["host"]
        captures["connection_port"] = kwargs["port"]
        return object()

    monkeypatch.setattr(
        HTTPAdapter,
        "build_connection_pool_key_attributes",
        fake_build_pool_keys,
    )
    monkeypatch.setattr(
        adapter.poolmanager,
        "connection_from_host",
        fake_connection_from_host,
    )

    adapter.get_connection_with_tls_context(
        request,
        verify=True,
        proxies={"https": "http://bad-proxy.example"},
        cert=None,
    )

    assert captures["connection_host"] == "203.0.113.10"
    assert captures["connection_port"] == 443
    assert captures["pool_kwargs"]["assert_hostname"] == "good.example.com"
    assert captures["pool_kwargs"]["server_hostname"] == "good.example.com"


def test_scraper_adapter_pins_connection_to_validated_ip(monkeypatch):
    """The adapter builds a real pool pinned to the validated IP."""
    recorded: dict[str, object] = {}

    def recording_connect(self):
        """Record connection target attributes and abort the attempt."""
        recorded["host"] = self.host
        recorded["assert_hostname"] = getattr(self, "assert_hostname", None)
        recorded["server_hostname"] = getattr(self, "server_hostname", None)
        raise urllib3.exceptions.ConnectTimeoutError("instrumented")

    monkeypatch.setattr(
        urllib3.connection.HTTPSConnection, "connect", recording_connect
    )
    adapter = _ScraperHTTPSAdapter({"good.example.com": "203.0.113.10"})
    request = requests.Request(
        "GET", "https://good.example.com/page?x=1"
    ).prepare()
    pool = adapter.get_connection_with_tls_context(
        request, verify=True, proxies=None, cert=None
    )
    with pytest.raises(urllib3.exceptions.ConnectTimeoutError):
        pool.urlopen(
            "GET",
            "/page?x=1",
            retries=False,
            timeout=urllib3.util.Timeout(connect=4, read=4),
        )

    assert recorded["host"] == "203.0.113.10"
    assert recorded["assert_hostname"] == "good.example.com"
    assert recorded["server_hostname"] == "good.example.com"


def test_validate_url_rejects_unsupported_url_forms():
    """Non-https schemes, credentials, and explicit ports are rejected."""
    unsupported_urls = [
        ("http://good.example.com/page", "https scheme"),
        (
            "https://user:pass@good.example.com/page",
            "Credentials in URL",
        ),
        (
            "https://good.example.com:8443/page",
            "Ports are not supported",
        ),
    ]
    for url, message in unsupported_urls:
        with pytest.raises(ValueError, match=message):
            _validate_url(url)


def test_validate_host_rejects_mixed_records(monkeypatch):
    """Every resolved record must be public; mixed hosts are rejected."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _mixed_same_host_addrinfo,
    )

    with pytest.raises(ValueError, match="Disallowed resolved IP"):
        _validate_url("https://good.example.com/page")


def test_resolve_redirect_url_rejects_protocol_relative():
    """Protocol-relative redirect targets are rejected."""
    with pytest.raises(
        ValueError, match="Protocol-relative redirects are disallowed"
    ):
        _resolve_redirect_url(
            "https://good.example.com/page",
            "//other.example.com/next",
            "good.example.com",
        )


def test_follow_redirects_rejects_missing_location(monkeypatch, requests_mock):
    """Redirect responses without a Location header are rejected."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _public_addrinfo,
    )
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"good.example.com"},
    )
    requests_mock.get("https://good.example.com/page", status_code=302)

    with pytest.raises(ValueError, match="Redirect missing Location header"):
        _follow_redirects("https://good.example.com/page")


def test_response_bytes_rejects_disallowed_content_type():
    """Non-HTML content types are rejected before parsing."""
    with pytest.raises(ValueError, match="Disallowed response type"):
        _response_bytes(
            _HeaderOnlyResponse({"Content-Type": "application/pdf"})
        )


def test_response_bytes_rejects_invalid_content_length():
    """Malformed Content-Length headers are rejected."""
    with pytest.raises(ValueError, match="Invalid Content-Length"):
        _response_bytes(
            _HeaderOnlyResponse(
                {"Content-Type": "text/html", "Content-Length": "abc"}
            )
        )


def test_scraper_session_disables_environment_proxies():
    """Scraper sessions do not read proxy settings from process environment."""
    session = _build_scraper_session({"good.example.com": "203.0.113.11"})

    assert session.trust_env is False


class _ChunkedResponse:
    """Fake response object without content length headers."""

    def __init__(
        self,
        chunks: list[bytes],
        clock: "MonotonicClock",
        content_type: str = "text/html",
    ) -> None:
        self.headers = {"Content-Type": content_type}
        self._chunks = chunks
        self._clock = clock

    def iter_content(self, _chunk_size: int = 1):
        """Yield response chunks with simulated delays."""
        for index, chunk in enumerate(self._chunks):
            if index > 0:
                self._clock.advance(0.6)
            yield chunk


class MonotonicClock:
    """Deterministic monotonic-clock shim for timeout regressions."""

    def __init__(self, start: float = 0.0) -> None:
        self._time = start

    def __call__(self) -> float:
        """Return the current synthetic monotonic timestamp.

        Returns:
            float: The current monotonic timestamp value.
        """
        return self._time

    def advance(self, seconds: float) -> None:
        """Advance the synthetic monotonic clock by a fixed interval."""
        self._time += seconds


def test_response_bytes_respects_total_deadline_with_slow_chunks(monkeypatch):
    """Simulated slow chunking must honor the absolute monotonic fetch timeout."""
    clock = MonotonicClock()
    response = _ChunkedResponse([b"chunk-1", b"chunk-2"], clock)

    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.time.monotonic",
        clock,
    )

    with pytest.raises(ValueError, match="Fetch exceeded total time budget"):
        _response_bytes(response, deadline=0.5)


def test_scrape_rejects_oversized_streamed_body():
    """Streaming responses are bounded by MAX_RESPONSE_BYTES."""
    response = _ChunkedResponse(
        [b"x" * (MAX_RESPONSE_BYTES + 1)], MonotonicClock()
    )

    with pytest.raises(ValueError, match="Response exceeded"):
        _response_bytes(response, deadline=time.monotonic() + 5)


def test_adapter_rejects_unvalidated_destination_host():
    """A host not pinned in the session map is refused at send time."""
    adapter = _build_scraper_session(
        {"good.example.com": "203.0.113.11"}
    ).get_adapter("https://good.example.com/")
    request = requests.Request("GET", "https://evil.example.com/").prepare()

    with pytest.raises(ValueError, match="was not validated"):
        adapter.send(request)


def test_parse_host_rejects_url_without_hostname():
    """URLs that cannot yield a hostname are rejected in the transport."""
    adapter = _build_scraper_session(
        {"good.example.com": "203.0.113.11"}
    ).get_adapter("https://good.example.com/")

    with pytest.raises(ValueError, match="Invalid URL hostname"):
        adapter._parse_host("https:///path")


@pytest.mark.parametrize("url", [None, ""])
def test_validated_url_rejects_empty_input(url):
    """Empty transport URLs fail closed."""
    with pytest.raises(
        ValueError, match="Invalid URL provided to scraper transport"
    ):
        _validated_url(url)


def test_validate_host_accepts_public_ip_literal():
    """Public IP literals are returned without DNS resolution."""
    assert _validate_host("93.184.216.34") == "93.184.216.34"


def test_validate_host_reports_unresolvable_hostname(monkeypatch):
    """DNS failures surface as fetch errors, not raw socket errors."""

    def _unresolvable(*args, **kwargs):
        raise socket.gaierror("name or service not known")

    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _unresolvable,
    )

    with pytest.raises(ValueError, match="Unresolvable host"):
        _validate_host("unresolvable.example.com")


def test_validate_host_rejects_empty_resolution(monkeypatch):
    """A host that resolves to no addresses is rejected."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        lambda *args, **kwargs: [],
    )

    with pytest.raises(ValueError, match="No addresses resolved"):
        _validate_host("no-records.example.com")


def test_validate_url_rejects_missing_hostname():
    """URLs without a hostname fail closed."""
    with pytest.raises(ValueError, match="URL must include a valid host"):
        _validate_url("https://")


def test_response_bytes_rejects_missing_content_type():
    """Responses without a Content-Type are refused."""
    with pytest.raises(ValueError, match="No response content-type"):
        _response_bytes(_HeaderOnlyResponse({}))


def test_response_bytes_rejects_oversized_content_length():
    """A Content-Length above the budget is refused before streaming."""
    response = _HeaderOnlyResponse(
        {
            "Content-Type": "text/html",
            "Content-Length": str(MAX_RESPONSE_BYTES + 1),
        }
    )

    with pytest.raises(ValueError, match="exceeds max size"):
        _response_bytes(response)


def test_response_bytes_accepts_valid_content_length():
    """A Content-Length within budget passes the header check."""
    response = _HeaderOnlyResponse(
        {
            "Content-Type": "text/html",
            "Content-Length": "1024",
        }
    )

    assert _response_bytes(response) == b""


def test_response_bytes_skips_empty_chunks():
    """Empty stream chunks are skipped without truncating the body."""
    response = _ChunkedResponse([b"a", b"", b"b"], MonotonicClock())

    assert _response_bytes(response) == b"ab"


def test_request_timeout_exhausted():
    """A fully consumed deadline refuses to schedule another request."""
    with pytest.raises(ValueError, match="Fetch exceeded total time budget"):
        _request_timeout(0.0)


def test_follow_redirects_rejects_unexpected_status(
    monkeypatch, requests_mock
):
    """Non-redirect error statuses surface as fetch errors."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"good.example.com"},
    )
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _public_addrinfo,
    )
    requests_mock.get(
        "https://good.example.com/page",
        status_code=500,
        headers={"Content-Type": "text/html"},
    )

    with pytest.raises(ValueError, match="Unexpected status code"):
        get_product_nutritional_info_from_url("https://good.example.com/page")


def test_follow_redirects_rejects_empty_location(monkeypatch, requests_mock):
    """Redirects without a Location value fail closed."""
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder._ALLOWED_SCRAPER_HOSTS",
        {"good.example.com"},
    )
    monkeypatch.setattr(
        "apps.foods.nutrition_facts_finder.socket.getaddrinfo",
        _public_addrinfo,
    )
    requests_mock.get(
        "https://good.example.com/page",
        status_code=302,
        headers={"Content-Type": "text/html", "Location": ""},
    )

    with pytest.raises(
        ValueError, match="Redirect Location header missing value"
    ):
        get_product_nutritional_info_from_url("https://good.example.com/page")
