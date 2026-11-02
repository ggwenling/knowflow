"""Validate retrieval traces and map runtime source IDs to public answer IDs."""
from hashlib import md5, sha256
import re
from uuid import UUID


_SOURCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)


def public_source_id(question_id, source_id):
    try:
        question = str(UUID(question_id))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("INVALID_QUESTION_ID") from None
    if not isinstance(source_id, str) or not _SOURCE.fullmatch(source_id):
        raise ValueError("INVALID_SOURCE_ID")
    # Java UUID.nameUUIDFromBytes hashes the bytes directly (no namespace).
    digest = md5((question + ":" + source_id).encode("utf-8"), usedforsecurity=False).digest()
    return str(UUID(bytes=digest, version=3))


def map_retrieval(question_id, rows, mappings):
    """Map one top-10 trace to scorer spans after validating source bytes.

    Mapping keys are runtime (document, content, index) IDs. Values contain
    the reviewed dataset document/version IDs, exact UTF-8 source bytes and
    the independently pinned SHA-256. This is not a production API.
    """
    if not isinstance(rows, list) or len(rows) > 10 or not isinstance(mappings, dict):
        raise ValueError("INVALID_TRACE")
    result, seen = [], set()
    for row in rows:
        try:
            key = (row["document_id"], row["content_version_id"], row["index_version_id"])
            mapped = mappings[key]
            source = mapped["source_bytes"]
            if not isinstance(source, bytes) or sha256(source).hexdigest() != mapped["source_sha256"]:
                raise ValueError("SOURCE_HASH_MISMATCH")
            text = source.decode("utf-8")
            locator = row["locator"]
            start, end = locator["start"], locator["end"]
            if (locator["kind"] != "text_range" or locator["unit"] != "unicode_code_point"
                    or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)):
                raise ValueError("INVALID_SOURCE_RANGE")
            text_hash = sha256(text[start:end].encode("utf-8")).hexdigest()
            if text_hash != row["text_sha256"]:
                raise ValueError("SPAN_HASH_MISMATCH")
            source_id = public_source_id(question_id, row["source_id"])
            if source_id in seen:
                raise ValueError("DUPLICATE_SOURCE_ID")
            seen.add(source_id)
            if not isinstance(mapped["dataset_document_id"], str) or not mapped["dataset_document_id"] or not isinstance(mapped["dataset_content_version_id"], str) or not mapped["dataset_content_version_id"]:
                raise ValueError("INVALID_DATASET_MAPPING")
            result.append({"document_id": mapped["dataset_document_id"],
                           "content_version_id": mapped["dataset_content_version_id"],
                           "start": start, "end": end, "text_sha256": text_hash,
                           "source_id": source_id})
        except (KeyError, TypeError, UnicodeDecodeError):
            raise ValueError("INVALID_TRACE_MAPPING") from None
    return result
