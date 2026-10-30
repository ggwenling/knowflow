"""Verify exact source positions, provenance, question groups and reference coverage."""
import hashlib,json
from pathlib import Path


def validate(root=None):
    root=root or Path(__file__).resolve().parents[1]/'seed-v1'
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'));questions=json.loads((root/'questions.json').read_text(encoding='utf-8'))
    assert manifest['synthetic'] is True
    docs={};texts={}
    for d in manifest['documents']:
        path=(root/d['path']).resolve();assert path.is_relative_to(root.resolve())
        raw=path.read_bytes();text=raw.decode('utf-8')
        assert hashlib.sha256(raw).hexdigest()==d['sha256']
        assert len(raw)==d['bytes'] and len(text)==d['characters']
        assert d['id'] not in docs and d['license']=='CC0-1.0'
        docs[d['id']]=d;texts[d['id']]=text
    assert len(docs)>=10 and len(questions)>=15
    ids=set();groups={};counts={'development':0,'holdout':0,'unanswerable':0};covered=set()
    for q in questions:
        assert q['id'] not in ids;ids.add(q['id'])
        assert q['question'] and q['reference_answer']
        assert groups.setdefault(q['leakage_group'],q['split'])==q['split'], 'split leakage'
        counts[q['split']]+=1
        assert bool(q['evidence'])==q['answerable']
        counts['unanswerable']+=not q['answerable']
        for e in q['evidence']:
            d=docs[e['document_id']];text=texts[d['id']];covered.add(d['id'])
            assert e['content_version_id']==d['content_version_id'] and e['unit']=='unicode_code_point'
            assert 0<=e['start']<e['end']<=len(text)
            assert text[e['start']:e['end']]==e['quote']
            assert text.count('\n',0,e['start'])+1==e['line_start']
            assert text.count('\n',0,e['end'])+1==e['line_end']
    assert covered==set(docs) and counts['unanswerable']>=3 and counts['holdout']>0
    return {'documents':len(docs),'questions':len(questions),**counts,'all_evidence_positions_verified':True}

if __name__=='__main__':print(json.dumps(validate(),ensure_ascii=False))
