import asyncio
import copy
import json
from pathlib import Path
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from knowflow_ai.app import create_app
from knowflow_ai.config import Settings, ConfigurationError
from knowflow_ai.protocol import ContractConsumer, InvalidMessage
from knowflow_ai.adapters import ProcessingError, validate_provider_result, within_deadline

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


def test_health_no_models_and_disabled_routes(client):
    assert client.get('/health/live').json() == {'status': 'UP'}
    r = client.get('/internal/v1/health', headers={**AUTH, 'X-Request-ID': 'java-trace-01'})
    assert r.status_code == 200
    assert r.json() == {'status': 'UP', 'contract_version': '0.2.0-draft.4', 'request_id': 'java-trace-01'}
    assert r.headers['x-request-id'] == 'java-trace-01'
    for path in ('/internal/v1/index-executions', '/internal/v1/answers', '/docs', '/openapi.json'):
        assert client.post(path, headers=AUTH, json={'owner_id': 'forged'}).status_code == 404


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
    with TestClient(app) as client:
        r = client.post('/internal/test-validation', headers=AUTH, json={'count': 'PRIVATE', 'owner_id': 'private'})
        assert r.status_code == 400
        assert 'PRIVATE' not in r.text and 'owner_id' not in r.text
        r = client.get('/internal/test-failure', headers=AUTH)
        assert r.status_code == 500 and r.json()['code'] == 'INTERNAL_ERROR'
        assert 'PRIVATE' not in r.text
        r = client.get('/internal/test-timeout', headers=AUTH)
        assert r.status_code == 504 and r.json()['code'] == 'PROCESSING_TIMEOUT'


def test_consumer_matches_all_shared_examples(app):
    examples = json.loads((ROOT / 'contracts/examples/protocol-cases.json').read_text())
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


def test_health_consumes_draft4_examples_without_version_fallback(app, client):
    cases = json.loads((Path(__file__).parent / 'fixtures/internal-health-draft4.json').read_text())
    for case in cases:
        if case['valid']:
            app.state.contract.validate('InternalHealth', case['payload'])
        else:
            with pytest.raises(InvalidMessage):
                app.state.contract.validate('InternalHealth', case['payload'])
    response = client.get('/internal/v1/health', headers=AUTH)
    app.state.contract.validate('InternalHealth', response.json())
    assert response.json()['contract_version'] == '0.2.0-draft.4'


@pytest.mark.parametrize('mutation', ['draft2', 'draft3', 'same-json-different-bytes'])
def test_startup_rejects_old_and_modified_schema_without_bypass(tmp_path, mutation):
    raw = (ROOT / 'contracts/schemas/protocol.schema.json').read_bytes()
    if mutation == 'same-json-different-bytes':
        raw += b'\n'
    else:
        old = b'0.2.0-draft.2' if mutation == 'draft2' else b'0.2.0-draft.3'
        raw = raw.replace(b'0.2.0-draft.4', old)
    path = tmp_path / 'schema.json'
    path.write_bytes(raw)
    with pytest.raises(ConfigurationError, match='CONTRACT_HASH_MISMATCH'):
        create_app(Settings(SECRET, path))
