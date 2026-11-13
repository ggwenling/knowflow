"""Evaluation-only retrieval capture; this module never creates a provider.

The caller must inject the retriever. This is not a runnable collection service
and does not enforce the provider budget; real calls remain out of scope.
"""
import asyncio
from copy import deepcopy
import re


_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z", re.ASCII)
_TRACE_FIELDS = ("document_id", "content_version_id", "index_version_id",
                 "source_id", "locator", "text_sha256")


class CaptureStore:
    """In-memory, single-use traces for one evaluation run.

    IDs cannot be reused, even after a failed call or a consumed trace. The
    store is process-local and intentionally does not persist source text.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._seen = set()
        self._pending = set()
        self._traces = {}

    async def begin(self, request_id):
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise ValueError("INVALID_REQUEST_ID")
        async with self._lock:
            if request_id in self._seen:
                raise ValueError("DUPLICATE_REQUEST_ID")
            self._seen.add(request_id)
            self._pending.add(request_id)

    async def fail(self, request_id):
        async with self._lock:
            self._pending.discard(request_id)

    @staticmethod
    def _validate_rows(rows, scope):
        if not isinstance(rows, list) or len(rows) > 10 or not isinstance(scope, dict):
            raise ValueError("INVALID_RETRIEVAL_TRACE")
        try:
            allowed = {(item["document_id"], item["content_version_id"], item["index_version_id"])
                       for item in scope["indexes"]}
            trace = []
            sources = set()
            for row in rows:
                key = (row["document_id"], row["content_version_id"], row["index_version_id"])
                source_id = row["source_id"]
                locator = row["locator"]
                if not isinstance(locator, dict) or locator.get("kind") != "text_range":
                    # The scorer compares character spans and source hashes;
                    # PDF page locators need a separate design, so reject them
                    # with a distinct, readable code instead of a generic error.
                    raise ValueError("UNSUPPORTED_LOCATOR_KIND")
                if (key not in allowed or not isinstance(source_id, str)
                        or not _REQUEST_ID.fullmatch(source_id) or source_id in sources
                        or set(locator) != {"kind", "unit", "start", "end"}
                        or locator["unit"] != "unicode_code_point"
                        or type(locator["start"]) is not int or type(locator["end"]) is not int
                        or not 0 <= locator["start"] < locator["end"]
                        or not isinstance(row["text_sha256"], str)
                        or not re.fullmatch(r"[0-9a-f]{64}", row["text_sha256"])):
                    raise ValueError("INVALID_RETRIEVAL_TRACE")
                sources.add(source_id)
                trace.append({name: deepcopy(row[name]) for name in _TRACE_FIELDS})
        except (KeyError, TypeError):
            raise ValueError("INVALID_RETRIEVAL_TRACE") from None
        return trace

    async def record(self, request_id, rows, scope):
        trace = self._validate_rows(rows, scope)
        async with self._lock:
            if request_id not in self._pending:
                raise ValueError("INVALID_REQUEST_ID_STATE")
            self._pending.remove(request_id)
            self._traces[request_id] = trace

    async def append_followup(self, request_id, rows, scope):
        trace = self._validate_rows(rows, scope)
        async with self._lock:
            initial = self._traces[request_id]
            seen = {row["source_id"] for row in initial}
            initial.extend(row for row in trace if row["source_id"] not in seen)
        return rows

    async def take(self, request_id):
        async with self._lock:
            if request_id not in self._traces:
                raise ValueError("TRACE_NOT_AVAILABLE")
            return self._traces.pop(request_id)

    def take_nowait(self, request_id):
        """Pop a trace without suspending; safe inside cancellation cleanup.

        The store is process-local and mutated only from the event loop, so a
        synchronous pop is atomic with respect to other tasks.
        """
        if request_id not in self._traces:
            raise ValueError("TRACE_NOT_AVAILABLE")
        return self._traces.pop(request_id)


class CapturingRetriever:
    """Capture one top-10 retrieval and expose only its first five rows."""

    def __init__(self, retriever, store, *, allow_followup=False):
        self._retriever = retriever
        self._store = store
        self._allow_followup = allow_followup

    async def retrieve(self, question, scope, request_id, *, deadline=None, top_k=5):
        if top_k != 5:
            raise ValueError("UNSUPPORTED_GENERATION_LIMIT")
        if self._allow_followup and request_id in self._store._traces:
            rows = await self._retriever.retrieve(question, scope, request_id, deadline=deadline, top_k=5)
            return await self._store.append_followup(request_id, rows, scope)
        await self._store.begin(request_id)
        try:
            rows = await self._retriever.retrieve(question, scope, request_id,
                                                  deadline=deadline, top_k=10)
            await self._store.record(request_id, rows, scope)
        except BaseException:
            await self._store.fail(request_id)
            raise
        return rows[:5]
