"""Single-process index executor fenced by Java's per-attempt lease."""
import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
from hashlib import sha256
import uuid

from .adapters import ProcessingError
from .batch_digest import batch_sha256, manifest_sha256
from .chunking import chunk_document
from .config import ConfigurationError
from .embedding import EmbeddingSettings, SiliconFlowEmbeddingAdapter
from .java_client import JavaGateway, JavaGatewayError
from .parsing import ParseFailure, parse_document
from .protocol import CONTRACT_VERSION


class WorkerUnavailable(RuntimeError):
    pass


def _execution_key(message: dict) -> tuple[str, str, int]:
    lease = message["lease"]
    return lease["task_id"], lease["lease_id"], lease["fencing"]


class IndexWorker:
    def __init__(self, gateway: JavaGateway, embedding_factory=None,
                 heartbeat_seconds: float = 10.0, queue_size: int = 100):
        self._gateway = gateway
        self._embedding_factory = embedding_factory or self._default_embedding
        self._heartbeat_seconds = heartbeat_seconds
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self._active: dict[tuple, asyncio.Task] = {}
        self._queued: set[tuple] = set()
        self._cancelled: set[tuple] = set()
        self._heartbeats: dict[tuple, asyncio.Task] = {}
        self._recent: OrderedDict[tuple, None] = OrderedDict()
        self._runner: asyncio.Task | None = None

    @staticmethod
    def _default_embedding():
        return SiliconFlowEmbeddingAdapter(EmbeddingSettings.from_environment())

    async def start(self):
        if self._runner is None:
            self._runner = asyncio.create_task(self._run(), name="knowflow-index-worker")

    async def close(self):
        if self._runner is not None:
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass
            self._runner = None
        tasks = tuple(self._active.values()) + tuple(self._heartbeats.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def accept(self, dispatch: dict):
        key = _execution_key(dispatch)
        if key in self._recent or key in self._active or key in self._queued:
            return
        if self._queue.full():
            raise WorkerUnavailable("INDEX_QUEUE_FULL")
        self._queued.add(key)
        heartbeat = asyncio.create_task(self._heartbeat(dispatch))
        heartbeat.add_done_callback(lambda completed: completed.exception()
                                    if not completed.cancelled() else None)
        self._heartbeats[key] = heartbeat
        self._queue.put_nowait((key, dispatch))

    async def cancel(self, message: dict):
        key = (message["task_id"], message["lease_id"], message["fencing"])
        active = self._active.get(key)
        if active is not None or key in self._queued:
            self._cancelled.add(key)
        if active is not None:
            active.cancel()
        elif key in self._heartbeats:
            self._heartbeats[key].cancel()

    async def _run(self):
        while True:
            key, dispatch = await self._queue.get()
            self._queued.discard(key)
            try:
                if key in self._cancelled:
                    continue
                heartbeat = self._heartbeats.get(key)
                if heartbeat is None or heartbeat.done():
                    continue
                current = asyncio.create_task(self._execute(dispatch, heartbeat),
                                              name="knowflow-index-execution")
                self._active[key] = current
                try:
                    await current
                except asyncio.CancelledError:
                    if asyncio.current_task().cancelling():
                        raise
                finally:
                    self._active.pop(key, None)
                    self._heartbeats.pop(key, None)
                    self._recent[key] = None
                    self._recent.move_to_end(key)
                    while len(self._recent) > 1024:
                        self._recent.popitem(last=False)
            finally:
                self._cancelled.discard(key)
                heartbeat = self._heartbeats.pop(key, None)
                if heartbeat is not None:
                    heartbeat.cancel()
                self._queue.task_done()

    async def _execute(self, dispatch: dict, heartbeat: asyncio.Task):
        lease = dispatch["lease"]
        embedding = None
        processing = None
        try:
            embedding = self._embedding_factory()
            processing = asyncio.create_task(self._index(dispatch, embedding))
            done, _ = await asyncio.wait((processing, heartbeat),
                                         return_when=asyncio.FIRST_COMPLETED)
            if heartbeat in done:
                error = heartbeat.exception()
                processing.cancel()
                try:
                    await processing
                except asyncio.CancelledError:
                    pass
                if error is not None:
                    raise error
            await processing
        except asyncio.CancelledError:
            if processing is not None:
                processing.cancel()
                await asyncio.gather(processing, return_exceptions=True)
            raise
        except JavaGatewayError as error:
            if error.code in {"LEASE_REJECTED", "DOCUMENT_UNAVAILABLE", "RESOURCE_NOT_FOUND",
                              "UNAUTHENTICATED", "SCOPE_DENIED"}:
                return
            await self._report_failure(lease, self._failure_code(error), error.retryable)
        except ParseFailure as error:
            await self._report_failure(lease, self._parse_failure_code(str(error)), False)
        except ConfigurationError:
            await self._report_failure(lease, "MODEL_FAILURE", False)
        except ProcessingError as error:
            await self._report_failure(lease, self._failure_code(error), error.retryable)
        except Exception:
            await self._report_failure(lease, "INDEX_WRITE_FAILED", True)
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            if embedding is not None:
                await embedding.aclose()

    async def _heartbeat(self, dispatch: dict):
        lease = dispatch["lease"]
        lease_expires_at = dispatch["lease_expires_at"]
        while True:
            expires_at = datetime.fromisoformat(lease_expires_at.replace("Z", "+00:00"))
            remaining_seconds = (expires_at - datetime.now(timezone.utc)).total_seconds()
            await asyncio.sleep(max(0.1, min(self._heartbeat_seconds, remaining_seconds / 3)))
            lease_expires_at = await self._gateway.heartbeat(lease)

    async def _index(self, dispatch: dict, embedding):
        lease = dispatch["lease"]
        source = await self._gateway.read_source(dispatch)
        parsed = parse_document(source, format=dispatch["source"]["format"],
                                document_id=lease["document_id"],
                                content_version_id=lease["content_version_id"],
                                file_id=dispatch["source"]["file_id"])
        if parsed.file_sha256 != dispatch["source"]["sha256"]:
            raise ProcessingError("SOURCE_UNAVAILABLE", 502, retryable=False)
        chunks = chunk_document(parsed)
        if not chunks:
            raise ParseFailure("EMPTY_DOCUMENT")
        batches: list[dict] = []
        model_profile = "BAAI/bge-m3"
        chunk_namespace = uuid.UUID(lease["index_version_id"])
        for start in range(0, len(chunks), 16):
            source_chunks = chunks[start:start + 16]
            vectors = await embedding.embed([chunk.text for chunk in source_chunks],
                                            request_id=str(uuid.uuid4()))
            rows = []
            for offset, (chunk, vector) in enumerate(zip(source_chunks, vectors["data"], strict=True)):
                locator = dict(chunk.locator)
                rows.append({
                    "chunk_id": str(uuid.uuid5(chunk_namespace, chunk.chunk_id)),
                    "sequence_no": chunk.sequence + 1,
                    "text": chunk.text,
                    "text_sha256": chunk.text_sha256,
                    "locator": locator,
                    "embedding": vector["embedding"],
                })
            batch = {
                "contract_version": CONTRACT_VERSION,
                "request_id": str(uuid.uuid4()),
                "lease": lease,
                "batch_id": str(uuid.uuid4()),
                "batch_sequence": len(batches) + 1,
                "batch_sha256": "0" * 64,
                "chunks": rows,
            }
            batch["batch_sha256"] = batch_sha256(batch)
            self._gateway._contract.validate("IndexBatch", batch)
            await self._gateway.write_batch(batch)
            batches.append(batch)

        manifest = {
            "chunk_count": len(chunks), "embedding_count": len(chunks),
            "embedding_dimensions": 1024, "embedding_model_profile_id": model_profile,
            "manifest_sha256": manifest_sha256(lease, model_profile, batches, len(chunks)),
        }
        completion = {"contract_version": CONTRACT_VERSION, "request_id": str(uuid.uuid4()),
                      "lease": lease, "outcome": "SUCCEEDED", "manifest": manifest}
        self._gateway._contract.validate("Completion", completion)
        await self._gateway.complete(completion)

    async def _report_failure(self, lease: dict, code: str, retryable: bool):
        completion = {
            "contract_version": CONTRACT_VERSION, "request_id": str(uuid.uuid4()),
            "lease": lease, "outcome": "FAILED",
            "failure": {"code": code, "message": code, "retryable": bool(retryable)},
        }
        try:
            self._gateway._contract.validate("Completion", completion)
            await self._gateway.complete(completion)
        except (JavaGatewayError, ValueError, TypeError):
            # A failed completion is recovered by Java when the lease expires.
            return

    @staticmethod
    def _parse_failure_code(code: str) -> str:
        if code in {"EMPTY_DOCUMENT", "PDF_NO_TEXT"}:
            return "EMPTY_CONTENT"
        if code in {"FILE_TOO_LARGE", "TEXT_TOO_LARGE", "PDF_PAGE_LIMIT"}:
            return "RESOURCE_LIMIT"
        if code == "PDF_ENCRYPTED":
            return "UNSUPPORTED_CONTENT"
        return "UNSUPPORTED_CONTENT"

    @staticmethod
    def _failure_code(error: ProcessingError) -> str:
        if error.code in {"PROCESSING_TIMEOUT", "MODEL_TIMEOUT", "JAVA_GATEWAY_TIMEOUT"}:
            return "MODEL_TIMEOUT"
        if error.code == "SOURCE_UNAVAILABLE":
            return "UNSUPPORTED_CONTENT"
        if error.code in {"JAVA_GATEWAY_UNAVAILABLE", "JAVA_GATEWAY_REJECTED"}:
            return "INDEX_WRITE_FAILED"
        if error.code in {"MODEL_FAILURE", "PROVIDER_MODEL_MISMATCH", "EMBEDDING_COUNT_MISMATCH"}:
            return "MODEL_FAILURE"
        return "INDEX_WRITE_FAILED"
