"""Deterministic draft.5 index-batch digest shared by Java and Python."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import hashlib
import re

_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _field(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return str(len(encoded)).encode("ascii") + b":" + encoded + b"\n"


def canonical_batch_bytes(batch: dict) -> bytes:
    """Build the exact draft.5 digest stream; execution token and request ID are omitted."""
    lease = batch["lease"]
    values = [
        lease["task_id"],
        lease["owner_id"],
        lease["knowledge_base_id"],
        lease["document_id"],
        lease["content_version_id"],
        lease["index_version_id"],
        lease["lease_id"],
        str(lease["fencing"]),
        batch["batch_id"],
        str(batch["batch_sequence"]),
        str(len(batch["chunks"])),
    ]
    previous = 0
    for chunk in batch["chunks"]:
        sequence = chunk["sequence_no"]
        if sequence != previous + 1 and previous != 0:
            raise ValueError("chunk sequence numbers in a batch must be contiguous")
        previous = sequence
        if sequence < 1:
            raise ValueError("chunk sequence number must be positive")
        if not _SHA256.fullmatch(chunk["text_sha256"]):
            raise ValueError("invalid text SHA-256")
        text_hash = hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
        if text_hash != chunk["text_sha256"]:
            raise ValueError("text SHA-256 does not match UTF-8 text")
        locator = chunk["locator"]
        values.extend((chunk["chunk_id"], str(sequence), chunk["text_sha256"],
                       locator["kind"]))
        if locator["kind"] == "pdf_page":
            if locator["page"] < 1:
                raise ValueError("PDF page numbers start at 1")
            values.append(str(locator["page"]))
        elif locator["kind"] == "text_range":
            start, end = locator["start"], locator["end"]
            if start < 0 or end <= start or locator["unit"] != "unicode_code_point":
                raise ValueError("invalid Unicode code-point range")
            values.extend((str(start), str(end), locator["unit"]))
        else:
            raise ValueError("unsupported locator kind")
        embedding = chunk["embedding"]
        if len(embedding) != 1024:
            raise ValueError("embedding must contain exactly 1024 values")
        for raw in embedding:
            try:
                value = Decimal(str(raw))
            except InvalidOperation as error:
                raise ValueError("invalid embedding value") from error
            if not value.is_finite():
                raise ValueError("embedding values must be finite")
            try:
                value = value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
            except InvalidOperation as error:
                raise ValueError("invalid embedding precision") from error
            if value.is_zero():
                value = abs(value)
            values.append(format(value, ".6f"))

    output = bytearray(b"knowflow-index-batch-v1\n")
    for value in values:
        output.extend(_field(value))
    return bytes(output)


def batch_sha256(batch: dict) -> str:
    return hashlib.sha256(canonical_batch_bytes(batch)).hexdigest()
