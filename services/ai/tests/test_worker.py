import copy
import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import time

import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.embedding import EmbeddingSettings
from knowflow_ai.java_client import JavaGatewayError
from knowflow_ai.parsing import ParseFailure
from knowflow_ai.protocol import ContractConsumer
from knowflow_ai.worker import IndexWorker, WorkerUnavailable, validate_runtime_profile


ROOT = Path(__file__).resolve().parents[3]
_digest_spec = importlib.util.spec_from_file_location(
    "shared_batch_digest", ROOT / "contracts/index_batch_hash.py")
_digest_module = importlib.util.module_from_spec(_digest_spec)
_digest_spec.loader.exec_module(_digest_module)
shared_batch_sha256 = _digest_module.batch_sha256


class FakeEmbedding:
    async def embed(self, texts, *, request_id):
        return {"request_id": request_id, "model": "BAAI/bge-m3", "dimensions": 1024,
                "data": [{"index": i, "embedding": [0.125] * 1024}
                         for i, _ in enumerate(texts)]}

    async def aclose(self):
        return None


class BlockingEmbedding:
    def __init__(self):
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.closed = asyncio.Event()
        self.order = []

    async def embed(self, texts, *, request_id):
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.order.append("cancelled")
            self.cancelled.set()

    async def aclose(self):
        self.order.append("closed")
        self.closed.set()


class FakeGateway:
    def __init__(self, contract, source):
        self._contract = contract
        self.source = source
        self.batches = []
        self.completions = []

    async def read_source(self, dispatch):
        return self.source

    async def write_batch(self, batch):
        self.batches.append(copy.deepcopy(batch))

    async def complete(self, completion):
        self.completions.append(copy.deepcopy(completion))


def _dispatch(source: bytes):
    examples = json.loads((ROOT / "contracts/examples/protocol-cases.json").read_text(encoding="utf-8"))
    dispatch = next(case["payload"] for case in examples
                    if case["definition"] == "IndexDispatch" and case["structurally_valid"])
    dispatch = copy.deepcopy(dispatch)
    dispatch["source"].update(format="txt", sha256=sha256(source).hexdigest())
    return dispatch


@pytest.mark.asyncio
async def test_worker_writes_batches_and_manifest_then_completes():
    source = ("KnowFlow verifies each citation against its original source. " * 45).encode("utf-8")
    contract = ContractConsumer(ROOT / "contracts/schemas/protocol.schema.json")
    gateway = FakeGateway(contract, source)
    worker = IndexWorker(gateway, embedding_factory=FakeEmbedding)

    await worker._index(_dispatch(source), FakeEmbedding())

    assert gateway.batches
    assert [batch["batch_sequence"] for batch in gateway.batches] == list(
        range(1, len(gateway.batches) + 1))
    for batch in gateway.batches:
        assert batch["batch_sha256"] == shared_batch_sha256(batch)
        assert all(len(chunk["embedding"]) == 1024 for chunk in batch["chunks"])
        assert all(len(chunk["chunk_id"]) == 36 for chunk in batch["chunks"])
        contract.validate("IndexBatch", batch)
    assert len(gateway.completions) == 1
    completion = gateway.completions[0]
    assert completion["outcome"] == "SUCCEEDED"
    assert completion["manifest"]["chunk_count"] == sum(
        len(batch["chunks"]) for batch in gateway.batches)
    contract.validate("Completion", completion)


@pytest.mark.parametrize(("max_batch_chunks", "max_batch_bytes", "expected_max_chunks"), [
    (2, 100_000, 2),
    (32, 9_000, 1),
])
@pytest.mark.asyncio
async def test_worker_applies_dispatch_chunk_embedding_and_write_limits(
        max_batch_chunks, max_batch_bytes, expected_max_chunks):
    source = ("😀" * 2_000).encode("utf-8")
    contract = ContractConsumer(ROOT / "contracts/schemas/protocol.schema.json")
    gateway = FakeGateway(contract, source)
    calls = []

    class RecordingEmbedding(FakeEmbedding):
        async def embed(self, texts, *, request_id):
            calls.append([len(text) for text in texts])
            return await super().embed(texts, request_id=request_id)

    dispatch = _dispatch(source)
    dispatch["runtime_profile"].update(
        chunk_max_codepoints=120,
        overlap_codepoints=20,
        embedding_max_batch_items=3,
        index_max_batch_chunks=max_batch_chunks,
        index_max_batch_bytes=max_batch_bytes,
    )
    worker = IndexWorker(gateway, embedding_factory=RecordingEmbedding)

    await worker._index(dispatch, RecordingEmbedding())

    assert calls and all(len(call) <= 3 for call in calls)
    assert max(len(call) for call in calls) == 3
    written = [chunk for batch in gateway.batches for chunk in batch["chunks"]]
    assert written and all(len(chunk["text"]) <= 120 for chunk in written)
    assert all(len(batch["chunks"]) <= max_batch_chunks for batch in gateway.batches)
    assert max(len(batch["chunks"]) for batch in gateway.batches) == expected_max_chunks
    assert all(len(json.dumps(batch, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
               <= max_batch_bytes for batch in gateway.batches)
    assert gateway.completions[0]["outcome"] == "SUCCEEDED"


@pytest.mark.asyncio
async def test_one_codepoint_chunking_keeps_heartbeat_responsive_and_cancellable(monkeypatch):
    import knowflow_ai.worker as worker_module
    from knowflow_ai.parsing import parse_document

    source = b"x" * 16_000
    parsed = parse_document(source, format="txt", document_id="doc-example-1",
                            content_version_id="content-example-1", file_id="file-example-1")

    async def parsed_source(*_args, **_kwargs):
        return parsed

    monkeypatch.setattr(worker_module, "parse_document_isolated", parsed_source)
    monkeypatch.setattr(worker_module, "_batch_wire_size", lambda *_args: 1)

    class NoopContract:
        def validate(self, *_args):
            return None

    class ResponsiveGateway(FakeGateway):
        def __init__(self):
            super().__init__(NoopContract(), source)
            self.heartbeat_started = asyncio.Event()

        async def heartbeat(self, _lease):
            self.heartbeat_started.set()
            return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        async def write_batch(self, _batch):
            return None

    class ResponsiveEmbedding:
        calls = 0
        vector = [0.125] * 1024

        async def embed(self, texts, *, request_id):
            self.calls += 1
            return {"data": [{"embedding": self.vector} for _ in texts]}

        async def aclose(self):
            return None

    gateway = ResponsiveGateway()
    embedding = ResponsiveEmbedding()
    worker = IndexWorker(gateway, heartbeat_seconds=0.001)
    dispatch = _dispatch(source)
    dispatch["runtime_profile"].update(
        chunk_max_codepoints=1,
        overlap_codepoints=0,
        embedding_max_batch_items=64,
        index_max_batch_chunks=64,
        index_max_batch_bytes=1_000_000,
    )
    dispatch["lease_expires_at"] = (
        datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    heartbeat = asyncio.create_task(worker._heartbeat(dispatch))
    processing = asyncio.create_task(worker._index(dispatch, embedding))
    started = time.monotonic()
    try:
        await asyncio.wait_for(gateway.heartbeat_started.wait(), timeout=1)
        processing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(processing, timeout=1)
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)

    assert time.monotonic() - started < 1
    assert embedding.calls < 16_000 // 64
    assert gateway.completions == []


def test_runtime_profile_must_match_lease_and_embedding_limits():
    dispatch = _dispatch(b"source")
    settings = EmbeddingSettings(api_key="e" * 40)
    validate_runtime_profile(dispatch, settings)

    with pytest.raises(ProcessingError, match="INVALID_REQUEST"):
        validate_runtime_profile(
            dispatch, EmbeddingSettings(api_key="e" * 40, max_batch_items=8))

    dispatch = _dispatch(b"source")
    dispatch["runtime_profile"]["pipeline_profile_id"] = "other-pipeline"
    with pytest.raises(ProcessingError, match="INVALID_REQUEST"):
        validate_runtime_profile(dispatch)


@pytest.mark.asyncio
async def test_chunk_ids_are_deterministic_and_isolated_by_string_index_version():
    source = ("Index versions require distinct chunk primary keys. " * 45).encode("utf-8")
    contract = ContractConsumer(ROOT / "contracts/schemas/protocol.schema.json")
    dispatch = _dispatch(source)
    first_gateway = FakeGateway(contract, source)
    second_gateway = FakeGateway(contract, source)
    first = IndexWorker(first_gateway, embedding_factory=FakeEmbedding)
    second = IndexWorker(second_gateway, embedding_factory=FakeEmbedding)
    other_version = copy.deepcopy(dispatch)
    other_version["lease"]["index_version_id"] = "index-version-two"

    await first._index(dispatch, FakeEmbedding())
    first_batch_count = len(first_gateway.batches)
    await first._index(dispatch, FakeEmbedding())
    await second._index(other_version, FakeEmbedding())

    first_ids = [chunk["chunk_id"] for batch in first_gateway.batches[:first_batch_count]
                 for chunk in batch["chunks"]]
    replay_ids = [chunk["chunk_id"] for batch in first_gateway.batches[first_batch_count:]
                  for chunk in batch["chunks"]]
    other_ids = [chunk["chunk_id"] for batch in second_gateway.batches
                 for chunk in batch["chunks"]]
    assert first_ids == replay_ids
    assert len(first_ids) == len(other_ids)
    assert set(first_ids).isdisjoint(other_ids)


@pytest.mark.asyncio
async def test_worker_deduplicates_an_accepted_lease_and_cancels_its_heartbeat():
    contract = ContractConsumer(ROOT / "contracts/schemas/protocol.schema.json")
    gateway = FakeGateway(contract, b"")
    worker = IndexWorker(gateway)
    dispatch = _dispatch(b"source")
    await worker.accept(dispatch)
    await worker.accept(dispatch)
    assert worker._queue.qsize() == 1
    assert len(worker._heartbeats) == 1
    await worker.cancel({"task_id": dispatch["lease"]["task_id"],
                         "lease_id": dispatch["lease"]["lease_id"],
                         "fencing": dispatch["lease"]["fencing"]})
    heartbeat = next(iter(worker._heartbeats.values()))
    with pytest.raises(asyncio.CancelledError):
        await heartbeat
    assert heartbeat.cancelled()
    await worker.close()


@pytest.mark.asyncio
async def test_cancelling_active_execution_stops_processing_before_closing_embedding():
    source = ("Synthetic cancellation must stop active processing. " * 45).encode("utf-8")
    contract = ContractConsumer(ROOT / "contracts/schemas/protocol.schema.json")
    gateway = FakeGateway(contract, source)
    embedding = BlockingEmbedding()
    worker = IndexWorker(gateway, embedding_factory=lambda: embedding,
                         heartbeat_seconds=3600)
    dispatch = _dispatch(source)
    dispatch["lease_expires_at"] = (
        datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    lease = dispatch["lease"]

    await worker.start()
    await worker.accept(dispatch)
    await asyncio.wait_for(embedding.started.wait(), timeout=1)
    await worker.cancel({"task_id": lease["task_id"], "lease_id": lease["lease_id"],
                         "fencing": lease["fencing"]})
    await asyncio.wait_for(embedding.cancelled.wait(), timeout=1)
    await asyncio.wait_for(embedding.closed.wait(), timeout=1)
    await asyncio.wait_for(worker._queue.join(), timeout=1)

    assert gateway.batches == []
    assert gateway.completions == []
    assert embedding.order == ["cancelled", "closed"]
    assert worker._active == {}
    assert worker._heartbeats == {}
    await worker.close()


@pytest.mark.asyncio
async def test_parser_process_unavailable_is_reported_as_retryable_infrastructure_failure(
        monkeypatch):
    import knowflow_ai.worker as worker_module

    source = b"parser process unavailable"
    contract = ContractConsumer(ROOT / "contracts/schemas/protocol.schema.json")
    gateway = FakeGateway(contract, source)

    async def unavailable(*_args, **_kwargs):
        raise ParseFailure("PARSER_UNAVAILABLE")

    monkeypatch.setattr(worker_module, "parse_document_isolated", unavailable)
    worker = IndexWorker(gateway, embedding_factory=FakeEmbedding)
    heartbeat = asyncio.create_task(asyncio.Event().wait())
    await worker._execute(_dispatch(source), heartbeat)

    assert gateway.completions[0]["failure"] == {
        "code": "INDEX_WRITE_FAILED",
        "message": "INDEX_WRITE_FAILED",
        "retryable": True,
    }


@pytest.mark.asyncio
async def test_lease_rejection_from_heartbeat_stops_processing_without_completion():
    source = ("A rejected lease must stop active indexing immediately. " * 45).encode("utf-8")
    contract = ContractConsumer(ROOT / "contracts/schemas/protocol.schema.json")
    embedding = BlockingEmbedding()

    class LeaseRejectedGateway(FakeGateway):
        def __init__(self):
            super().__init__(contract, source)
            self.heartbeat_started = asyncio.Event()

        async def heartbeat(self, lease):
            self.heartbeat_started.set()
            await embedding.started.wait()
            raise JavaGatewayError("LEASE_REJECTED", 409)

    gateway = LeaseRejectedGateway()
    worker = IndexWorker(gateway, embedding_factory=lambda: embedding,
                         heartbeat_seconds=0.001)
    dispatch = _dispatch(source)
    lease = dispatch["lease"]

    await worker.start()
    await worker.accept(dispatch)
    await asyncio.wait_for(gateway.heartbeat_started.wait(), timeout=1)
    await asyncio.wait_for(embedding.started.wait(), timeout=1)
    await asyncio.wait_for(embedding.cancelled.wait(), timeout=1)
    await asyncio.wait_for(embedding.closed.wait(), timeout=1)
    await asyncio.wait_for(worker._queue.join(), timeout=1)

    assert gateway.batches == []
    assert gateway.completions == []
    assert embedding.order == ["cancelled", "closed"]
    assert worker._active == {}
    assert worker._heartbeats == {}
    await worker.close()


@pytest.mark.asyncio
async def test_worker_rejects_dispatch_when_bounded_queue_is_full():
    contract = ContractConsumer(ROOT / "contracts/schemas/protocol.schema.json")
    gateway = FakeGateway(contract, b"source")
    worker = IndexWorker(gateway, heartbeat_seconds=3600, queue_size=1)
    first = _dispatch(b"source")
    second = copy.deepcopy(first)
    second["lease"]["fencing"] += 1
    first_key = (first["lease"]["task_id"], first["lease"]["lease_id"],
                 first["lease"]["fencing"])
    second_key = (second["lease"]["task_id"], second["lease"]["lease_id"],
                  second["lease"]["fencing"])

    await worker.accept(first)
    with pytest.raises(WorkerUnavailable, match="INDEX_QUEUE_FULL"):
        await worker.accept(second)

    assert worker._queue.qsize() == 1
    assert worker._queued == {first_key}
    assert set(worker._heartbeats) == {first_key}
    assert second_key not in worker._heartbeats
    await worker.cancel({"task_id": first_key[0], "lease_id": first_key[1],
                         "fencing": first_key[2]})
    with pytest.raises(asyncio.CancelledError):
        await worker._heartbeats[first_key]
    await worker.close()
