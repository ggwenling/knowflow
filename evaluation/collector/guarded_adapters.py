"""Opt-in evaluation adapter wrappers; not wired into the product service.

The caller must provide the same durable ledger to every adapter and a trusted,
provider-specific conservative token-bound function. These wrappers do not stop
other adapters or processes from bypassing them and therefore do not by
themselves establish a global spending cap.
"""
import asyncio
from contextlib import aclosing
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4


class _GuardedAdapter:
    def __init__(self, *, adapter_factory, ledger, provider, model, quote, token_bounds, bound_evidence):
        if not callable(adapter_factory) or not callable(token_bounds) or ledger is None:
            raise ValueError("GUARD_CONFIGURATION_REQUIRED")
        self._factory = adapter_factory
        self._ledger = ledger
        self._provider = provider
        self._model = model
        self._quote = deepcopy(quote)
        self._token_bounds = token_bounds
        self._bound_evidence = deepcopy(bound_evidence)
        self._adapter = None
        self._closed = False

    async def _reserve(self, operation, *inputs):
        if self._closed:
            raise ValueError("ADAPTER_CLOSED")
        self._verify_bound_evidence()
        bounds = self._token_bounds(operation, *inputs)
        if (not isinstance(bounds, tuple) or len(bounds) != 2
                or type(bounds[0]) is not int or bounds[0] <= 0
                or type(bounds[1]) is not int or bounds[1] < 0
                or (operation in ("generate", "stream") and bounds[1] < 1024)):
            raise ValueError("TOKEN_BOUNDS_UNAVAILABLE")
        # A fresh reservation ID for each attempt: retries and split batches can
        # share a product request ID but must never share a budget reservation.
        attempt_id = "eval:" + uuid4().hex
        await asyncio.to_thread(
            self._ledger.reserve, attempt_id, provider=self._provider, model=self._model,
            input_tokens_upper=bounds[0], output_tokens_upper=bounds[1], quote=self._quote)
        if self._closed:
            raise ValueError("ADAPTER_CLOSED")
        if self._adapter is None:
            candidate = self._factory()
            if getattr(getattr(candidate, "settings", None), "model", None) != self._model:
                await candidate.aclose()
                raise ValueError("ADAPTER_MODEL_MISMATCH")
            self._adapter = candidate
        return self._adapter

    def _verify_bound_evidence(self):
        evidence = self._bound_evidence
        required = {"provider", "model", "policy_id", "source_url", "verified_by", "verified_at", "valid_until"}
        if (not isinstance(evidence, dict) or set(evidence) != required
                or evidence["provider"] != self._provider or evidence["model"] != self._model
                or not isinstance(evidence["policy_id"], str) or not evidence["policy_id"].strip()
                or getattr(self._token_bounds, "policy_id", None) != evidence["policy_id"]
                or not isinstance(evidence["verified_by"], str) or not evidence["verified_by"].strip()
                or not isinstance(evidence["source_url"], str)):
            raise ValueError("TOKEN_BOUND_EVIDENCE_REQUIRED")
        try:
            url = urlsplit(evidence["source_url"])
            start = datetime.fromisoformat(evidence["verified_at"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(evidence["valid_until"].replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if (url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment
                    or start.tzinfo is None or end.tzinfo is None
                    or not start <= now <= end):
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            raise ValueError("TOKEN_BOUND_EVIDENCE_REQUIRED") from None

    async def aclose(self):
        self._closed = True
        if self._adapter is not None:
            await self._adapter.aclose()


class GuardedEmbedding(_GuardedAdapter):
    async def embed(self, texts, *, request_id):
        snapshot = deepcopy(texts)
        adapter = await self._reserve("embed", snapshot)
        return await adapter.embed(snapshot, request_id=request_id)


class GuardedLlm(_GuardedAdapter):
    @property
    def last_usage(self):
        return getattr(self._adapter, "last_usage", None)

    async def generate(self, question, evidence, *, request_id):
        snapshot = deepcopy(evidence)
        adapter = await self._reserve("generate", question, snapshot)
        return await adapter.generate(question, snapshot, request_id=request_id)

    async def stream_content(self, question, evidence, *, request_id):
        snapshot = deepcopy(evidence)
        adapter = await self._reserve("stream", question, snapshot)
        async with aclosing(adapter.stream_content(question, snapshot, request_id=request_id)) as stream:
            async for fragment in stream:
                yield fragment
