from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import httpx
import pytest

from knowflow_ai.java_client import JavaGateway, JavaGatewayError
from knowflow_ai.protocol import CONTRACT_VERSION, ContractConsumer


ROOT = Path(__file__).resolve().parents[3]
SECRET = "test-only-java-gateway-secret-" + "x" * 32


def _case(definition):
    cases = json.loads((ROOT / "contracts/examples/protocol-cases.json").read_text(encoding="utf-8"))
    return deepcopy(next(case["payload"] for case in cases
                        if case["definition"] == definition and case["structurally_valid"]))


def _client(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    contract = ContractConsumer(ROOT / "contracts/schemas/protocol.schema.json")
    return JavaGateway("http://java.test", SECRET, contract, client), client


@pytest.mark.asyncio
async def test_source_read_checks_identity_length_and_content_digest():
    source = b"synthetic source body"
    dispatch = _case("IndexDispatch")
    dispatch["source"]["sha256"] = sha256(source).hexdigest()
    dispatch["source"]["format"] = "txt"

    async def handler(request):
        assert request.method == "POST"
        assert request.url.path.endswith("/source")
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        assert request.headers["accept"] == "application/octet-stream"
        return httpx.Response(200, content=source, headers={
            "cache-control": "no-store", "content-length": str(len(source)),
            "x-contract-version": CONTRACT_VERSION,
            "x-request-id": request.headers["x-request-id"],
            "x-task-id": dispatch["lease"]["task_id"],
            "x-document-id": dispatch["lease"]["document_id"],
            "x-content-version-id": dispatch["lease"]["content_version_id"],
            "x-source-format": "txt", "x-source-sha256": dispatch["source"]["sha256"],
        })

    gateway, client = _client(handler)
    try:
        assert await gateway.read_source(dispatch) == source
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_source_read_rejects_mismatched_hash_without_echoing_body():
    dispatch = _case("IndexDispatch")
    dispatch["source"]["sha256"] = sha256(b"expected").hexdigest()

    async def handler(request):
        return httpx.Response(200, content=b"private provider body", headers={
            "cache-control": "no-store", "content-length": "21",
            "x-contract-version": CONTRACT_VERSION,
            "x-request-id": request.headers["x-request-id"],
            "x-task-id": dispatch["lease"]["task_id"],
            "x-document-id": dispatch["lease"]["document_id"],
            "x-content-version-id": dispatch["lease"]["content_version_id"],
            "x-source-format": dispatch["source"]["format"],
            "x-source-sha256": dispatch["source"]["sha256"],
        })

    gateway, client = _client(handler)
    try:
        with pytest.raises(JavaGatewayError, match="SOURCE_UNAVAILABLE") as exc:
            await gateway.read_source(dispatch)
        assert "private provider body" not in str(exc.value)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_batch_and_completion_receipts_must_match_the_submitted_lease():
    batch = _case("IndexBatch")
    completion = _case("Completion")
    received = []

    async def handler(request):
        body = json.loads(request.content)
        received.append(body)
        if request.url.path.endswith("index-batches"):
            receipt = _case("IndexBatchReceipt")
            receipt.update(contract_version=CONTRACT_VERSION, request_id=body["request_id"],
                           task_id=body["lease"]["task_id"],
                           index_version_id=body["lease"]["index_version_id"],
                           batch_id=body["batch_id"], batch_sha256=body["batch_sha256"],
                           chunk_count=len(body["chunks"]))
        else:
            receipt = _case("CompletionReceipt")
            receipt.update(contract_version=CONTRACT_VERSION, request_id=body["request_id"],
                           task_id=body["lease"]["task_id"],
                           index_version_id=body["lease"]["index_version_id"])
        return httpx.Response(200, json=receipt)

    gateway, client = _client(handler)
    try:
        await gateway.write_batch(batch)
        await gateway.complete(completion)
        assert len(received) == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_batch_receipt_cannot_claim_a_different_lease():
    batch = _case("IndexBatch")

    async def handler(request):
        body = json.loads(request.content)
        receipt = _case("IndexBatchReceipt")
        receipt.update(contract_version=CONTRACT_VERSION, request_id=body["request_id"],
                       task_id="task-other", index_version_id=body["lease"]["index_version_id"],
                       batch_id=body["batch_id"], batch_sha256=body["batch_sha256"],
                       chunk_count=len(body["chunks"]))
        return httpx.Response(200, json=receipt)

    gateway, client = _client(handler)
    try:
        with pytest.raises(JavaGatewayError, match="JAVA_GATEWAY_INVALID_RESPONSE"):
            await gateway.write_batch(batch)
    finally:
        await client.aclose()
