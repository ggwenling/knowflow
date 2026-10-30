"""Save parser assertions and hashes, never extracted text."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo
from knowflow_ai.parsing import parse_document,ParseFailure,PARSER_PROFILE

root=Path(__file__).resolve().parents[1]
repo=root.parents[1]
manifest=json.loads((repo/'evaluation/data/seed-v1/manifest.json').read_text())
checks=[]
for doc in manifest['documents']:
    raw=(repo/'evaluation/data/seed-v1'/doc['path']).read_bytes()
    result=parse_document(raw,format=doc['format'],document_id=doc['id'],content_version_id=doc['content_version_id'],file_id=doc['id'])
    assert result.file_sha256==doc['sha256'] and result.characters==doc['characters']
    checks.append({'id':doc['id'],'status':'PASSED','source_sha256':result.file_sha256,'characters':result.characters})
for name,expected in [('chinese-pages.pdf',None),('blank.pdf','PDF_NO_TEXT'),('image-only.pdf','PDF_NO_TEXT'),('encrypted.pdf','PDF_ENCRYPTED'),('malformed.pdf','INVALID_PDF')]:
    raw=(root/'tests/fixtures/pdf'/name).read_bytes()
    try:
        result=parse_document(raw,format='pdf',document_id='pdf-doc',content_version_id='v1',file_id='pdf-file')
        assert expected is None and result.pages==3 and result.empty_pages==(2,)
        assert [b.page for b in result.blocks]==[1,3]
        observed='PARSED'
    except ParseFailure as exc:
        assert str(exc)==expected
        observed=expected
    checks.append({'id':name,'status':'PASSED','observed':observed,'source_sha256':sha256(raw).hexdigest()})
report={'recorded_at':datetime.now(ZoneInfo('Asia/Hong_Kong')).isoformat(),'parser_profile':PARSER_PROFILE,
        'parser_sha256':sha256((root/'src/knowflow_ai/parsing.py').read_bytes()).hexdigest(),
        'git_head_at_run':subprocess.check_output(['git','rev-parse','HEAD'],text=True,cwd=root).strip(),
        'checks':checks,'external_model_calls':0,'scope':'Synthetic local samples only; no production capacity claim.'}
(root/'docs/evidence/parser-smoke.json').write_text(json.dumps(report,indent=2)+'\n')
print('Parser smoke:',len(checks),'sample assertions passed')
