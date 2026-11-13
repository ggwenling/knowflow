"""Allowlisted, single-line model attempt events. Never accept provider payloads."""
import asyncio
import json
import logging
import re
from uuid import uuid4

from .adapters import ProcessingError

_logger = logging.getLogger(__name__)
PROTOCOLS = frozenset(('deepseek', 'chat_completions', 'anthropic_messages', 'responses'))
FAILURE_CATEGORIES = frozenset((
    'http_4xx', 'auth', 'rate_limited', 'http_5xx', 'connect_failure', 'connection_reset',
    'connect_timeout', 'first_token_timeout', 'read_timeout', 'total_timeout',
    'invalid_completion', 'model_mismatch', 'length_truncation', 'content_filter', 'redirect',
    'response_too_large', 'busy', 'circuit_open', 'cancelled', 'configuration', 'budget', 'unknown',
))
ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', re.ASCII)
RAW_LOGGERS = (
    'openai._base_client', 'openai._response', 'openai._legacy_response',
    'anthropic._base_client', 'anthropic._response', 'anthropic._tracing', 'httpx', 'httpx2',
    *(f'{library}.{source}' for library in ('httpcore', 'httpcore2')
      for source in ('connection', 'http11', 'http2', 'proxy', 'socks')),
)


class _DiscardProviderPayload(logging.Filter):
    def filter(self, record):
        return False


_discard = _DiscardProviderPayload()


def install_safe_logging():
    _logger.setLevel(logging.INFO)
    # Uvicorn's default logging config installs handlers only for its own loggers.
    if not _logger.hasHandlers():
        _logger.addHandler(logging.StreamHandler())
    # Filters on ancestors do not apply to propagated child records. Install on
    # each actual source in the pinned SDKs, including both HTTP implementations.
    for name in RAW_LOGGERS:
        logger = logging.getLogger(name)
        if _discard not in logger.filters:
            logger.addFilter(_discard)


def normalize_usage(metadata):
    if not isinstance(metadata, dict):
        return None
    usage = {key: metadata[key] for key in ('input_tokens', 'output_tokens', 'total_tokens')
             if type(metadata.get(key)) is int and metadata[key] >= 0}
    return usage or None


def safe_model_id(value, key):
    if (not isinstance(value, str) or not 1 <= len(value) <= 160
            or not value.isprintable() or '@' in value
            or (key and (key in value or value in key))
            or re.search(r'(?i)(?:https?://|[^\s/]+:[^\s/]*@|sk[-_]|api[-_]?key)', value)):
        return '[redacted]'
    return value


def failure_category(error=None, *, kind=None):
    # Retry decisions may say output_started; logs preserve the underlying cause.
    if isinstance(error, asyncio.CancelledError):
        return 'cancelled'
    if error is not None and not isinstance(error, ProcessingError):
        seen = set()
        cause = error.__cause__
        while cause is not None and id(cause) not in seen:
            seen.add(id(cause))
            if isinstance(cause, ProcessingError):
                return failure_category(cause)
            cause = cause.__cause__
    if isinstance(error, ProcessingError):
        kind = kind or error.retry_reason
        if error.status == 429 and error.provider_status is None:
            return 'busy'
        status = error.provider_status
        if status is not None:
            if status in (401, 403):
                return 'auth'
            if status == 429:
                return 'rate_limited'
            if 400 <= status <= 499:
                return 'http_4xx'
            if 500 <= status <= 599:
                return 'http_5xx'
        if kind is None and error.code == 'PROCESSING_TIMEOUT':
            return 'total_timeout'
    aliases = {
        'completion_validation': 'invalid_completion', 'sdk_parse': 'invalid_completion',
        'parse': 'invalid_completion', 'garbage': 'invalid_completion', 'encoding': 'invalid_completion',
        'refusal': 'content_filter', 'local_budget': 'budget', 'admission': 'busy',
        'invalid_url': 'configuration', 'unsupported_protocol': 'configuration',
        'local_input': 'configuration', 'outer_deadline': 'total_timeout',
    }
    category = aliases.get(kind, kind)
    return category if category in FAILURE_CATEGORIES else 'unknown'


def build_call_fields(*, context, protocol, model_id, key, call_id, attempt=0,
                      state=None, duration_ms=0, category=None):
    first = state.first_content_at if state is not None else None
    start = state.dispatched_at if state is not None else None
    called = state is not None and state.provider_called
    request_id = context.request_id
    return {
        'event': 'llm_call',
        'request_id': request_id if isinstance(request_id, str) and ID_PATTERN.fullmatch(request_id) else '[redacted]',
        'protocol': protocol if protocol in PROTOCOLS else 'deepseek',
        'model_id': safe_model_id(model_id, key),
        'duration_ms': max(0, round(duration_ms)),
        'first_token_latency_ms': max(0, round((first - start) * 1000))
        if first is not None and start is not None else None,
        'first_token_observation': state.first_token_observation if first is not None else None,
        'token_usage': normalize_usage(state.usage) if state is not None else None,
        'outcome': 'failure' if category is not None else 'success',
        'failure_category': category if category in FAILURE_CATEGORIES else ('unknown' if category else None),
        'call_id': call_id, 'attempt': attempt if called else 0,
        'purpose': context.purpose if context.purpose in ('answer', 'repair', 'probe') else 'answer',
        'provider_called': called,
    }


def emit_call(**fields):
    # Observability must never mask a business exception (including cancellation).
    try:
        _logger.info(json.dumps(build_call_fields(**fields), ensure_ascii=True, separators=(',', ':')))
    except Exception:
        pass


def new_call_id():
    return uuid4().hex
