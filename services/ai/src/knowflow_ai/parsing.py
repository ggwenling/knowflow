"""KF2-016: byte inputs only. No OCR, URL fetch, filesystem access or state writes."""
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
import logging
import re
from pypdf import PdfReader

# Library diagnostics can include document details. Service diagnostics use fixed codes.
_pdf_logger = logging.getLogger('pypdf')
_pdf_logger.addHandler(logging.NullHandler())
_pdf_logger.propagate = False
PARSER_PROFILE = 'text-v1+pypdf-6.21.4'
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', re.ASCII)


class ParseFailure(ValueError):
    """Only a fixed non-sensitive error code."""


@dataclass(frozen=True)
class ParseLimits:
    # JP-01 development proposals, not validated production performance promises.
    max_file_bytes: int = 8 * 1024 * 1024
    max_pdf_pages: int = 200
    max_characters: int = 200_000

    def __post_init__(self):
        if any(type(x) is not int or x < 1 for x in (self.max_file_bytes,self.max_pdf_pages,self.max_characters)):
            raise ValueError('INVALID_PARSE_LIMITS')


@dataclass(frozen=True)
class TextBlock:
    sequence: int
    text: str = field(repr=False)
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    document_id: str
    content_version_id: str
    file_id: str
    file_sha256: str
    format: str
    blocks: tuple[TextBlock, ...] = field(repr=False)
    characters: int
    pages: int | None
    empty_pages: tuple[int, ...] = ()
    parser_profile: str = PARSER_PROFILE


def parse_document(data: bytes, *, format: str, document_id: str, content_version_id: str,
                   file_id: str, limits: ParseLimits | None = None) -> ParsedDocument:
    limits = limits or ParseLimits()
    if not all(isinstance(x,str) and IDENTIFIER.fullmatch(x) for x in (document_id,content_version_id,file_id)):
        raise ParseFailure('INVALID_SOURCE_IDENTITY')
    if format not in ('txt','md','pdf'):
        raise ParseFailure('UNSUPPORTED_FORMAT')
    if not isinstance(data,bytes):
        raise ParseFailure('INVALID_INPUT_TYPE')
    if len(data) > limits.max_file_bytes:
        raise ParseFailure('FILE_TOO_LARGE')
    if not data:
        raise ParseFailure('EMPTY_DOCUMENT')
    if format in ('txt','md'):
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            raise ParseFailure('INVALID_UTF8') from None
        if '\x00' in text:
            raise ParseFailure('INVALID_TEXT')
        # Classify Unicode whitespace (plus the existing BOM allowance) without
        # stripping or normalizing the original text used for source offsets.
        if not any(ch != '\ufeff' and not ch.isspace() for ch in text):
            raise ParseFailure('EMPTY_DOCUMENT')
        if len(text) > limits.max_characters:
            raise ParseFailure('TEXT_TOO_LARGE')
        # Keep BOM, CRLF, Markdown syntax and emoji: offsets refer to original decoded bytes.
        return ParsedDocument(document_id,content_version_id,file_id,sha256(data).hexdigest(),format,
                              (TextBlock(0,text,char_start=0,char_end=len(text)),),len(text),None)
    if not data.startswith(b'%PDF-'):
        raise ParseFailure('INVALID_PDF')
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ParseFailure('PDF_ENCRYPTED')
        pages = len(reader.pages)
        if pages > limits.max_pdf_pages:
            raise ParseFailure('PDF_PAGE_LIMIT')
        blocks = []; empty = []; characters = 0
        for page_number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ''
            characters += len(text)
            if characters > limits.max_characters:
                raise ParseFailure('TEXT_TOO_LARGE')
            if text.strip():
                blocks.append(TextBlock(len(blocks),text,page=page_number))
            else:
                empty.append(page_number)
        if not blocks:
            raise ParseFailure('PDF_NO_TEXT')
        return ParsedDocument(document_id,content_version_id,file_id,sha256(data).hexdigest(),format,
                              tuple(blocks),characters,pages,tuple(empty))
    except ParseFailure:
        raise
    except Exception:
        raise ParseFailure('INVALID_PDF') from None
