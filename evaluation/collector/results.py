"""Process-local, single-use synchronous answer capture for evaluation."""
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
        except ProcessingError as error:
            error_code = error.code
            raise
        except Exception:
            error_code = "AI_PROCESSING_FAILED"
            raise
        finally:
            request_id = request["request_id"]
            try:
                trace = await self._factories.traces.take(request_id)
            except ValueError:
                trace = None
            self._factories.results[request_id] = {
                "request_id": request_id, "response": deepcopy(response),
                "error_code": error_code, "trace": trace,
            }

    async def stream(self, request):
        async for event in self._service.stream(request):
            yield event
