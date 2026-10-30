"""Authenticated internal AI service for lease-fenced indexing and answers."""
from contextlib import asynccontextmanager
import hmac
import re
import uuid
from typing import Any
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from .config import ConfigurationError, Settings
from .protocol import CONTRACT_VERSION, ContractConsumer, ErrorBody, InvalidMessage
from .adapters import ProcessingError
from .answering import AnswerService, LlmSettings
from .embedding import EmbeddingSettings
from .java_client import JavaGateway
from .worker import IndexWorker, WorkerUnavailable

ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', re.ASCII)


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
        public = scope['path'] == '/health/live' and scope['method'] == 'GET'
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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    contract = ContractConsumer(settings.contract_path)

    @asynccontextmanager
    async def lifespan(app):
        gateway = JavaGateway(settings.java_base_url, settings.internal_secret, contract)
        worker = IndexWorker(gateway)
        app.state.java_gateway = gateway
        app.state.index_worker = worker
        await worker.start()
        try:
            yield
        finally:
            await worker.close()
            await gateway.aclose()

    app = FastAPI(title='KnowFlow internal AI', docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.contract = contract
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
        EmbeddingSettings.from_environment()
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

    @app.post('/internal/v1/answers')
    async def answer(request: Request, payload: dict[str, Any]):
        contract.validate('TrustedAnswerRequest', payload)
        if payload['request_id'] != request.state.request_id:
            raise ProcessingError('INVALID_REQUEST', 400, retryable=False)
        if not settings.ai_database_url:
            raise ProcessingError('AI_PROCESSING_FAILED', 503, retryable=True)
        EmbeddingSettings.from_environment()
        LlmSettings.from_environment()
        service = AnswerService(settings.ai_database_url, contract)
        return await service.answer(payload)

    return app
