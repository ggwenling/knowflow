"""Launch an actual Uvicorn process, report only redacted assertions."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx

root = Path(__file__).resolve().parents[1]
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
secret = secrets.token_urlsafe(48)
env = {**os.environ, 'KNOWFLOW_INTERNAL_SHARED_SECRET': secret}
# Service availability must not depend on model credentials.
for key in ('EMBEDING_KEY', 'DEEPSEEK_API_KEY'):
    env.pop(key, None)
with tempfile.TemporaryFile() as log:
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'knowflow_ai.app:create_app', '--factory',
        '--host','127.0.0.1','--port',str(port),'--no-access-log'], env=env, stdout=log, stderr=log)
    try:
        url = f'http://127.0.0.1:{port}'
        with httpx.Client(base_url=url, timeout=2, trust_env=False) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('SERVICE_START_FAILED')
                try:
                    if client.get('/health/live').status_code == 200: break
                except httpx.TransportError: pass
                time.sleep(.05)
            else: raise RuntimeError('SERVICE_START_TIMEOUT')
            auth = {'Authorization':'Bearer '+secret, 'X-Request-ID':'java-ready-smoke-1'}
            checks = {}
            r = client.get('/internal/v1/health', headers=auth)
            checks['authenticated_health'] = r.status_code == 200 and r.json()['request_id'] == 'java-ready-smoke-1'
            checks['request_id_header'] = r.headers['x-request-id'] == 'java-ready-smoke-1'
            checks['missing_credential'] = client.get('/internal/v1/health').status_code == 401
            checks['wrong_credential'] = client.get('/internal/v1/health',headers={'Authorization':'Bearer wrong'}).status_code == 401
            checks['unknown_route'] = client.get('/internal/unknown',headers=auth).status_code == 404
            r = client.post('/internal/v1/health', headers=auth)
            checks['wrong_method'] = r.status_code == 405 and 'GET' in r.headers['allow']
            checks['business_disabled'] = client.post('/internal/v1/answers',headers=auth,json={'question':'synthetic'}).status_code == 404
            assert all(checks.values()), 'PROCESS_SMOKE_FAILED'
    finally:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    log.seek(0)
    assert secret.encode() not in log.read(), 'SECRET_IN_LOG'
checks['no_secret_in_process_log'] = True
report = {'recorded_at': datetime.now(ZoneInfo('Asia/Hong_Kong')).isoformat(), 'checks':checks,
          'external_model_calls':0, 'java_webclient_called':False,
          'scope':'Real Python HTTP process only; Java caller separately required.',
          'git_head_at_run':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
          'app_sha256':hashlib.sha256((root/'src/knowflow_ai/app.py').read_bytes()).hexdigest()}
(root/'docs/evidence/process-smoke.json').write_text(json.dumps(report,indent=2)+'\n')
print('real Python process smoke:',len(checks),'passed')
