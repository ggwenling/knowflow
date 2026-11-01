"""Test-session environment isolation.

The suite must not depend on how the host machine configures egress proxies.
httpx parses every ``NO_PROXY`` entry as a URL pattern, so a bracketed literal
such as ``[::1]`` is read as host ``[`` with port ``:1]`` and aborts client
construction inside test helpers. Such entries are dropped here; everything else
is kept verbatim. Adapter clients handle any other malformed form by degrading
(see ``knowflow_ai.http_client``).
"""
import os


def _acceptable(entry: str) -> bool:
    return "[" not in entry and "]" not in entry


def _normalized_no_proxy(raw: str) -> str:
    return ",".join(entry.strip() for entry in raw.split(",")
                    if entry.strip() and _acceptable(entry.strip()))


def pytest_configure(config):
    for name in ("NO_PROXY", "no_proxy"):
        raw = os.environ.get(name)
        if raw:
            os.environ[name] = _normalized_no_proxy(raw)
