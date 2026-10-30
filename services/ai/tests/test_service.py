import asyncio
import copy
import json
from pathlib import Path
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
import knowflow_ai.app as ai_app
from knowflow_ai.app import create_app
from knowflow_ai.config import Settings, ConfigurationError
from knowflow_ai.protocol import ContractConsumer, InvalidMessage
from knowflow_ai.adapters import ProcessingError, validate_provider_result, within_deadline
from knowflow_ai.embedding import EmbeddingSettings
from knowflow_ai.worker import WorkerUnavailable

ROOT = Path(__file__).resolve().parents[3]
SECRET = 'test-only-' + 'a' * 40
AUTH = {'Authorization': f'Bearer {SECRET}'}


@pytest.fixture
def app():
    return create_app(Settings(SECRET))


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def test_startup_fails_closed_without_echoing_secret(tmp_path):
    for value in ('', 'x', 'a'*32+'\nPRIVATE', 'x'*257, '密码'*32, 'a'*32+' secret'):
        with pytest.raises(ConfigurationError) as exc:
            Settings(value)
        assert value not in str(exc.value) or not value
    assert SECRET not in repr(Settings(SECRET))
    with pytest.raises(ConfigurationError, match='CONTRACT_UNAVAILABLE'):
        create_app(Settings(SECRET, tmp_path / 'missing.json'))
    changed = tmp_path / 'changed.json'
    changed.write_text('{}')
    with pytest.raises(ConfigurationError, match='CONTRACT_HASH_MISMATCH'):
        create_app(Settings(SECRET, changed))


def test_health_does_not_probe_models_or_database(client):
    assert client.get('/health/live').json() == {'status': 'UP'}
    r = client.get('/internal/v1/health', headers={**AUTH, 'X-Request-ID': 'java-trace-01'})
    assert r.status_code == 200
    assert r.json() == {'status': 'UP', 'contract_version': '0.2.0-draft.6', 'request_id': 'java-trace-01'}
    assert r.headers['x-request-id'] == 'java-trace-01'
    for path in ('/docs', '/openapi.json'):
        assert client.post(path, headers=AUTH, json={'owner_id': 'forged'}).status_code == 404
    for path in ('/internal/v1/index-executions', '/internal/v1/answers'):
        assert client.post(path, headers=AUTH, json={'owner_id': 'forged'}).status_code == 400


@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Bearer wrong'},
    [('Authorization', f'Bearer {SECRET}'), ('Authorization', 'Bearer wrong')]])
def test_auth_before_routing(client, headers):
    r = client.get('/internal/v1/health', headers=headers)
    assert r.status_code == 401
    assert r.json()['code'] == 'UNAUTHENTICATED'
    assert r.headers['www-authenticate'] == 'Bearer'
    assert SECRET not in r.text


def test_request_id_invalid_or_duplicated_is_regenerated(client):
    for headers in ({'X-Request-ID': '<script>private'}, {'X-Request-ID': 'a'*129},
                    [('X-Request-ID', 'first'), ('X-Request-ID', 'second')]):
        r = client.get('/health/live', headers=headers)
        assert len(r.headers['x-request-id']) == 36


def test_404_405_and_error_schema(client, app):
    for method, path, status, code in [('GET','/missing',404,'ENDPOINT_UNAVAILABLE'),
        ('POST','/internal/v1/health',405,'INVALID_REQUEST')]:
        r = client.request(method, path, headers=AUTH)
        assert r.status_code == status
        assert r.json()['code'] == code
        app.state.contract.validate('Error', r.json())
        if status == 405:
            assert 'GET' in r.headers['allow']


def test_unhandled_and_validation_errors_redact_inputs(app):
    class Payload(BaseModel):
        model_config = ConfigDict(extra='forbid')
        count: int
    @app.post('/internal/test-validation')
    async def validated(payload: Payload):
        return {'count': payload.count}
    @app.get('/internal/test-failure')
    async def broken():
        raise RuntimeError('PRIVATE provider key and input')
    @app.get('/internal/test-timeout')
    async def timeout():
        raise ProcessingError('PROCESSING_TIMEOUT', 504)
    @app.get('/internal/test-non-retryable-model-failure')
    async def non_retryable_model_failure():
        raise ProcessingError('MODEL_FAILURE', 502, retryable=False)
    @app.get('/internal/test-invalid-provider-input')
    async def invalid_provider_input():
        raise ProcessingError('INVALID_EMBEDDING_INPUT', 400, retryable=False)
    with TestClient(app) as client:
        r = client.post('/internal/test-validation', headers=AUTH, json={'count': 'PRIVATE', 'owner_id': 'private'})
        assert r.status_code == 400
        assert 'PRIVATE' not in r.text and 'owner_id' not in r.text
        r = client.get('/internal/test-failure', headers=AUTH)
        assert r.status_code == 500 and r.json()['code'] == 'INTERNAL_ERROR'
        assert 'PRIVATE' not in r.text
        r = client.get('/internal/test-timeout', headers=AUTH)
        assert r.status_code == 504 and r.json()['code'] == 'PROCESSING_TIMEOUT'
        assert r.json()['retryable'] is True
        r = client.get('/internal/test-non-retryable-model-failure', headers=AUTH)
        assert r.status_code == 502 and r.json()['code'] == 'AI_PROCESSING_FAILED'
        assert r.json()['retryable'] is False
        r = client.get('/internal/test-invalid-provider-input', headers=AUTH)
        assert r.status_code == 400 and r.json()['code'] == 'INVALID_REQUEST'
        assert r.json()['retryable'] is False


def test_consumer_matches_all_shared_examples(app):
    examples = json.loads((ROOT / 'contracts/examples/protocol-cases.json').read_text(encoding='utf-8'))
    for case in examples:
        if case['structurally_valid']:
            app.state.contract.validate(case['definition'], case['payload'])
        else:
            with pytest.raises(InvalidMessage):
                app.state.contract.validate(case['definition'], case['payload'])
    valid = next(x['payload'] for x in examples if x['definition'] == 'IndexDispatch' and x['structurally_valid'])
    for key, value in [('contract_version', 'unsupported'), ('file_path', '/etc/passwd')]:
        changed = copy.deepcopy(valid); changed[key] = value
        with pytest.raises(InvalidMessage):
            app.state.contract.validate('IndexDispatch', changed)


def test_provider_validation_never_accepts_wrong_model_or_vectors():
    valid = {'model': 'BAAI/bge-m3', 'data': [{'index': 0, 'embedding': [1.0]*1024}]}
    validate_provider_result(valid, 'BAAI/bge-m3', count=1)
    for changed in ({**valid, 'model':'wrong'}, {**valid, 'model':None},
                    {**valid, 'data':[{'index':0,'embedding':[0]*1024}]},
                    {**valid, 'data':[{'index':0,'embedding':[float('nan')]*1024}]},
                    {**valid, 'data':[{'index':0,'embedding':[1]}]}):
        with pytest.raises(ProcessingError):
            validate_provider_result(changed, 'BAAI/bge-m3', count=1)


@pytest.mark.asyncio
async def test_deadline_cancel_and_failure_redaction():
    cancelled = asyncio.Event()
    async def slow():
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.set()
    with pytest.raises(ProcessingError, match='PROCESSING_TIMEOUT'):
        await within_deadline(slow, .01)
    assert cancelled.is_set()
    async def failure():
        raise RuntimeError('PRIVATE')
    with pytest.raises(ProcessingError, match='AI_PROCESSING_FAILED') as exc:
        await within_deadline(failure, 1)
    assert 'PRIVATE' not in str(exc.value)
    task = asyncio.create_task(within_deadline(slow, 30))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_health_consumes_draft6_examples_without_version_fallback(app, client):
    cases = json.loads((Path(__file__).parent / 'fixtures/internal-health-draft6.json').read_text(encoding='utf-8'))
    for case in cases:
        if case['valid']:
            app.state.contract.validate('InternalHealth', case['payload'])
        else:
            with pytest.raises(InvalidMessage):
                app.state.contract.validate('InternalHealth', case['payload'])
    response = client.get('/internal/v1/health', headers=AUTH)
    app.state.contract.validate('InternalHealth', response.json())
    assert response.json()['contract_version'] == '0.2.0-draft.6'


@pytest.mark.parametrize('mutation', ['draft2', 'draft3', 'draft4', 'draft5', 'same-json-different-bytes'])
def test_startup_rejects_old_and_modified_schema_without_bypass(tmp_path, mutation):
    raw = (ROOT / 'contracts/schemas/protocol.schema.json').read_bytes()
    if mutation == 'same-json-different-bytes':
        raw += b'\n'
    else:
        old = {'draft2': b'0.2.0-draft.2', 'draft3': b'0.2.0-draft.3',
               'draft4': b'0.2.0-draft.4', 'draft5': b'0.2.0-draft.5'}[mutation]
        raw = raw.replace(b'0.2.0-draft.6', old)
    path = tmp_path / 'schema.json'
    path.write_bytes(raw)
    with pytest.raises(ConfigurationError, match='CONTRACT_HASH_MISMATCH'):
        create_app(Settings(SECRET, path))


def test_full_index_queue_returns_retryable_503_not_accepted(client, app, monkeypatch):
    cases = json.loads((ROOT / 'contracts/examples/protocol-cases.json').read_text(encoding='utf-8'))
    dispatch = copy.deepcopy(next(case['payload'] for case in cases
                                  if case['definition'] == 'IndexDispatch'
                                  and case['structurally_valid']))
    dispatch['request_id'] = 'queue-full-request'
    dispatch['runtime_profile_id'] = 'runtime-default'
    dispatch['lease_expires_at'] = '2099-01-01T00:00:00+00:00'

    async def reject_when_full(_dispatch):
        raise WorkerUnavailable('INDEX_QUEUE_FULL')

    monkeypatch.setattr(EmbeddingSettings, 'from_environment', staticmethod(lambda: None))
    monkeypatch.setattr(app.state.index_worker, 'accept', reject_when_full)
    response = client.post('/internal/v1/index-executions',
                           headers={**AUTH, 'X-Request-ID': dispatch['request_id']},
                           json=dispatch)

    assert response.status_code == 503
    assert response.json()['code'] == 'AI_PROCESSING_FAILED'
    assert response.json()['request_id'] == dispatch['request_id']
    assert response.json()['retryable'] is True
    assert 'result' not in response.json()


def test_index_dispatch_without_embedding_credential_is_not_accepted(client, app, monkeypatch):
    cases = json.loads((ROOT / 'contracts/examples/protocol-cases.json').read_text(encoding='utf-8'))
    dispatch = copy.deepcopy(next(case['payload'] for case in cases
                                  if case['definition'] == 'IndexDispatch'
                                  and case['structurally_valid']))
    dispatch['request_id'] = 'missing-embedding-key'
    dispatch['runtime_profile_id'] = 'runtime-default'
    dispatch['lease_expires_at'] = '2099-01-01T00:00:00+00:00'
    accepted = []

    async def record_acceptance(payload):
        accepted.append(payload)

    monkeypatch.delenv('KNOWFLOW_EMBEDDING_KEY_ENV', raising=False)
    monkeypatch.delenv('EMBEDING_KEY', raising=False)
    monkeypatch.setattr(app.state.index_worker, 'accept', record_acceptance)
    response = client.post('/internal/v1/index-executions',
                           headers={**AUTH, 'X-Request-ID': dispatch['request_id']},
                           json=dispatch)

    assert response.status_code == 503
    assert response.json()['code'] == 'AI_PROCESSING_FAILED'
    assert response.json()['request_id'] == dispatch['request_id']
    assert response.json()['retryable'] is True
    assert 'result' not in response.json()
    assert accepted == []


@pytest.mark.parametrize('missing_credential', ['embedding', 'llm'])
def test_answer_without_model_credential_does_not_construct_service(monkeypatch, missing_credential):
    monkeypatch.delenv('KNOWFLOW_EMBEDDING_KEY_ENV', raising=False)
    monkeypatch.delenv('EMBEDING_KEY', raising=False)
    monkeypatch.delenv('KNOWFLOW_LLM_KEY_ENV', raising=False)
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    if missing_credential == 'llm':
        monkeypatch.setenv('EMBEDING_KEY', 'e' * 40)

    payload = {
        'contract_version': '0.2.0-draft.6',
        'request_id': f'missing-{missing_credential}-key',
        'question': 'How is this document indexed?',
        'scope': {
            'owner_id': 'owner-1',
            'knowledge_base_id': 'kb-1',
            'snapshot_id': 'snapshot-1',
            'indexes': [{
                'document_id': 'document-1',
                'content_version_id': 'content-1',
                'index_version_id': 'index-1',
            }],
        },
    }
    constructed = []

    def record_construction(*args, **kwargs):
        constructed.append((args, kwargs))
        raise AssertionError('AnswerService must not be constructed without model credentials')

    monkeypatch.setattr(ai_app, 'AnswerService', record_construction)
    answer_app = create_app(Settings(SECRET, ai_database_url='postgresql://unused.invalid/knowflow'))
    with TestClient(answer_app) as answer_client:
        response = answer_client.post('/internal/v1/answers',
                                       headers={**AUTH, 'X-Request-ID': payload['request_id']},
                                       json=payload)

    assert response.status_code == 503
    assert response.json()['code'] == 'AI_PROCESSING_FAILED'
    assert response.json()['request_id'] == payload['request_id']
    assert response.json()['retryable'] is True
    assert 'answer' not in response.json()
    assert constructed == []
    assert 'unused.invalid' not in response.text
