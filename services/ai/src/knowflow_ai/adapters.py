"""Capability boundaries for later workers; no provider calls or fallback model."""
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar
import math


class ProcessingError(RuntimeError):
    def __init__(self, code: str, status: int = 502, *, retryable: bool | None = None):
        super().__init__(code)
        self.code, self.status = code, status
        self.retryable = status in (502, 504) if retryable is None else retryable


class ModelAdapter(Protocol):
    async def embed(self, texts: list[str], *, request_id: str) -> dict[str, Any]: ...
    async def generate(self, question: str, context: list[str], *, request_id: str) -> dict[str, Any]: ...


class IndexExecutor(Protocol):
    async def execute(self, dispatch: dict[str, Any]) -> None: ...
    async def cancel(self, execution_id: str) -> None: ...


class Retriever(Protocol):
    async def retrieve(self, question: str, trusted_scope: dict[str, Any]) -> list[dict[str, Any]]: ...


def validate_provider_result(result: dict[str, Any], model: str, *, count: int | None = None, dimensions: int = 1024):
    if result.get('model') != model:
        raise ProcessingError('PROVIDER_MODEL_MISMATCH')
    if count is not None:
        rows = result.get('data')
        if not isinstance(rows, list) or len(rows) != count:
            raise ProcessingError('EMBEDDING_COUNT_MISMATCH')
        indexes = set()
        for row in rows:
            if not isinstance(row, dict) or type(row.get('index')) is not int:
                raise ProcessingError('INVALID_EMBEDDING_INDEX')
            indexes.add(row['index'])
            v = row.get('embedding')
            if not isinstance(v, list) or len(v) != dimensions:
                raise ProcessingError('EMBEDDING_DIMENSION_MISMATCH')
            if any(type(n) not in (int, float) or not math.isfinite(n) for n in v) or not any(v):
                raise ProcessingError('INVALID_EMBEDDING_VALUE')
        if indexes != set(range(count)):
            raise ProcessingError('INVALID_EMBEDDING_INDEX')


T = TypeVar('T')


async def within_deadline(operation: Callable[[], Awaitable[T]], seconds: float) -> T:
    if not 0 < seconds <= 30:
        raise ValueError('INVALID_TIMEOUT')
    try:
        async with asyncio.timeout(seconds):
            return await operation()
    except TimeoutError:
        raise ProcessingError('PROCESSING_TIMEOUT', 504) from None
    except asyncio.CancelledError:
        raise
    except ProcessingError:
        raise
    except Exception:
        raise ProcessingError('AI_PROCESSING_FAILED') from None
