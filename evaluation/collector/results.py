"""Process-local, single-use synchronous answer capture for evaluation."""
import asyncio
from copy import deepcopy

from knowflow_ai.adapters import ProcessingError


class RecordingAnswerService:
    def __init__(self, service, factories):
        self._service = service
        self._factories = factories

    async def answer(self, request):
        response, error_code = None, None
        try:
            response = await self._service.answer(request)
            return response
        except asyncio.CancelledError:
            error_code = "EXECUTION_CANCELLED"
            raise
        except ProcessingError as error:
            error_code = error.code
            raise
        except Exception:
            error_code = "AI_PROCESSING_FAILED"
            raise
        finally:
            request_id = request["request_id"]
            # Never await during cancellation cleanup: a second cancellation
            # would abort before the result lands. The trace store is local,
            # so a synchronous pop is atomic.
            try:
                trace = self._factories.traces.take_nowait(request_id)
            except ValueError:
                trace = None
            self._factories.results[request_id] = {
                "request_id": request_id, "response": deepcopy(response),
                "error_code": error_code, "trace": trace,
                # Reason codes and counts only; never answer, claim, or source text.
                "citation": deepcopy(getattr(self._service, "last_diagnostics", None)),
            }

    async def stream(self, request):
        async for event in self._service.stream(request):
            yield event
