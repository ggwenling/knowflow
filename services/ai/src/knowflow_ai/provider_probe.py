"""Cheap provider readiness probe for /health/ready.

The probe calls each provider's model-list endpoint (GET /models) with the
provider key. It never calls chat/completions or embeddings, so it consumes no
tokens. A configured run also checks the shared ledger. Results are cached
briefly so a frequent readiness check cannot hammer the provider.
"""
import asyncio
import logging
import os
import sqlite3
import time
from pathlib import Path

import httpx

from .answering import LlmSettings
from .budget import BudgetLedger, RUN_BUDGET_ENVIRONMENT, SOFT_STOP_MICROYUAN
from .config import ConfigurationError
from .embedding import EmbeddingSettings
from .http_client import build_async_client

_logger = logging.getLogger(__name__)


def _default_timeout():
    try:
        value = float(os.environ.get("KNOWFLOW_PROVIDER_PROBE_TIMEOUT_SECONDS", "5"))
    except (TypeError, ValueError):
        return 5.0
    return value if 1.0 <= value <= 15.0 else 5.0


def _default_ttl():
    try:
        value = float(os.environ.get("KNOWFLOW_PROVIDER_PROBE_TTL_SECONDS", "10"))
    except (TypeError, ValueError):
        return 10.0
    return value if 0.0 <= value <= 60.0 else 10.0


def _budget_check(environ):
    ledger = environ.get("KNOWFLOW_BUDGET_LEDGER_PATH", "")
    price = environ.get("KNOWFLOW_BUDGET_PRICE_FILE", "")
    policy = environ.get("KNOWFLOW_BUDGET_POLICY_FILE", "")
    if not ledger or not price or not policy:
        return {"status": "DOWN", "reason": "BUDGET_PATHS_MISSING"}
    if not Path(ledger).parent.is_dir():
        return {"status": "DOWN", "reason": "BUDGET_LEDGER_DIR_MISSING"}
    if not Path(price).is_file() or not Path(policy).is_file():
        return {"status": "DOWN", "reason": "BUDGET_FILES_MISSING"}
    if any(environ.get(name) for name in RUN_BUDGET_ENVIRONMENT):
        try:
            scoped = BudgetLedger.from_environment(environ)
            reason = scoped.stop_reason()
            if reason not in ("BUDGET_SOFT_STOP", "BUDGET_EXCEEDED"):
                if scoped.summary()["reserved_microyuan"] >= SOFT_STOP_MICROYUAN:
                    reason = "BUDGET_SOFT_STOP"
        except (ValueError, sqlite3.Error):
            return {"status": "DOWN", "reason": "BUDGET_CONFIGURATION_REQUIRED"}
        if reason is not None:
            return {"status": "DOWN", "reason": reason}
    return {"status": "UP"}


async def probe_provider(name, *, base_url, api_key, timeout_seconds, client=None):
    """Return an UP/DOWN check without revealing URLs, keys, or response bodies."""
    owned = client is None
    client = client or build_async_client(timeout_seconds,
                                          environment_proxy_fallback=True)
    try:
        response = await client.get(
            base_url.rstrip("/") + "/models",
            headers={"Authorization": "Bearer " + api_key, "Accept": "application/json"},
            timeout=timeout_seconds,
        )
        status = response.status_code
        if status == 200:
            return {"status": "UP"}
        if status == 429:
            return {"status": "DOWN", "reason": "RATE_LIMITED", "provider_status": status}
        if status >= 500:
            return {"status": "DOWN", "reason": "PROVIDER_ERROR", "provider_status": status}
        if status in (401, 403):
            return {"status": "DOWN", "reason": "AUTH_REJECTED", "provider_status": status}
        return {"status": "DOWN", "reason": "PROVIDER_REJECTED", "provider_status": status}
    except httpx.TimeoutException:
        return {"status": "DOWN", "reason": "TIMEOUT"}
    except httpx.HTTPError:
        return {"status": "DOWN", "reason": "UNREACHABLE"}
    except Exception:
        _logger.warning("provider_probe_failed provider=%s reason=unexpected", name)
        return {"status": "DOWN", "reason": "UNKNOWN"}
    finally:
        if owned:
            await client.aclose()


def _load_provider_settings(environ):
    llm = LlmSettings.from_environment(environ)
    embedding = EmbeddingSettings.from_environment(environ)
    return llm, embedding


class ProviderReadiness:
    def __init__(self, *, timeout_seconds=None, ttl_seconds=None, environ=None,
                 probe=None, settings_loader=None):
        self.timeout_seconds = (_default_timeout() if timeout_seconds is None
                                else timeout_seconds)
        self.ttl_seconds = _default_ttl() if ttl_seconds is None else ttl_seconds
        self.environ = os.environ if environ is None else environ
        self._probe = probe
        self._settings_loader = settings_loader or _load_provider_settings
        self._cached = None
        self._checked_at = 0.0
        self._lock = asyncio.Lock()

    @classmethod
    def from_environment(cls):
        return cls(environ=os.environ)

    async def check(self):
        async with self._lock:
            now = time.monotonic()
            if (self._cached is not None
                    and now - self._checked_at < self.ttl_seconds):
                return self._cached
            result = await self._check()
            self._cached, self._checked_at = result, now
            return result

    async def _check(self):
        checks = {"budget": await asyncio.to_thread(_budget_check, self.environ)}
        try:
            llm_settings, embedding_settings = self._settings_loader(self.environ)
        except ConfigurationError:
            checks["llm"] = {"status": "DOWN", "reason": "CONFIGURATION_INVALID"}
            checks["embedding"] = {"status": "DOWN", "reason": "CONFIGURATION_INVALID"}
        else:
            if self._probe is None:
                llm, embedding = await asyncio.gather(
                    probe_provider("llm", base_url=llm_settings.base_url,
                                   api_key=llm_settings.api_key,
                                   timeout_seconds=self.timeout_seconds),
                    probe_provider("embedding", base_url=embedding_settings.base_url,
                                   api_key=embedding_settings.api_key,
                                   timeout_seconds=self.timeout_seconds),
                )
            else:
                llm, embedding = await asyncio.gather(
                    self._probe("llm", llm_settings),
                    self._probe("embedding", embedding_settings),
                )
            checks["llm"] = llm
            checks["embedding"] = embedding
        status = "UP" if all(item.get("status") == "UP" for item in checks.values()) else "UNAVAILABLE"
        return {"status": status, "checks": checks}
