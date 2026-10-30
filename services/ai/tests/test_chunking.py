from hashlib import sha256
import json
from pathlib import Path

import pytest

from knowflow_ai.chunking import ChunkingConfig, ChunkingFailure, chunk_document
from knowflow_ai.parsing import parse_document


ROOT = Path(__file__).resolve().parents[3]
IDS = {"document_id": "doc-1", "content_version_id": "content-1", "file_id": "file-1"}


@pytest.mark.parametrize("format", ["txt", "md"])
def test_ranges_reproduce_original_unicode_source_and_ids_are_stable(format):
    text = "\ufeff# 标题🙂\r\n\r\n第一段有中文。" + "甲乙丙丁" * 260 + "\r\n\r\n## 下一节\r\n内容保持原样。"
    raw = text.encode("utf-8")
    parsed = parse_document(raw, format=format, **IDS)
    config = ChunkingConfig(max_codepoints=240, overlap_codepoints=32)
    chunks = chunk_document(parsed, config)
    repeated = chunk_document(parsed, config)

    assert chunks == repeated
    assert len(chunks) > 5
    assert [chunk.sequence for chunk in chunks] == list(range(len(chunks)))
    assert all(len(chunk.text) <= config.max_codepoints for chunk in chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert all(len(chunk.chunk_id) == 70 and chunk.chunk_id.startswith("chunk-") for chunk in chunks)
    for chunk in chunks:
        start, end = chunk.locator["start"], chunk.locator["end"]
        assert chunk.locator == {"kind": "text_range", "start": start, "end": end,
                                 "unit": "unicode_code_point"}
        assert end > start and text[start:end] == chunk.text
        assert chunk.text_sha256 == sha256(chunk.text.encode("utf-8")).hexdigest()
        assert chunk.document_id == IDS["document_id"]
        assert chunk.content_version_id == IDS["content_version_id"]

    for first, second in zip(chunks, chunks[1:]):
        left_end = first.locator["end"]
        right_start = second.locator["start"]
        assert 0 <= left_end - right_start <= config.overlap_codepoints


def test_paragraphs_and_markdown_headings_are_preferred_boundaries():
    source = ("# 第一节\n" + "第一段。" * 30 + "\n\n"
              + "第二段！" * 30 + "\n\n## 第二节\n" + "第三段？" * 30)
    parsed = parse_document(source.encode(), format="md", **IDS)
    chunks = chunk_document(parsed, ChunkingConfig(max_codepoints=180, overlap_codepoints=20))
    boundaries = {chunk.locator["end"] for chunk in chunks[:-1]}
    assert any(source[:position].endswith("\n\n") for position in boundaries)
    assert all(source[chunk.locator["start"]:chunk.locator["end"]] == chunk.text for chunk in chunks)


def test_pdf_chunks_keep_physical_page_identity_and_never_cross_pages():
    raw = (ROOT / "services/ai/tests/fixtures/pdf/chinese-pages.pdf").read_bytes()
    parsed = parse_document(raw, format="pdf", **IDS)
    chunks = chunk_document(parsed, ChunkingConfig(max_codepoints=8, overlap_codepoints=2))

    assert chunks
    assert {chunk.locator["page"] for chunk in chunks} == {1, 3}
    assert all(chunk.locator == {"kind": "pdf_page", "page": chunk.locator["page"]}
               for chunk in chunks)
    assert all(len(chunk.text) <= 8 for chunk in chunks)
    assert all(chunk.sequence == index for index, chunk in enumerate(chunks))
    for page in parsed.blocks:
        page_chunks = [chunk for chunk in chunks if chunk.locator["page"] == page.page]
        assert all(chunk.text in page.text for chunk in page_chunks)


def test_seed_evidence_remains_retrievable_from_chunks():
    root = ROOT / "evaluation/data/seed-v1"
    manifest = json.loads((root / "manifest.json").read_text())
    questions = json.loads((root / "questions.json").read_text())
    chunks_by_document = {}
    for item in manifest["documents"]:
        document = parse_document((root / item["path"]).read_bytes(), format=item["format"],
                                  document_id=item["id"], content_version_id=item["content_version_id"],
                                  file_id=item["id"])
        chunks_by_document[item["id"]] = chunk_document(document)

    for question in questions:
        for evidence in question["evidence"]:
            quote = evidence["quote"]
            located = [chunk for chunk in chunks_by_document[evidence["document_id"]]
                       if chunk.locator["kind"] == "text_range"
                       and chunk.locator["start"] <= evidence["start"]
                       and chunk.locator["end"] >= evidence["end"]]
            assert located, question["id"]
            assert any(chunk.text[evidence["start"] - chunk.locator["start"]:
                                  evidence["end"] - chunk.locator["start"]] == quote for chunk in located)


@pytest.mark.parametrize("maximum,overlap", [(0, 0), (10, -1), (10, 10), (True, 0), (1.5, 0)])
def test_invalid_chunk_profiles_fail_closed(maximum, overlap):
    with pytest.raises(ChunkingFailure, match="INVALID_CHUNKING_CONFIG"):
        ChunkingConfig(maximum, overlap)


def test_chunk_identity_changes_when_content_version_or_profile_changes():
    parsed = parse_document(b"Stable source text.", format="txt", **IDS)
    original = chunk_document(parsed)[0]
    changed_version = parse_document(b"Stable source text.", format="txt",
                                     **{**IDS, "content_version_id": "content-2"})
    changed_profile = chunk_document(parsed, ChunkingConfig(32, 4))[0]
    assert chunk_document(changed_version)[0].chunk_id != original.chunk_id
    assert changed_profile.chunking_profile_id != original.chunking_profile_id
    assert changed_profile.chunk_id != original.chunk_id
