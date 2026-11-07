"""Bounded provider retry for transient 5xx / timeout / 429 failures.

Budget reservations stay inside the per-attempt callable, so every retry is a
new reservation and can never bypass the ledger's soft stop. 4xx is final.
"""
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import asyncio
import logging
import math
import os
import time

from .adapters import ProcessingError
from .config import ConfigurationError

_logger = logging.getLogger(__name__)


def _read_int(env, name, default):
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ConfigurationError("PROVIDER_RETRY_CONFIGURATION_INVALID") from None
    return value


def _read_float(env, name, default):
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ConfigurationError("PROVIDER_RETRY_CONFIGURATION_INVALID") from None
    return value


@dataclass(frozen=True)
class ProviderRetryPolicy:
    max_attempts: int = 3
    base_seconds: float = 0.5
    total_seconds: float = 25.0

    def __post_init__(self):
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 5:
            raise ConfigurationError("PROVIDER_RETRY_CONFIGURATION_INVALID")
        if (not math.isfinite(self.base_seconds) or not 0 <= self.base_seconds <= 5):
            raise ConfigurationError("PROVIDER_RETRY_CONFIGURATION_INVALID")
        if (not math.isfinite(self.total_seconds) or not 0 <= self.total_seconds <= 60):
            raise ConfigurationError("PROVIDER_RETRY_CONFIGURATION_INVALID")

    @classmethod
    def from_environment(cls, environ=None):
        env = os.environ if environ is None else environ
        return cls(
            max_attempts=_read_int(env, "KNOWFLOW_PROVIDER_RETRY_MAX_ATTEMPTS", 3),
            base_seconds=_read_float(env, "KNOWFLOW_PROVIDER_RETRY_BASE_SECONDS", 0.5),
            total_seconds=_read_float(env, "KNOWFLOW_PROVIDER_RETRY_TOTAL_SECONDS", 25.0),
        )


def retry_after_seconds(value, *, now=None):
    """Parse an HTTP Retry-After value; malformed input means "no hint"."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except (TypeError, ValueError):
        try:
            when = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
        if when is None:
            return None
        current = time.time() if now is None else now
        seconds = when.timestamp() - current
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def retry_delay(policy, exc, attempt):
    if getattr(exc, "retry_after", None) is not None:
        return exc.retry_after
    return policy.base_seconds * (2 ** (attempt - 1))


def _reason(exc):
    return getattr(exc, "retry_reason", None) or exc.code


async def run_provider_with_retry(operation, *, policy, request_id, provider):
    """Call ``operation`` up to ``policy.max_attempts`` times.

    ``operation`` must perform its own budget reservation immediately before
    the HTTP request. Any ``ProcessingError`` with ``retryable=False`` is final.
    """
    started = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        try:
            return await operation()
        except ProcessingError as exc:
            retryable = bool(getattr(exc, "retryable", False))
            if not retryable:
                raise
            if attempt >= policy.max_attempts:
                _logger.warning(
                    "provider_retry_exhausted request_id=%s provider=%s attempts=%d reason=%s status=%s",
                    request_id, provider, attempt, _reason(exc),
                    getattr(exc, "provider_status", None))
                raise
            delay = retry_delay(policy, exc, attempt)
            remaining = policy.total_seconds - (time.monotonic() - started)
            if remaining <= 0 or delay > remaining:
                _logger.warning(
                    "provider_retry_abandoned request_id=%s provider=%s attempts=%d "
                    "reason=%s status=%s remaining_ms=%d delay_ms=%d",
                    request_id, provider, attempt, _reason(exc),
                    getattr(exc, "provider_status", None),
                    max(0, round(remaining * 1000)), round(delay * 1000))
                raise
            _logger.info(
                "provider_retry request_id=%s provider=%s attempt=%d reason=%s status=%s delay_ms=%d",
                request_id, provider, attempt, _reason(exc),
                getattr(exc, "provider_status", None), round(delay * 1000))
            await asyncio.sleep(delay)
