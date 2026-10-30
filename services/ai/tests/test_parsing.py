from hashlib import sha256
import json
from pathlib import Path
import pytest
from knowflow_ai.parsing import parse_document,ParseFailure,ParseLimits,PARSER_PROFILE

FIXTURES=Path(__file__).parent/'fixtures/pdf'
ROOT=Path(__file__).resolve().parents[3]
IDS={'document_id':'doc-1','content_version_id':'content-1','file_id':'file-1'}


@pytest.mark.parametrize('format',['txt','md'])
def test_unicode_source_offsets_are_original(format):
    text='\ufeff# 中文🙂A\r\n\r\n**不能改写**\r\n'
    raw=text.encode('utf-8')
    result=parse_document(raw,format=format,**IDS)
    block=result.blocks[0]
    assert block.text==text and (block.char_start,block.char_end)==(0,len(text))
    assert result.file_sha256==sha256(raw).hexdigest()
    assert result.document_id=='doc-1' and result.content_version_id=='content-1' and result.file_id=='file-1'
    assert block.page is None and result.parser_profile==PARSER_PROFILE
    assert text not in repr(result) and text not in repr(block)


def test_all_seed_documents_preserve_source_text_and_evidence():
    root=ROOT/'evaluation/data/seed-v1'
    manifest=json.loads((root/'manifest.json').read_text())
    questions=json.loads((root/'questions.json').read_text())
    parsed={}
    for d in manifest['documents']:
        result=parse_document((root/d['path']).read_bytes(),format=d['format'],
            document_id=d['id'],content_version_id=d['content_version_id'],file_id=d['id'])
        parsed[d['id']]=result.blocks[0].text
        assert result.file_sha256==d['sha256']
    for q in questions:
        for e in q['evidence']:
            assert parsed[e['document_id']][e['start']:e['end']]==e['quote']


def test_pdf_chinese_pages_and_empty_page_keep_physical_page_numbers():
    raw=(FIXTURES/'chinese-pages.pdf').read_bytes()
    first=parse_document(raw,format='pdf',**IDS)
    second=parse_document(raw,format='pdf',**IDS)
    assert first==second
    assert first.pages==3 and first.empty_pages==(2,)
    assert [(b.sequence,b.page) for b in first.blocks]==[(0,1),(1,3)]
    assert '上传后等待索引完成' in first.blocks[0].text
    assert '删除后不可再次检索' in first.blocks[1].text
    assert all(b.char_start is None and b.char_end is None for b in first.blocks)


@pytest.mark.parametrize('filename,code',[('encrypted.pdf','PDF_ENCRYPTED'),('image-only.pdf','PDF_NO_TEXT'),
    ('blank.pdf','PDF_NO_TEXT'),('malformed.pdf','INVALID_PDF')])
def test_pdf_unprocessable_inputs_fail_with_fixed_error(filename,code,caplog):
    with pytest.raises(ParseFailure) as exc:
        parse_document((FIXTURES/filename).read_bytes(),format='pdf',**IDS)
    assert str(exc.value)==code
    assert not caplog.records


@pytest.mark.parametrize('raw,format,code',[(b'','txt','EMPTY_DOCUMENT'),(b'\xffPRIVATE','txt','INVALID_UTF8'),
    (b'\x00PRIVATE','md','INVALID_TEXT'),(b'  \r\n','txt','EMPTY_DOCUMENT'),
    (b'file','docx','UNSUPPORTED_FORMAT'),(b'notpdf PRIVATE','pdf','INVALID_PDF'),('text','txt','INVALID_INPUT_TYPE')])
def test_invalid_input_never_echoes_raw_content(raw,format,code):
    with pytest.raises(ParseFailure) as exc:parse_document(raw,format=format,**IDS)
    assert str(exc.value)==code


def test_limits_identity_and_exact_boundary():
    raw='中文🙂A'.encode('utf-8')
    assert parse_document(raw,format='txt',limits=ParseLimits(len(raw),1,4),**IDS).characters==4
    for limits,expected in [(ParseLimits(len(raw)-1,1,4),'FILE_TOO_LARGE'),(ParseLimits(100,1,3),'TEXT_TOO_LARGE')]:
        with pytest.raises(ParseFailure,match=expected):parse_document(raw,format='txt',limits=limits,**IDS)
    pdf=(FIXTURES/'chinese-pages.pdf').read_bytes()
    for limits,expected in [(ParseLimits(max_pdf_pages=2),'PDF_PAGE_LIMIT'),(ParseLimits(max_characters=1),'TEXT_TOO_LARGE')]:
        with pytest.raises(ParseFailure,match=expected):parse_document(pdf,format='pdf',limits=limits,**IDS)
    with pytest.raises(ParseFailure,match='INVALID_SOURCE_IDENTITY'):
        parse_document(b'text',format='txt',**{**IDS,'file_id':'../../private'})
    with pytest.raises(ValueError,match='INVALID_PARSE_LIMITS'):ParseLimits(max_pdf_pages=0)


def test_committed_pdf_fixture_hashes():
    for fixture in json.loads((FIXTURES/'manifest.json').read_text())['fixtures']:
        raw=(FIXTURES/fixture['path']).read_bytes()
        assert len(raw)==fixture['bytes'] and sha256(raw).hexdigest()==fixture['sha256']
