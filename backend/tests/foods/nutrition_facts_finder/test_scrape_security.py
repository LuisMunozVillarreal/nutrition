"""Tests for nutrition URL scraper hardening."""

import socket

import pytest

from apps.foods.nutrition_facts_finder import (
    MAX_RESPONSE_BYTES,
    _response_bytes,
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
def test_scrape_rejects_private_ipv6_notations(url, monkeypatch, requests_mock):
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


class _ChunkedResponse:
    """Fake response object without content length headers."""

    def __init__(self, body: bytes, content_type: str = "text/html") -> None:
        self.headers = {"Content-Type": content_type}
        self._body = body

    def iter_content(self, _chunk_size: int = 1):
        """Yield response chunks exactly as iter_content would."""
        yield self._body


def test_scrape_rejects_oversized_streamed_body():
    """Streaming responses are bounded by MAX_RESPONSE_BYTES."""
    response = _ChunkedResponse(b"x" * (MAX_RESPONSE_BYTES + 1))

    with pytest.raises(ValueError, match="Response exceeded"):
        _response_bytes(response)
