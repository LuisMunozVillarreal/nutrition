"""Food product nutrition facts finder module."""

import ast
import ipaddress
import socket
from typing import Any, Dict, Set
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from google import genai
from google.genai import types

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
REQUEST_TIMEOUT = (4, 10)
MAX_REDIRECTS = 3
STREAM_CHUNK_SIZE = 64 * 1024
ALLOWED_CONTENT_TYPES: Set[str] = {"text/html", "application/xhtml+xml"}


class NutritionFactsFetchError(ValueError):
    """Raised when the nutrition URL cannot be safely fetched."""


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True when IP looks public enough for scraper usage."""
    return (
        ip.is_global
        and not ip.is_multicast
        and not ip.is_unspecified
        and not ip.is_reserved
        and not ip.is_link_local
    )


def _validate_host(hostname: str) -> None:
    """Validate that a hostname resolves only to public addresses."""
    name = hostname.strip("[]").rstrip(".").lower()
    try:
        ip = ipaddress.ip_address(name)
        if not _is_public_ip(ip):
            raise NutritionFactsFetchError(
                f"Disallowed IP address: {hostname}"
            )
        return
    except ValueError:
        pass

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

    # All resolved endpoints must be publicly routable.
    for _, _, _, _, address in addrs:
        resolved = ipaddress.ip_address(address[0])
        if not _is_public_ip(resolved):
            raise NutritionFactsFetchError(
                f"Disallowed resolved IP for host {hostname}: {resolved}"
            )


def _validate_url(url: str) -> str:
    """Validate scheme and host in a URL and enforce public address resolution."""
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise NutritionFactsFetchError("URL must use the https scheme")
    if parsed.username or parsed.password:
        raise NutritionFactsFetchError("Credentials in URL are not allowed")

    if parsed.hostname is None:
        raise NutritionFactsFetchError("URL must include a valid host")

    _validate_host(parsed.hostname)
    return url


def _response_bytes(response: requests.Response) -> bytes:
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
            if int(content_length) > max_size:
                raise NutritionFactsFetchError(
                    f"Response exceeds max size: {content_length}"
                )
        except ValueError as exc:
            raise NutritionFactsFetchError(
                "Invalid Content-Length header"
            ) from exc

    collected: bytearray = bytearray()
    for chunk in response.iter_content(STREAM_CHUNK_SIZE):
        if not chunk:
            continue
        collected.extend(chunk)
        if len(collected) > max_size:
            raise NutritionFactsFetchError(
                f"Response exceeded {max_size} bytes while streaming"
            )
    return bytes(collected)


def _follow_redirects(url: str) -> bytes:
    """Follow redirects with validation and return response bytes."""
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        _validate_url(current_url)
        with requests.get(
            current_url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
                ),
            },
            allow_redirects=False,
            stream=True,
        ) as response:
            if (
                300 <= response.status_code < 400
                and response.headers.get("Location") is not None
            ):
                current_url = urljoin(
                    response.url, response.headers["Location"]
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
            return _response_bytes(response)
    raise NutritionFactsFetchError(
        "Too many redirects while fetching source URL"
    )


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
        html_bytes = _follow_redirects(_validate_url(url))
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
