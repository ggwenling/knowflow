"""Authenticated internal AI service for lease-fenced indexing and answers."""
import asyncio
from contextlib import aclosing, asynccontextmanager
import hmac
import json
import os
import re
import uuid
from typing import Any
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, StreamingResponse
from .config import ConfigurationError, Settings
from .protocol import CONTRACT_VERSION, ContractConsumer, ErrorBody, InvalidMessage
from .adapters import ProcessingError
from .answering import AnswerService, LlmSettings
from .embedding import EmbeddingSettings
from .langchain_answer import CustomModel, LangChainAnswerModel
from .java_client import JavaGateway
from .provider_probe import ProviderReadiness
from .worker import IndexWorker, WorkerUnavailable, validate_runtime_profile

ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', re.ASCII)


class ClosingStreamingResponse(StreamingResponse):
    def __init__(self, *args, on_close=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_close = on_close

    async def __call__(self, scope, receive, send):
        streaming = asyncio.create_task(self.stream_response(send))
        disconnect = asyncio.create_task(self.listen_for_disconnect(receive))
        try:
            await asyncio.wait((streaming, disconnect), return_when=asyncio.FIRST_COMPLETED)
            if streaming.done():
                streaming.result()
        finally:
            for task in (streaming, disconnect):
                if not task.done():
                    task.cancel()
            await asyncio.gather(streaming, disconnect, return_exceptions=True)
            try:
                await self.body_iterator.aclose()
            finally:
                if self.on_close is not None:
                    self.on_close()


class QuestionAdmission:
    def __init__(self, limit: int):
        self.limit = limit
        self.active = 0

    def try_acquire(self) -> bool:
        if self.active >= self.limit:
            return False
        self.active += 1
        return True

    def release(self) -> None:
        self.active -= 1


async def await_answer_or_disconnect(request: Request, operation):
    task = asyncio.create_task(operation())
    try:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise asyncio.CancelledError
            await asyncio.wait((task,), timeout=0.1)
        return task.result()
    except BaseException:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        raise


def failure(request_id, status, code, *, headers=None, retryable=None):
    # Messages are constants. Never serialize exception text or validation inputs.
    if retryable is None:
        retryable = status in (502, 504)
    payload = ErrorBody(request_id=request_id, code=code, message=code,
                        retryable=retryable).model_dump()
    return JSONResponse(payload, status_code=status, headers=headers)


class BoundaryMiddleware:
    def __init__(self, app, secret):
        self.app, self.secret = app, secret.encode('ascii')

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = scope.get('headers', [])
        ids = [v for k, v in headers if k.lower() == b'x-request-id']
        proposed = ids[0].decode('latin-1') if len(ids) == 1 else ''
        request_id = proposed if ID_PATTERN.fullmatch(proposed) else str(uuid.uuid4())
        scope.setdefault('state', {})['request_id'] = request_id
        started, finished = False, False

        async def safe_send(message):
            nonlocal started, finished
            if message['type'] == 'http.response.start':
                started = True
                message['headers'] = [(k, v) for k, v in message.get('headers', [])
                                      if k.lower() != b'x-request-id'] + [(b'x-request-id', request_id.encode('ascii'))]
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                finished = True
            await send(message)

        auth = [v for k, v in headers if k.lower() == b'authorization']
        public = (scope['path'] in ('/health/live', '/health/ready')
                  and scope['method'] == 'GET')
        authenticated = False
        if len(auth) == 1:
            scheme, sep, credential = auth[0].partition(b' ')
            authenticated = (scheme.lower() == b'bearer' and bool(sep)
                             and hmac.compare_digest(credential, self.secret))
        if not public and not authenticated:
            return await failure(request_id, 401, 'UNAUTHENTICATED',
                                 headers={'WWW-Authenticate': 'Bearer'})(scope, receive, safe_send)
        try:
            await self.app(scope, receive, safe_send)
        except Exception:
            # Starlette may have sent its handled error already. No raw exception logging.
            if not started:
                await failure(request_id, 500, 'INTERNAL_ERROR')(scope, receive, safe_send)
            elif not finished:
                await safe_send({'type': 'http.response.body', 'body': b''})


def create_app(settings: Settings | None = None, *, worker_factory=None,
               answer_service_factory=None, provider_readiness_factory=None) -> FastAPI:
    settings = settings or Settings.from_environment()
    contract = ContractConsumer(settings.contract_path)
    worker_factory = worker_factory if worker_factory is not None else IndexWorker
    use_langchain = answer_service_factory is None
    answer_service_factory = answer_service_factory or AnswerService

    @asynccontextmanager
    async def lifespan(app):
        gateway = JavaGateway(settings.java_base_url, settings.internal_secret, contract)
        worker = None
        try:
            worker = worker_factory(gateway)
            app.state.java_gateway = gateway
            app.state.index_worker = worker
            await worker.start()
            yield
        finally:
            try:
                if worker is not None:
                    await worker.close()
            finally:
                await gateway.aclose()

    app = FastAPI(title='KnowFlow internal AI', docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.contract = contract
    app.state.question_admission = QuestionAdmission(settings.max_concurrent_questions)
    app.state.provider_readiness = (
        provider_readiness_factory() if provider_readiness_factory is not None
        else ProviderReadiness.from_environment())
    app.add_middleware(BoundaryMiddleware, secret=settings.internal_secret)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = {404: 'ENDPOINT_UNAVAILABLE', 405: 'INVALID_REQUEST',
                401: 'UNAUTHENTICATED', 403: 'SCOPE_DENIED',
                503: 'AI_PROCESSING_FAILED'}.get(exc.status_code, 'INVALID_REQUEST')
        headers = {'Allow': exc.headers['Allow']} if exc.headers and 'Allow' in exc.headers else None
        return failure(request.state.request_id, exc.status_code, code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return failure(request.state.request_id, 400, 'INVALID_REQUEST')

    @app.exception_handler(InvalidMessage)
    async def invalid_contract_message(request: Request, exc: InvalidMessage):
        return failure(request.state.request_id, 400, 'INVALID_REQUEST')

    @app.exception_handler(ProcessingError)
    async def processing_error(request: Request, exc: ProcessingError):
        code = {400: 'INVALID_REQUEST', 504: 'PROCESSING_TIMEOUT'}.get(
            exc.status, 'AI_PROCESSING_FAILED')
        return failure(request.state.request_id, exc.status, code, retryable=exc.retryable)

    @app.exception_handler(WorkerUnavailable)
    async def worker_unavailable(request: Request, exc: WorkerUnavailable):
        return failure(request.state.request_id, 503, 'AI_PROCESSING_FAILED', retryable=True)

    @app.exception_handler(ConfigurationError)
    async def configuration_error(request: Request, exc: ConfigurationError):
        return failure(request.state.request_id, 503, 'AI_PROCESSING_FAILED', retryable=True)

    @app.get('/health/live')
    async def live():
        return {'status': 'UP'}

    @app.get('/health/ready')
    async def ready(request: Request):
        result = await request.app.state.provider_readiness.check()
        status = 200 if result['status'] == 'UP' else 503
        return JSONResponse(result, status_code=status)

    @app.get('/internal/v1/health')
    async def internal_health(request: Request):
        return {'status': 'UP', 'contract_version': CONTRACT_VERSION, 'request_id': request.state.request_id}

    @app.post('/internal/v1/index-executions', status_code=202)
    async def dispatch_index(request: Request, payload: dict[str, Any]):
        contract.validate('IndexDispatch', payload)
        if payload['request_id'] != request.state.request_id:
            raise ProcessingError('INVALID_REQUEST', 400, retryable=False)
        if payload['runtime_profile_id'] != settings.runtime_profile_id:
            raise ProcessingError('INVALID_REQUEST', 400, retryable=False)
        embedding_settings = EmbeddingSettings.from_environment()
        validate_runtime_profile(payload, embedding_settings)
        await request.app.state.index_worker.accept(payload)
        receipt = {'contract_version': CONTRACT_VERSION, 'request_id': payload['request_id'],
                   'task_id': payload['lease']['task_id'],
                   'index_version_id': payload['lease']['index_version_id'], 'result': 'ACCEPTED'}
        contract.validate('IndexExecutionReceipt', receipt)
        return receipt

    @app.post('/internal/v1/index-executions/{task_id}/cancel', status_code=204)
    async def cancel_index(request: Request, task_id: str, payload: dict[str, Any]):
        contract.validate('CancelExecution', payload)
        if payload['request_id'] != request.state.request_id or payload['task_id'] != task_id:
            raise ProcessingError('INVALID_REQUEST', 400, retryable=False)
        await request.app.state.index_worker.cancel(payload)
        return Response(status_code=204)

    def build_answer(request, payload, custom=None):
        contract.validate('TrustedAnswerRequest', payload)
        if payload['request_id'] != request.state.request_id:
            raise ProcessingError('INVALID_REQUEST', 400, retryable=False)
        if not settings.ai_database_url:
            raise ProcessingError('AI_PROCESSING_FAILED', 503, retryable=True)
        embedding_settings = EmbeddingSettings.from_environment()
        llm_settings = custom if custom is not None else LlmSettings.from_environment()
        options = {"embedding_settings": embedding_settings, "model_profile": {
            "embedding_model_profile_id": embedding_settings.model,
            "llm_model_profile_id": f"custom:{custom.id}" if custom is not None else llm_settings.model,
        }}
        if use_langchain or custom is not None:
            options['llm_factory'] = lambda: LangChainAnswerModel(llm_settings)
        return answer_service_factory(settings.ai_database_url, contract, **options)

    def require_custom():
        if os.environ.get('KNOWFLOW_CUSTOM_LLM_ENABLED', '').lower() != 'true':
            raise ProcessingError('AI_PROCESSING_FAILED', 503, retryable=False)

    async def execute_answer(request, payload, custom=None):
        service = build_answer(request, payload, custom)
        admission = request.app.state.question_admission
        if not admission.try_acquire():
            raise ProcessingError('AI_PROCESSING_FAILED', 503, retryable=True)
        try:
            return await await_answer_or_disconnect(request, lambda: service.answer(payload))
        finally:
            admission.release()

    async def execute_stream(request, payload, custom=None):
        service = build_answer(request, payload, custom)
        admission = request.app.state.question_admission
        if not admission.try_acquire():
            raise ProcessingError('AI_PROCESSING_FAILED', 503, retryable=True)

        async def frames():
            async with aclosing(service.stream(payload)) as events:
                async for event in events:
                    data = json.dumps(event, ensure_ascii=False, separators=(',', ':'))
                    yield f"event: {event['event']}\ndata: {data}\n\n"

        return ClosingStreamingResponse(frames(), media_type='text/event-stream',
                                        on_close=admission.release,
                                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.post('/internal/v1/answers')
    async def answer(request: Request, payload: dict[str, Any]):
        return await execute_answer(request, payload)

    @app.post('/internal/v1/answers/stream')
    async def stream_answer(request: Request, payload: dict[str, Any]):
        return await execute_stream(request, payload)

    class CustomAnswer(BaseModel):
        model_config = ConfigDict(extra='forbid')
        request: dict[str, Any]
        model: CustomModel

    @app.post('/internal/v1/custom-answers')
    async def custom_answer(request: Request, payload: CustomAnswer):
        require_custom()
        return await execute_answer(request, payload.request, payload.model)

    @app.post('/internal/v1/custom-answers/stream')
    async def custom_stream(request: Request, payload: CustomAnswer):
        require_custom()
        return await execute_stream(request, payload.request, payload.model)

    @app.post('/internal/v1/llm-models/probe')
    async def probe_model(request: Request, payload: CustomModel):
        require_custom()
        admission = request.app.state.question_admission
        if not admission.try_acquire():
            raise ProcessingError('AI_PROCESSING_FAILED', 503, retryable=True)

        async def probe():
            model = LangChainAnswerModel(payload, probe=True)
            try:
                async with asyncio.timeout(10):
                    return {'supports_tools': await model.probe_capabilities()}
            except TimeoutError:
                raise ProcessingError('PROCESSING_TIMEOUT', 504) from None
            finally:
                await model.aclose()

        try:
            return await await_answer_or_disconnect(request, probe)
        finally:
            admission.release()

    return app
