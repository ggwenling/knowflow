"""Deterministic, source-preserving text segmentation for KF2-017."""
from bisect import bisect_left, bisect_right
from collections.abc import Iterator
from dataclasses import dataclass, field
from hashlib import sha256
import re

from .parsing import ParsedDocument, TextBlock


DEFAULT_MAX_CODEPOINTS = 800
DEFAULT_OVERLAP_CODEPOINTS = 100


class ChunkingFailure(ValueError):
    """Fixed, non-sensitive chunking error code."""


@dataclass(frozen=True)
class ChunkingConfig:
    max_codepoints: int = DEFAULT_MAX_CODEPOINTS
    overlap_codepoints: int = DEFAULT_OVERLAP_CODEPOINTS

    def __post_init__(self) -> None:
        if (type(self.max_codepoints) is not int or type(self.overlap_codepoints) is not int
                or self.max_codepoints < 1 or self.overlap_codepoints < 0
                or self.overlap_codepoints >= self.max_codepoints):
            raise ChunkingFailure("INVALID_CHUNKING_CONFIG")

    @property
    def profile_id(self) -> str:
        identity = f"unicode-codepoint-v1:{self.max_codepoints}:{self.overlap_codepoints}"
        return "chunk-" + sha256(identity.encode("ascii")).hexdigest()[:24]


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    sequence: int
    document_id: str
    content_version_id: str
    file_id: str
    parser_profile: str
    chunking_profile_id: str
    text: str = field(repr=False)
    text_sha256: str
    locator: dict[str, int | str]


_PARAGRAPH_BREAK = re.compile(r"\n(?:[ \t\r\f\v]*\n)+")
_MARKDOWN_HEADING = re.compile(r"(?m)^#{1,6}[ \t]+")
_SENTENCE_END = re.compile(r"[。！？!?；;](?:[”’\"')\]】）》]*)|\.(?:[”’\"')\]】）》]*)")
_SPACE = re.compile(r"\s+", re.UNICODE)


def _boundaries(text: str) -> tuple[tuple[int, int], ...]:
    """Return (position, priority): paragraph/title, sentence, then whitespace."""
    found: dict[int, int] = {}
    for match in _PARAGRAPH_BREAK.finditer(text):
        found[match.end()] = max(found.get(match.end(), 0), 3)
    for match in _MARKDOWN_HEADING.finditer(text):
        if match.start() > 0:
            found[match.start()] = max(found.get(match.start(), 0), 3)
    for match in _SENTENCE_END.finditer(text):
        position = match.end()
        # An ASCII period is a sentence boundary only before whitespace/end.
        if match.group().startswith(".") and position < len(text) and not text[position].isspace():
            continue
        found[position] = max(found.get(position, 0), 2)
    for match in _SPACE.finditer(text):
        found[match.end()] = max(found.get(match.end(), 0), 1)
    return tuple(sorted(found.items()))


def _index_boundaries(boundaries: tuple[tuple[int, int], ...]) -> tuple[tuple[int, ...], ...]:
    positions = ([], [], [])
    for position, priority in boundaries:
        positions[priority - 1].append(position)
    return tuple(tuple(group) for group in positions)


def _choose_end(text: str, start: int, hard_end: int,
                boundaries: tuple[tuple[int, int], ...],
                indexed: tuple[tuple[int, ...], ...] | None = None) -> int:
    if hard_end == len(text):
        return hard_end
    floor = start + max(1, (hard_end - start) // 2)
    if indexed is None:
        indexed = _index_boundaries(boundaries)
    # Prefer paragraph/title, sentence, and whitespace boundaries in that order.
    for positions in reversed(indexed):
        left = bisect_left(positions, floor)
        right = bisect_right(positions, hard_end)
        if left < right:
            return positions[right - 1]
    return hard_end


def _choose_overlap_start(end: int, start: int, text_length: int, overlap: int,
                          boundaries: tuple[tuple[int, int], ...],
                          indexed: tuple[tuple[int, ...], ...] | None = None) -> int:
    if overlap == 0:
        return end
    target = max(start + 1, end - overlap)
    # Snap forward to a nearby meaningful boundary so chunks do not start inside
    # a paragraph or sentence. This keeps the overlap at or below its configured cap.
    if indexed is None:
        indexed = _index_boundaries(boundaries)
    nearby = []
    for positions in indexed[1:]:
        index = bisect_left(positions, target)
        if index < len(positions) and positions[index] < end:
            nearby.append(positions[index])
    return min(nearby) if nearby else target


def _iter_split_text(text: str, maximum: int, overlap: int) -> Iterator[tuple[int, int]]:
    if not text:
        return
    boundaries = _boundaries(text)
    indexed = _index_boundaries(boundaries)
    start = 0
    while start < len(text):
        hard_end = min(start + maximum, len(text))
        end = _choose_end(text, start, hard_end, boundaries, indexed)
        if end <= start:
            raise ChunkingFailure("CHUNKING_NO_PROGRESS")
        yield start, end
        if end == len(text):
            break
        next_start = _choose_overlap_start(end, start, len(text), overlap, boundaries, indexed)
        if next_start <= start or next_start >= end:
            # Very short final intervals may not contain the configured overlap.
            next_start = end
        start = next_start


def _split_text(text: str, maximum: int, overlap: int) -> tuple[tuple[int, int], ...]:
    return tuple(_iter_split_text(text, maximum, overlap))


def _block_locator(block: TextBlock, start: int, end: int, source_format: str) -> dict[str, int | str]:
    if source_format == "pdf":
        if block.page is None:
            raise ChunkingFailure("PDF_PAGE_MISSING")
        return {"kind": "pdf_page", "page": block.page}
    base = block.char_start
    if base is None:
        raise ChunkingFailure("TEXT_SOURCE_RANGE_MISSING")
    return {"kind": "text_range", "start": base + start, "end": base + end,
            "unit": "unicode_code_point"}


def _iter_document_chunks(document: ParsedDocument,
                          config: ChunkingConfig | None = None) -> Iterator[Chunk]:
    """Yield chunks in source order without normalizing source positions."""
    config = config or ChunkingConfig()
    if document.format not in ("txt", "md", "pdf"):
        raise ChunkingFailure("UNSUPPORTED_SOURCE_FORMAT")
    sequence = 0
    for block in document.blocks:
        if not block.text:
            continue
        for start, end in _iter_split_text(
                block.text, config.max_codepoints, config.overlap_codepoints):
            text = block.text[start:end]
            locator = _block_locator(block, start, end, document.format)
            identity = "\0".join((
                document.document_id, document.content_version_id, document.file_id,
                document.file_sha256, document.parser_profile, config.profile_id,
                str(block.page or 0), str(start), str(end),
                sha256(text.encode("utf-8")).hexdigest(),
            ))
            chunk_id = "chunk-" + sha256(identity.encode("utf-8")).hexdigest()
            yield Chunk(
                chunk_id=chunk_id, sequence=sequence, document_id=document.document_id,
                content_version_id=document.content_version_id, file_id=document.file_id,
                parser_profile=document.parser_profile, chunking_profile_id=config.profile_id,
                text=text, text_sha256=sha256(text.encode("utf-8")).hexdigest(), locator=locator,
            )
            sequence += 1


def chunk_document(document: ParsedDocument, config: ChunkingConfig | None = None) -> tuple[Chunk, ...]:
    """Split parsed source blocks without normalizing or losing source positions."""
    return tuple(_iter_document_chunks(document, config))
