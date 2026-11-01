"""Owned HTTP client construction shared by provider and gateway adapters.

httpx parses every ``NO_PROXY`` entry as a URL pattern when ``trust_env`` is on.
A single unparseable entry (``[::1]`` is a common one, because httpx reads it as
host ``[`` with port ``:1]``) raises ``httpx.InvalidURL`` inside ``AsyncClient``,
before any request is made. Left alone that failure escapes the adapters as an
unhandled error instead of the configured fail-closed response, so construction
degrades to a client that skips environment proxies and records one warning
token. No environment value is ever logged.

A ``socks://`` proxy without httpx's optional socks extra fails the same way in
construction, so that case degrades to the validated-proxy path as well.
"""
import logging
import os

import httpx

_logger = logging.getLogger(__name__)

_PROXY_VARIABLES = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
                    "ALL_PROXY", "all_proxy")


def _validated_environment_proxy() -> httpx.URL | None:
    """First environment proxy that parses as an absolute http(s) URL."""
    for name in _PROXY_VARIABLES:
        raw = os.environ.get(name)
        if not raw:
            continue
        try:
            url = httpx.URL(raw)
        except (httpx.InvalidURL, ValueError, TypeError):
            continue
        if url.scheme in ("http", "https") and url.host:
            return url
    return None


def build_async_client(timeout, *, follow_redirects: bool = False,
                       trust_env: bool = True,
                       environment_proxy_fallback: bool = False) -> httpx.AsyncClient:
    """Build an adapter-owned client, tolerating a malformed proxy environment.

    ``environment_proxy_fallback`` keeps an outbound provider reachable through
    the host proxy when ``NO_PROXY`` itself cannot be parsed. Internal gateways
    leave it off: their addresses are local and must never be proxied.
    """
    if trust_env:
        try:
            return httpx.AsyncClient(timeout=timeout,
                                     follow_redirects=follow_redirects,
                                     trust_env=True)
        except httpx.InvalidURL:
            _logger.warning("http_client_proxy_environment_ignored")
        except ImportError:
            # A socks:// proxy in the environment without the optional socks
            # extra; httpx cannot build that transport and refuses every client.
            _logger.warning("http_client_socks_transport_unavailable")
    proxy = _validated_environment_proxy() if environment_proxy_fallback else None
    return httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects,
                             trust_env=False, proxy=proxy)
