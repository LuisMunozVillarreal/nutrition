"""Food product nutrition facts finder module."""

import ast
import ipaddress
import socket
import time
from collections.abc import Mapping
from typing import Any, Dict, Set, cast
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
import urllib3
from bs4 import BeautifulSoup
from django.conf import settings
from google import genai
from google.genai import types
from requests import PreparedRequest
from requests.adapters import HTTPAdapter

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
REQUEST_TIMEOUT = (4, 10)
TOTAL_FETCH_TIMEOUT = 18
MAX_REDIRECTS = 3
STREAM_CHUNK_SIZE = 64 * 1024
ALLOWED_CONTENT_TYPES: Set[str] = {"text/html", "application/xhtml+xml"}
_ALLOWED_SCRAPER_HOSTS = {
    host.strip().lower() for host in settings.NUTRITION_SCRAPER_ALLOWED_HOSTS
}


class NutritionFactsFetchError(ValueError):
    """Raised when the nutrition URL cannot be safely fetched."""


class _ScraperHTTPSAdapter(HTTPAdapter):
    """HTTPS adapter pinned to validated destination IPs."""

    def __init__(self, resolved_ips: dict[str, str]) -> None:
        super().__init__()
        self._resolved_ips = resolved_ips

    def get_connection_with_tls_context(
        self,
        request: PreparedRequest,
        verify: bool | str | None,
        proxies: Mapping[str, str] | None = None,
        cert: str | tuple[str, str] | None = None,
    ) -> urllib3.connectionpool.ConnectionPool:
        """Create a connection pool using previously validated host resolution.

        Args:
            request: Prepared request object to resolve transport details from.
            verify: TLS verification mode passed through requests.
            proxies: Environment or call-site proxy mapping (ignored for safety).
            cert: Optional client certificate tuple or path.

        Returns:
            The HTTPS connection pool configured to connect by resolved IP while
            preserving TLS hostname checks.

        Raises:
            NutritionFactsFetchError: When request validation or destination
                resolution blocks the fetch.
        """
        # Disable environment proxy influence and explicit overrides for scraper
        # requests to avoid DNS/SSRF ambiguity.
        resolved_host = self._parse_host(request.url)
        selected_ip = self._resolved_ips.get(resolved_host)
        if selected_ip is None:
            raise NutritionFactsFetchError(
                "Scraper destination host was not validated for this request"
            )

        _ = proxies
        tls_verify: bool | str = verify if verify is not None else True
        host_params, pool_kwargs = cast(
            tuple[dict[str, Any], dict[str, Any]],
            self.build_connection_pool_key_attributes(
                request, tls_verify, cert
            ),
        )
        host_params["host"] = selected_ip
        parsed_url = urlsplit(_validated_url(request.url))
        host_params["port"] = parsed_url.port or host_params.get("port", 443)
        pool_kwargs.update(
            {
                "assert_hostname": resolved_host,
                "server_hostname": resolved_host,
            }
        )
        return self.poolmanager.connection_from_host(
            **host_params,
            pool_kwargs=pool_kwargs,
        )

    def _parse_host(self, url: str | None) -> str:
        parsed = urlsplit(_validated_url(url))
        if parsed.hostname is None:
            raise NutritionFactsFetchError("Invalid URL hostname")
        return _normalize_host(parsed.hostname)


def _validated_url(url: str | None) -> str:
    """Ensure URL strings passed to low-level transport helpers are present."""
    if not url:
        raise NutritionFactsFetchError(
            "Invalid URL provided to scraper transport"
        )
    return url


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True when IP looks public enough for scraper usage."""
    return (
        ip.is_global
        and not ip.is_multicast
        and not ip.is_unspecified
        and not ip.is_reserved
        and not ip.is_link_local
    )


def _normalize_host(hostname: str) -> str:
    """Normalize hostname for comparison and dictionary lookups."""
    return hostname.strip("[]").rstrip(".").lower()


def _validate_host_allowlist(hostname: str) -> None:
    """Reject hosts that are not explicitly configured for scraping."""
    if hostname not in _ALLOWED_SCRAPER_HOSTS:
        raise NutritionFactsFetchError(
            f"Host not in scraper allowlist: {hostname}"
        )


def _validate_host(hostname: str) -> str:
    """Validate that a hostname resolves only to public addresses."""
    name = _normalize_host(hostname)
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        if not _is_public_ip(ip):
            raise NutritionFactsFetchError(
                f"Disallowed IP address: {hostname}"
            )
        return name

    try:
        addrs = socket.getaddrinfo(
            name,
            None,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise NutritionFactsFetchError(
            f"Unresolvable host: {hostname}"
        ) from exc

    # All resolved endpoints must be publicly routable; every record is
    # inspected before any address is selected for the connection.
    resolved_records = addrs
    if (
        isinstance(addrs, tuple)
        and len(addrs) == 5
        and not isinstance(addrs[0], tuple)
    ):
        resolved_records = [addrs]
    selected_ip: str | None = None
    for _, _, _, _, address in resolved_records:
        resolved = ipaddress.ip_address(address[0])
        if not _is_public_ip(resolved):
            raise NutritionFactsFetchError(
                f"Disallowed resolved IP for host {hostname}: {resolved}"
            )
        if selected_ip is None:
            selected_ip = str(resolved)
    if selected_ip is None:
        raise NutritionFactsFetchError(
            f"No addresses resolved for host: {hostname}"
        )
    return selected_ip


def _validate_url(url: str) -> tuple[str, str, str]:
    """Validate scheme and host in a URL and enforce public address resolution."""
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise NutritionFactsFetchError("URL must use the https scheme")
    if parsed.username or parsed.password:
        raise NutritionFactsFetchError("Credentials in URL are not allowed")
    if parsed.port is not None:
        raise NutritionFactsFetchError(
            "Ports are not supported for scraping URLs"
        )

    if parsed.hostname is None:
        raise NutritionFactsFetchError("URL must include a valid host")

    normalized_host = _normalize_host(parsed.hostname)
    _validate_host_allowlist(normalized_host)
    resolved_host = _validate_host(normalized_host)
    path = parsed.path or "/"
    return (
        urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, "")),
        normalized_host,
        resolved_host,
    )


def _response_bytes(
    response: requests.Response,
    deadline: float | None = None,
) -> bytes:
    """Read response bytes safely with strict size accounting."""
    content_type = (
        response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    )
    if not content_type:
        raise NutritionFactsFetchError("No response content-type provided")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise NutritionFactsFetchError(
            f"Disallowed response type: {content_type}"
        )

    max_size = MAX_RESPONSE_BYTES
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            parsed_length = int(content_length)
        except ValueError as exc:
            raise NutritionFactsFetchError(
                "Invalid Content-Length header"
            ) from exc
        if parsed_length > max_size:
            raise NutritionFactsFetchError(
                f"Response exceeds max size: {content_length}"
            )

    collected: bytearray = bytearray()
    for chunk in response.iter_content(STREAM_CHUNK_SIZE):
        if deadline is not None:
            _assert_within_deadline(deadline)
        if not chunk:
            continue
        collected.extend(chunk)
        if len(collected) > max_size:
            raise NutritionFactsFetchError(
                f"Response exceeded {max_size} bytes while streaming"
            )
    return bytes(collected)


def _assert_within_deadline(deadline: float) -> None:
    """Raise when the remaining fetch budget is already exhausted."""
    if deadline - time.monotonic() <= 0:
        raise NutritionFactsFetchError("Fetch exceeded total time budget")


def _request_timeout(deadline: float) -> tuple[float, float]:
    """Return connect and read timeout values respecting the remaining deadline."""
    remaining = max(0.0, deadline - time.monotonic())
    if remaining <= 0:
        raise NutritionFactsFetchError("Fetch exceeded total time budget")

    connect_timeout = min(REQUEST_TIMEOUT[0], remaining)
    read_timeout = min(REQUEST_TIMEOUT[1], remaining)
    return (connect_timeout, read_timeout)


def _build_scraper_session(host_ips: dict[str, str]) -> requests.Session:
    """Create a session with strict DNS, proxy, and TLS controls."""
    session = requests.Session()
    session.trust_env = False
    session.mount("https://", _ScraperHTTPSAdapter(host_ips))
    return session


def _follow_redirects(url: str) -> bytes:
    """Follow redirects with validation and return response bytes."""
    current_url, current_host, current_host_ip = _validate_url(url)
    deadline = time.monotonic() + TOTAL_FETCH_TIMEOUT

    for _ in range(MAX_REDIRECTS + 1):
        with _build_scraper_session(
            {current_host: current_host_ip}
        ) as session:
            timeout = _request_timeout(deadline)
            with session.get(
                current_url,
                timeout=timeout,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
                    ),
                    "Connection": "close",
                },
                allow_redirects=False,
                stream=True,
                proxies={},
            ) as response:
                if (
                    300 <= response.status_code < 400
                    and response.headers.get("Location") is not None
                ):
                    (
                        current_url,
                        current_host,
                        current_host_ip,
                    ) = _resolve_redirect_url(
                        current_url,
                        response.headers["Location"],
                        current_host,
                    )
                    continue
                if 300 <= response.status_code < 400:
                    raise NutritionFactsFetchError(
                        f"Redirect missing Location header: {response.status_code}"
                    )
                if response.status_code >= 400:
                    raise NutritionFactsFetchError(
                        f"Unexpected status code: {response.status_code}"
                    )
                return _response_bytes(response, deadline)
    raise NutritionFactsFetchError(
        "Too many redirects while fetching source URL"
    )


def _resolve_redirect_url(
    current_url: str, location: str, expected_host: str
) -> tuple[str, str, str]:
    """Resolve redirect target and keep requests on the same validated host."""
    location = location.strip()
    if not location:
        raise NutritionFactsFetchError(
            "Redirect Location header missing value"
        )
    if location.startswith("//"):
        raise NutritionFactsFetchError(
            "Protocol-relative redirects are disallowed"
        )

    if "://" in location:
        next_url = location
    else:
        base = urlsplit(current_url)
        base_url = urlunsplit(
            (
                base.scheme,
                base.netloc,
                base.path,
                "",
                "",
            )
        )
        next_url = urljoin(base_url, location)

    next_url, next_host, next_host_ip = _validate_url(next_url)
    if next_host != expected_host:
        raise NutritionFactsFetchError(
            "Redirect host mismatch in follow-up request"
        )
    return next_url, next_host, next_host_ip


def get_product_nutritional_info_from_url(url: str) -> Dict[str, Any | float]:
    """Get product nutritional information from URL.

    Use https://aistudio.google.com/ to tweak the prompt.

    Args:
        url (str): URL to scrape the date from.

    Returns:
        Dict[str, str | float]

    Raises:
        ValueError: If the URL cannot be safely fetched or if the parsed
            response body is invalid.
    """
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Scrape
    try:
        html_bytes = _follow_redirects(url)
    except (NutritionFactsFetchError, requests.RequestException) as exc:
        raise ValueError(str(exc)) from exc

    soup = BeautifulSoup(html_bytes, "html.parser")
    html = soup.find("html")

    # Analyse
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        config=types.GenerateContentConfig(system_instruction="""
            You will receive an HTML page.
            This page might contain javascript.
            That page contains information of a food product.
            Extract information from that page.
            Return only code, no text or markdown language.
            Return that information as a python dictionary.
            Your answer can't contain "```python".
            Provide all values as numbers, except from the size unit.
            Use international units for the size unit.
            It's python, use None instead of null.
            That python dictionary should contain the following keys:
            - brand
            - name (without the brand in it)
            - size
            - size unit
            - servings
            - kcal
            - fat
            - saturates
            - carbohydrates
            - sugars
            - fibre
            - protein
            - salt
        """),
        contents=[str(html)],  # type: ignore[arg-type]
    )

    if response.text is None:  # pragma: no cover
        return {}
    return ast.literal_eval(response.text)


def get_food_nutrition_facts(food: str) -> Dict[str, float]:
    """Get food nutrition facts.

    Args:
        food (str): Food to get the nutrition facts from.

    Returns:
        Dict[str, float]
    """
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Analyse
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        config=types.GenerateContentConfig(system_instruction="""
            I'll give you the name of a food and I need you to give me a
            python dictionary with the nutritional facts for 100 grams of
            such food.
            Only a python dictionary, I don't need any additional text.
            Your answer can't contain "```python".
            The dictionary should have the following keys:
            - kcal
            - fat
            - saturates
            - carbohydrates
            - sugars
            - fibre
            - protein
            - salt
        """),
        contents=[food],  # type: ignore[arg-type]
    )

    if response.text is None:  # pragma: no cover
        return {}
    return ast.literal_eval(response.text)
