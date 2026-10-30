import copy
import asyncio
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

import pytest

from knowflow_ai.java_client import JavaGatewayError
from knowflow_ai.protocol import ContractConsumer
from knowflow_ai.worker import IndexWorker, WorkerUnavailable


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
async def test_worker_writes_draft6_batches_and_manifest_then_completes():
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
