"""Draft.5 digests shared with the Java write and publication gateways."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from hashlib import sha256


def _field(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return str(len(encoded)).encode("ascii") + b":" + encoded + b"\n"


def _canonical(values: list[str], header: bytes) -> bytes:
    return header + b"".join(_field(value) for value in values)


def batch_sha256(batch: dict) -> str:
    lease = batch["lease"]
    values = [lease[name] for name in (
        "task_id", "owner_id", "knowledge_base_id", "document_id",
        "content_version_id", "index_version_id", "lease_id")]
    values.extend((str(lease["fencing"]), batch["batch_id"],
                   str(batch["batch_sequence"]), str(len(batch["chunks"]))))
    previous = 0
    for chunk in batch["chunks"]:
        sequence = chunk["sequence_no"]
        if type(sequence) is not int or sequence < 1 or (previous and sequence != previous + 1):
            raise ValueError("INVALID_CHUNK_SEQUENCE")
        previous = sequence
        text = chunk["text"]
        text_hash = sha256(text.encode("utf-8", errors="strict")).hexdigest()
        if text_hash != chunk["text_sha256"]:
            raise ValueError("TEXT_HASH_MISMATCH")
        locator = chunk["locator"]
        values.extend((chunk["chunk_id"], str(sequence), text_hash, locator["kind"]))
        if locator["kind"] == "pdf_page" and type(locator.get("page")) is int and locator["page"] > 0:
            values.append(str(locator["page"]))
        elif (locator["kind"] == "text_range" and type(locator.get("start")) is int
              and type(locator.get("end")) is int and locator["start"] >= 0
              and locator["end"] > locator["start"]
              and locator.get("unit") == "unicode_code_point"):
            values.extend((str(locator["start"]), str(locator["end"]), locator["unit"]))
        else:
            raise ValueError("INVALID_LOCATOR")
        vector = chunk["embedding"]
        if len(vector) != 1024:
            raise ValueError("INVALID_EMBEDDING_DIMENSION")
        for raw in vector:
            try:
                value = Decimal(str(raw))
                if not value.is_finite():
                    raise InvalidOperation
                value = value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
            except (InvalidOperation, ValueError):
                raise ValueError("INVALID_EMBEDDING_VALUE") from None
            values.append(format(abs(value) if value.is_zero() else value, ".6f"))
    return sha256(_canonical(values, b"knowflow-index-batch-v1\n")).hexdigest()


def manifest_sha256(lease: dict, model_profile: str, batches: list[dict], chunk_count: int) -> str:
    values = [lease[name] for name in (
        "task_id", "owner_id", "knowledge_base_id", "document_id",
        "content_version_id", "index_version_id", "pipeline_profile_id")]
    values.extend((model_profile, "1024", str(chunk_count), str(chunk_count), str(len(batches))))
    for batch in batches:
        values.extend((str(batch["batch_sequence"]), batch["batch_id"],
                       batch["batch_sha256"], str(len(batch["chunks"]))))
    return sha256(_canonical(values, b"knowflow-index-manifest-v1\n")).hexdigest()
