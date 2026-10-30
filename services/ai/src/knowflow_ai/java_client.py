"""Authenticated, bounded client for Java's lease and storage gateways."""
import hashlib
import uuid
from urllib.parse import quote

import httpx

from .adapters import ProcessingError
from .protocol import CONTRACT_VERSION


class JavaGatewayError(ProcessingError):
    def __init__(self, code: str, status: int, *, retryable: bool = False):
        super().__init__(code, status, retryable=retryable)


class JavaGateway:
    def __init__(self, base_url: str, secret: str, contract,
                 client: httpx.AsyncClient | None = None):
        self._base = base_url.rstrip("/")
        self._secret = secret
        self._contract = contract
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(12.0),
                                                   follow_redirects=False, trust_env=True)

    async def aclose(self):
        if self._owns_client:
            await self._client.aclose()

    def _headers(self, request_id: str):
        return {"Authorization": f"Bearer {self._secret}",
                "Content-Type": "application/json", "Accept": "application/json",
                "X-Request-ID": request_id}

    async def _post(self, path: str, body: dict, definition: str, request_id: str) -> dict:
        try:
            response = await self._client.post(self._base + path, json=body,
                                               headers=self._headers(request_id))
        except httpx.TimeoutException:
            raise JavaGatewayError("JAVA_GATEWAY_TIMEOUT", 504, retryable=True) from None
        except httpx.HTTPError:
            raise JavaGatewayError("JAVA_GATEWAY_UNAVAILABLE", 502, retryable=True) from None
        if response.status_code >= 400:
            code = "JAVA_GATEWAY_REJECTED"
            try:
                error = response.json()
                if isinstance(error, dict) and error.get("code") in {
                    "LEASE_REJECTED", "DOCUMENT_UNAVAILABLE", "RESOURCE_NOT_FOUND",
                    "BATCH_CONFLICT", "COMPLETION_CONFLICT", "SCOPE_DENIED",
                    "UNAUTHENTICATED", "INDEX_INTEGRITY_FAILED", "INVALID_REQUEST",
                }:
                    code = error["code"]
            except (ValueError, TypeError):
                pass
            raise JavaGatewayError(code, response.status_code,
                                   retryable=response.status_code >= 500)
        try:
            payload = response.json()
            self._contract.validate(definition, payload)
        except (ValueError, TypeError):
            raise JavaGatewayError("JAVA_GATEWAY_INVALID_RESPONSE", 502) from None
        if payload.get("request_id") != request_id or payload.get("contract_version") != CONTRACT_VERSION:
            raise JavaGatewayError("JAVA_GATEWAY_INVALID_RESPONSE", 502)
        return payload

    async def read_source(self, dispatch: dict) -> bytes:
        lease = dispatch["lease"]
        request_id = str(uuid.uuid4())
        body = {"contract_version": CONTRACT_VERSION, "request_id": request_id, "lease": lease}
        path = f"/internal/v1/tasks/{quote(lease['task_id'], safe='')}/source"
        headers = self._headers(request_id)
        headers["Accept"] = "application/octet-stream"
        try:
            async with self._client.stream("POST", self._base + path, json=body,
                                           headers=headers) as response:
                if response.status_code != 200:
                    raise JavaGatewayError("SOURCE_UNAVAILABLE", response.status_code,
                                           retryable=response.status_code >= 500)
                headers = response.headers
                expected = {
                    "x-contract-version": CONTRACT_VERSION,
                    "x-request-id": request_id,
                    "x-task-id": lease["task_id"],
                    "x-document-id": lease["document_id"],
                    "x-content-version-id": lease["content_version_id"],
                    "x-source-format": dispatch["source"]["format"],
                    "x-source-sha256": dispatch["source"]["sha256"],
                }
                if any(headers.get(name) != value for name, value in expected.items()):
                    raise JavaGatewayError("SOURCE_UNAVAILABLE", 502)
                if headers.get("cache-control") != "no-store":
                    raise JavaGatewayError("SOURCE_UNAVAILABLE", 502)
                length = int(headers.get("content-length", "-1"))
                if not 1 <= length <= 8 * 1024 * 1024:
                    raise JavaGatewayError("SOURCE_UNAVAILABLE", 502)
                contents = bytearray()
                async for part in response.aiter_bytes():
                    contents.extend(part)
                    if len(contents) > length:
                        raise JavaGatewayError("SOURCE_UNAVAILABLE", 502)
                if len(contents) != length or hashlib.sha256(contents).hexdigest() != expected["x-source-sha256"]:
                    raise JavaGatewayError("SOURCE_UNAVAILABLE", 502)
                return bytes(contents)
        except httpx.TimeoutException:
            raise JavaGatewayError("JAVA_GATEWAY_TIMEOUT", 504, retryable=True) from None
        except httpx.HTTPError:
            raise JavaGatewayError("JAVA_GATEWAY_UNAVAILABLE", 502, retryable=True) from None

    async def heartbeat(self, lease: dict):
        request_id = str(uuid.uuid4())
        body = {"contract_version": CONTRACT_VERSION, "request_id": request_id, "lease": lease}
        task_id = quote(lease["task_id"], safe="")
        receipt = await self._post(f"/internal/v1/tasks/{task_id}/heartbeat", body,
                                   "HeartbeatReceipt", request_id)
        if receipt.get("task_id") != lease["task_id"]:
            raise JavaGatewayError("LEASE_REJECTED", 409)
        return receipt["lease_expires_at"]

    async def write_batch(self, batch: dict):
        request_id = batch["request_id"]
        task_id = quote(batch["lease"]["task_id"], safe="")
        receipt = await self._post(f"/internal/v1/tasks/{task_id}/index-batches", batch,
                                   "IndexBatchReceipt", request_id)
        expected = {"task_id": batch["lease"]["task_id"],
                    "index_version_id": batch["lease"]["index_version_id"],
                    "batch_id": batch["batch_id"], "batch_sha256": batch["batch_sha256"]}
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise JavaGatewayError("JAVA_GATEWAY_INVALID_RESPONSE", 502)

    async def complete(self, completion: dict):
        request_id = completion["request_id"]
        task_id = quote(completion["lease"]["task_id"], safe="")
        receipt = await self._post(f"/internal/v1/tasks/{task_id}/completion", completion,
                                   "CompletionReceipt", request_id)
        if receipt.get("task_id") != completion["lease"]["task_id"]:
            raise JavaGatewayError("JAVA_GATEWAY_INVALID_RESPONSE", 502)
