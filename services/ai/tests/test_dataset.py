import importlib.util
import json
from pathlib import Path
import shutil
import pytest

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('seed_validation', ROOT/'evaluation/data/tools/validate_seed.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_seed_all_sources_versions_and_splits():
    report=module.validate()
    assert report['documents']==10 and report['questions']==15 and report['unanswerable']==3


@pytest.mark.parametrize('damage',['source','offset','version','split'])
def test_seed_tampering_is_detected(tmp_path,damage):
    root=tmp_path/'seed';shutil.copytree(ROOT/'evaluation/data/seed-v1',root)
    qs=json.loads((root/'questions.json').read_text())
    if damage=='source':
        p=next((root/'documents').glob('*.md'));p.write_text(p.read_text()+'篡改')
    elif damage=='offset':qs[0]['evidence'][0]['start']+=1
    elif damage=='version':qs[0]['evidence'][0]['content_version_id']='wrong'
    else:qs[1]['split']='holdout'
    (root/'questions.json').write_text(json.dumps(qs))
    with pytest.raises(AssertionError):module.validate(root)
