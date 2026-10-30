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
args=parser.parse_args()

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

class SlowFixture(BaseHTTPRequestHandler):
    def do_GET(self):
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
with tempfile.TemporaryDirectory(prefix='knowflow-java-python-') as temporary, tempfile.TemporaryFile() as pylog, tempfile.TemporaryFile() as javalog:
    temp=Path(temporary);java=temp/'api';java.mkdir()
    # Only source/build inputs; no local .env, target, settings or secret files are copied.
    for name in ('pom.xml','mvnw'):
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
        command=['./mvnw','-B','-q']
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
        assert int(suite.attrib['tests'])==5 and int(suite.attrib['failures'])==0 and int(suite.attrib['errors'])==0
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        slow.shutdown();slow.server_close()
    for log in (pylog,javalog):
        log.seek(0);assert secret.encode() not in log.read(), 'SECRET_IN_PROCESS_LOG'
report={'recorded_at':datetime.now(ZoneInfo('Asia/Hong_Kong')).isoformat(),
        'git_head_at_run':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
        'contract_version':'0.2.0-draft.2','java_tests':5,'failures':0,'errors':0,
        'real_java_http_service':True,'real_java_webclient':True,'real_python_http_service':True,
        'timeout_target':'Separate local slow fixture; real Java responseTimeout config, not a Python business route.',
        'public_java_gateway_error_mapping':'Not implemented by A yet; probe validates transport and Python error bodies only.',
        'external_model_calls':0,'database_calls':0,'secret_in_process_logs':False,
        'app_sha256':sha256((root/'src/knowflow_ai/app.py').read_bytes()).hexdigest(),
        'java_client_config_sha256':sha256((repo/'services/api/src/main/java/com/knowflow/api/config/AiHttpClientConfiguration.java').read_bytes()).hexdigest(),
        'java_probe_sha256':sha256(source.read_bytes()).hexdigest()}
(root/'docs/evidence/java-python-smoke.json').write_text(json.dumps(report,indent=2)+'\n')
print('real Java service/WebClient + Python HTTP:',report['java_tests'],'integration checks passed')
