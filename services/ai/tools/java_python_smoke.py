"""B-owned cross-service probe; runs unmodified Java source in a disposable copy."""
import argparse
from datetime import datetime
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from xml.etree import ElementTree
from zoneinfo import ZoneInfo
import httpx

root=Path(__file__).resolve().parents[1]
repo=root.parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--maven-settings',type=Path)
parser.add_argument('--output', type=Path)
parser.add_argument('--java-target')
parser.add_argument('--require-clean', action='store_true')
args=parser.parse_args()

def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=repo, text=True,
                                   encoding='utf-8').strip()

clean_before = not git('status', '--porcelain')
if args.require_clean and not clean_before:
    raise RuntimeError('INTEGRATION_WORKTREE_NOT_CLEAN')
java_target = git('rev-parse', args.java_target) if args.java_target else None
if java_target:
    subprocess.run(['git', 'merge-base', '--is-ancestor', java_target, 'HEAD'], cwd=repo, check=True)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

class SlowFixture(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get('X-Request-ID') == 'java-old-version-fixture':
            body = json.dumps({'status':'UP', 'contract_version':'0.2.0-draft.2',
                               'request_id':'java-old-version-fixture'}).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers(); self.wfile.write(body)
            return
        if self.headers.get('X-Request-ID') == 'java-draft5-fixture':
            body = json.dumps({'status':'UP', 'contract_version':'0.2.0-draft.5',
                               'request_id':'java-draft5-fixture'}).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers(); self.wfile.write(body)
            return
        time.sleep(36)  # deliberately exceed Java's real 30s response timeout
        self.send_response(200);self.end_headers()
    def log_message(self,*args):pass

slow=ThreadingHTTPServer(('127.0.0.1',0),SlowFixture);slow.daemon_threads=True
threading.Thread(target=slow.serve_forever,daemon=True).start()
secret=secrets.token_urlsafe(48)
port=free_port()
env={**os.environ,'KNOWFLOW_INTERNAL_SHARED_SECRET':secret,'KNOWFLOW_AI_BASE_URL':f'http://127.0.0.1:{port}',
     'KNOWFLOW_JP01_SLOW_URL':f'http://127.0.0.1:{slow.server_port}',
     'KNOWFLOW_JP01_UNREACHABLE_URL':f'http://127.0.0.1:{free_port()}'}
for key in ('EMBEDING_KEY','DEEPSEEK_API_KEY'):env.pop(key,None)
env['KNOWFLOW_CONTRACT_PATH'] = str(repo / 'contracts/schemas/protocol.schema.json')
env['SPRING_PROFILES_ACTIVE'] = ''
with tempfile.TemporaryDirectory(prefix='knowflow-java-python-') as temporary, tempfile.TemporaryFile() as pylog, tempfile.TemporaryFile() as javalog:
    temp=Path(temporary);java=temp/'api';java.mkdir()
    # Only source/build inputs; no local .env, target, settings or secret files are copied.
    wrapper = 'mvnw.cmd' if os.name == 'nt' else 'mvnw'
    for name in ('pom.xml',wrapper):
        shutil.copy2(repo/'services/api'/name,java/name)
    for name in ('src','.mvn'):
        shutil.copytree(repo/'services/api'/name,java/name)
    source=root/'tests/integration/JavaPythonHealthIntegrationTest.java'
    shutil.copy2(source,java/'src/test/java/com/knowflow/api'/source.name)
    process=subprocess.Popen([sys.executable,'-m','uvicorn','knowflow_ai.app:create_app','--factory','--host','127.0.0.1','--port',str(port),'--no-access-log'],env=env,stdout=pylog,stderr=pylog)
    try:
        with httpx.Client(timeout=2,trust_env=False) as client:
            for _ in range(100):
                if process.poll() is not None:raise RuntimeError('PYTHON_START_FAILED')
                try:
                    if client.get(env['KNOWFLOW_AI_BASE_URL']+'/health/live').status_code==200:break
                except httpx.TransportError:pass
                time.sleep(.05)
            else:raise RuntimeError('PYTHON_START_TIMEOUT')
        command=['cmd','/c',wrapper,'-B','-q'] if os.name == 'nt' else ['./mvnw','-B','-q']
        if args.maven_settings:command+=['-s',str(args.maven_settings.resolve())]
        command+=['-Dtest=JavaPythonHealthIntegrationTest','test']
        result=subprocess.run(command,cwd=java,env=env,stdout=javalog,stderr=javalog,timeout=240)
        if result.returncode:
            javalog.seek(0)
            diagnostic=javalog.read().decode(errors='replace').replace(secret,'[REDACTED]')
            print(diagnostic[-4000:])
            raise RuntimeError('JAVA_PYTHON_PROBE_FAILED')
        xml=next((java/'target/surefire-reports').glob('TEST-*JavaPythonHealthIntegrationTest.xml'))
        suite=ElementTree.parse(xml).getroot()
        assert int(suite.attrib['tests'])==9 and int(suite.attrib['failures'])==0 and int(suite.attrib['errors'])==0
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        slow.shutdown();slow.server_close()
    for log in (pylog,javalog):
        log.seek(0);assert secret.encode() not in log.read(), 'SECRET_IN_PROCESS_LOG'
clean_after = not git('status', '--porcelain')
if args.require_clean and not clean_after:
    raise RuntimeError('INTEGRATION_WORKTREE_CHANGED')
report={'recorded_at':datetime.now(ZoneInfo('Asia/Hong_Kong')).isoformat(),
        'git_head_at_run':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,
                                                  text=True,encoding='utf-8').strip(),
        'contract_version':'0.2.0-draft.6','java_tests':9,'failures':0,'errors':0,
        'clean_worktree_before':clean_before, 'clean_worktree_after':clean_after,
        'integration_tree':git('rev-parse','HEAD^{tree}'), 'java_target':java_target,
        'schema_sha256':sha256((repo/'contracts/schemas/protocol.schema.json').read_bytes()).hexdigest(),
        'examples_sha256':sha256((repo/'contracts/examples/protocol-cases.json').read_bytes()).hexdigest(),
        'consumer_sha256':sha256((root/'src/knowflow_ai/protocol.py').read_bytes()).hexdigest(),
        'real_java_health_client':True, 'java_health_client_accepts_draft6':True,
        'java_health_client_rejects_draft2_fixture':True, 'java_health_client_rejects_draft5_fixture':True,
        'java_health_client_five_second_timeout':True,
        'java_health_client_sha256':sha256((repo/'services/api/src/main/java/com/knowflow/api/ai/AiInternalHealthClient.java').read_bytes()).hexdigest(),
        'real_java_http_service':True,'real_java_webclient':True,'real_python_http_service':True,
        'timeout_target':'Separate local slow fixture; real Java responseTimeout config, not a Python business route.',
        'public_java_gateway_error_mapping':'An upstream AI HTTP 503 maps to a retryable public 502 in DocumentApiIntegrationTest using a local HTTP fixture; this health-only probe does not exercise that route.',
        'external_model_calls':0,'database_calls':0,'secret_in_process_logs':False,
        'app_sha256':sha256((root/'src/knowflow_ai/app.py').read_bytes()).hexdigest(),
        'java_client_config_sha256':sha256((repo/'services/api/src/main/java/com/knowflow/api/config/AiHttpClientConfiguration.java').read_bytes()).hexdigest(),
        'java_probe_sha256':sha256(source.read_bytes()).hexdigest()}
output = args.output or root/'docs/evidence/java-python-smoke.json'
output.write_text(json.dumps(report,indent=2)+'\n', encoding='utf-8')
print('real Java service/WebClient + Python HTTP:',report['java_tests'],'integration checks passed')
