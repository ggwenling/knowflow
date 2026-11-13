"""Bounded provider retry for transient 5xx / timeout / 429 failures.

Budget reservations stay inside the per-attempt callable, so every retry is a
new reservation and can never bypass the ledger's soft stop. 4xx is final.
"""
from asyncio import CancelledError, current_task
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import asyncio
import logging
import math
import os
import time
from typing import Literal

import httpx
import httpx2

from .adapters import ProcessingError
from .config import ConfigurationError

_logger = logging.getLogger(__name__)


FailureReason = Literal[
    "rate_limited", "http_5xx", "auth", "http_4xx", "redirect",
    "connect_failure", "connection_reset", "connect_timeout", "first_token_timeout", "read_timeout",
    "total_timeout", "outer_deadline", "completion_validation", "model_mismatch", "parse",
    "garbage", "response_too_large", "encoding", "content_filter", "refusal", "length_truncation",
    "invalid_url", "unsupported_protocol", "local_budget", "admission", "circuit_open",
    "local_input", "configuration", "cancelled", "output_started", "client_output_started", "unknown",
]
_TRANSIENT_KINDS = frozenset((
    "connect_failure", "connection_reset", "connect_timeout", "first_token_timeout", "read_timeout",
))
_FINAL_KINDS = frozenset((
    "total_timeout", "outer_deadline", "completion_validation", "model_mismatch", "parse",
    "garbage", "response_too_large", "encoding", "content_filter", "refusal", "length_truncation",
    "invalid_url", "unsupported_protocol", "local_budget", "admission", "circuit_open",
    "local_input", "configuration", "cancelled",
))


@dataclass(frozen=True)
class RetryDecision:
    retryable: bool
    reason: FailureReason


def classify_provider_failure(*, status: int | None = None, failure_kind: str | None = None,
                              output_started: bool = False, client_output_started: bool = False) -> RetryDecision:
    """Classify safe scalars only; custom callers must additionally disable retry.

    Unknown failures fail closed. Explicit local/completion failures take precedence
    over HTTP status, and neither provider nor client output can be replayed.
    """
    if client_output_started:
        return RetryDecision(False, "client_output_started")
    if output_started:
        return RetryDecision(False, "output_started")
    if failure_kind in _FINAL_KINDS:
        return RetryDecision(False, failure_kind)
    if type(status) is int:
        if status == 429:
            return RetryDecision(True, "rate_limited")
        if 500 <= status <= 599:
            return RetryDecision(True, "http_5xx")
        if status in (401, 403):
            return RetryDecision(False, "auth")
        if 400 <= status <= 499:
            return RetryDecision(False, "http_4xx")
        if 300 <= status <= 399:
            return RetryDecision(False, "redirect")
        return RetryDecision(False, "unknown")
    if failure_kind in _TRANSIENT_KINDS:
        return RetryDecision(True, failure_kind)
    return RetryDecision(False, "unknown")


def transport_failure_kind(error):
    """Normalize the two HTTP libraries at the boundary, never their text.

    Inspect causes as well: SDK connection wrappers must not turn a local URL,
    encoding, or protocol error into a transient connection failure.
    SDK-specific recognition belongs to the LangChain boundary.
    """
    kind = "unknown"
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, (httpx.InvalidURL, httpx2.InvalidURL)):
            return "invalid_url"
        if isinstance(error, (httpx.UnsupportedProtocol, httpx2.UnsupportedProtocol)):
            return "unsupported_protocol"
        if isinstance(error, (httpx.DecodingError, httpx2.DecodingError, UnicodeError)):
            return "encoding"
        if isinstance(error, (httpx.LocalProtocolError, httpx2.LocalProtocolError, ValueError)):
            return "local_input"
        if isinstance(error, (httpx.ConnectTimeout, httpx2.ConnectTimeout)):
            kind = "connect_timeout"
        elif isinstance(error, (httpx.ReadTimeout, httpx2.ReadTimeout)):
            kind = "read_timeout"
        elif isinstance(error, (httpx.ConnectError, httpx2.ConnectError)):
            kind = "connect_failure"
        elif isinstance(error, (httpx.ReadError, httpx2.ReadError, httpx.WriteError, httpx2.WriteError,
                                httpx.RemoteProtocolError, httpx2.RemoteProtocolError,
                                ConnectionResetError, BrokenPipeError)):
            kind = "connection_reset"
        error = error.__cause__
    return kind


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


async def run_provider_with_retry(operation, *, policy, request_id, provider,
                                  clock=None, sleep=None, output_started=None,
                                  client_output_started=None, outer_deadline=None):
    """Call ``operation`` up to ``policy.max_attempts`` times.

    ``operation`` must perform its own budget reservation immediately before
    the HTTP request. Any ``ProcessingError`` with ``retryable=False`` is final.
    Deadlines and ``clock`` use the same monotonic time base. The cutoff limits
    retry scheduling; the caller's total deadline must also wrap the operation.
    A zero retry budget still permits the first attempt.
    """
    clock = time.monotonic if clock is None else clock
    sleep = asyncio.sleep if sleep is None else sleep
    cutoff = clock() + policy.total_seconds
    if outer_deadline is not None:
        cutoff = min(cutoff, outer_deadline)
        if clock() >= outer_deadline:
            raise ProcessingError("PROCESSING_TIMEOUT", 504, retryable=False, retry_reason="total_timeout")

    def check_cancelled():
        task = current_task()
        if task is not None and task.cancelling():
            raise CancelledError

    def has_output():
        return ((output_started is not None and output_started())
                or (client_output_started is not None and client_output_started()))

    attempt = 0
    while True:
        check_cancelled()
        attempt += 1
        try:
            return await operation()
        except ProcessingError as exc:
            retryable = bool(getattr(exc, "retryable", False))
            check_cancelled()
            if not retryable or has_output():
                raise
            if attempt >= policy.max_attempts:
                _logger.warning(
                    "provider_retry_exhausted request_id=%s provider=%s attempts=%d reason=%s status=%s",
                    request_id, provider, attempt, _reason(exc),
                    getattr(exc, "provider_status", None))
                raise
            delay = retry_delay(policy, exc, attempt)
            remaining = cutoff - clock()
            if remaining <= 0 or not math.isfinite(delay) or delay < 0 or delay >= remaining:
                _logger.warning(
                    "provider_retry_abandoned request_id=%s provider=%s attempts=%d "
                    "reason=%s status=%s remaining_ms=%d delay_ms=%d",
                    request_id, provider, attempt, _reason(exc),
                    getattr(exc, "provider_status", None),
                    max(0, round(remaining * 1000)), round(delay * 1000) if math.isfinite(delay) else 0)
                raise
            _logger.info(
                "provider_retry request_id=%s provider=%s attempt=%d reason=%s status=%s delay_ms=%d",
                request_id, provider, attempt, _reason(exc),
                getattr(exc, "provider_status", None), round(delay * 1000))
            check_cancelled()
            if has_output() or cutoff - clock() <= delay:
                raise
            await sleep(delay)
            check_cancelled()
            if has_output() or clock() >= cutoff:
                raise
