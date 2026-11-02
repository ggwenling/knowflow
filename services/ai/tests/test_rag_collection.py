import importlib.util
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import Barrier

import pytest


ROOT = Path(__file__).resolve().parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "evaluation" / "collector" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


budget = load("budget")
mapping = load("mapping")
NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)
QUOTE = {"provider": "synthetic", "model": "model-a", "input_cny_per_million": "1",
         "output_cny_per_million": "2", "source_url": "https://example.test/prices",
         "verified_by": "test", "verified_at": "2026-11-01T00:00:00Z",
         "valid_until": "2026-11-03T00:00:00Z"}


def reserve(ledger, request_id, *, tokens=1_000_000, quote=None, model="model-a"):
    return ledger.reserve(request_id, provider="synthetic", model=model, input_tokens_upper=tokens,
                          output_tokens_upper=0, quote=quote if quote is not None else QUOTE, now=NOW)


def test_budget_is_durable_and_duplicate_retries_cannot_reuse_reservation(tmp_path):
    path = tmp_path / "budget.sqlite3"
    result = reserve(budget.BudgetLedger(path), "request-1", tokens=9_000_000)
    assert result["remaining_microyuan"] == 1_000_000
    reopened = budget.BudgetLedger(path)
    with pytest.raises(ValueError, match="DUPLICATE_REQUEST_ID"):
        reserve(reopened, "request-1", tokens=1)
    with pytest.raises(ValueError, match="BUDGET_EXCEEDED"):
        reserve(reopened, "retry-2", tokens=1_000_001)
    assert reserve(reopened, "retry-3")["remaining_microyuan"] == 0
    with pytest.raises(ValueError, match="BUDGET_LIMIT_MISMATCH"):
        budget.BudgetLedger(path, limit_microyuan=9_000_000)


def test_budget_reservations_are_serialized_across_independent_connections(tmp_path):
    path = tmp_path / "budget.sqlite3"
    budget.BudgetLedger(path)
    barrier = Barrier(3)

    def run(index):
        ledger = budget.BudgetLedger(path)
        barrier.wait()
        try:
            reserve(ledger, f"attempt-{index}", tokens=4_000_000)
            return "reserved"
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, range(3)))
    assert sorted(results) == ["BUDGET_EXCEEDED", "reserved", "reserved"]


def test_budget_rejects_unknown_expired_or_wrong_model_prices(tmp_path):
    ledger = budget.BudgetLedger(tmp_path / "budget.sqlite3")
    with pytest.raises(ValueError, match="UNVERIFIED_PRICE"):
        reserve(ledger, "unverified", quote={**QUOTE, "verified_by": ""})
    with pytest.raises(ValueError, match="PRICE_EXPIRED_OR_UNVERIFIED"):
        reserve(ledger, "expired", quote={**QUOTE, "valid_until": "2026-11-01T01:00:00Z"})
    with pytest.raises(ValueError, match="PRICE_MODEL_MISMATCH"):
        reserve(ledger, "wrong-model", model="another")
    with pytest.raises(ValueError, match="UNVERIFIED_PRICE"):
        reserve(ledger, "invalid-price", quote={**QUOTE, "input_cny_per_million": "NaN"})
    assert reserve(ledger, "ok", tokens=1)["reserved_microyuan"] == 1


def test_budget_rounds_up_and_reserves_output_upper_bound(tmp_path):
    ledger = budget.BudgetLedger(tmp_path / "budget.sqlite3")
    result = ledger.reserve("mixed", provider="synthetic", model="model-a", input_tokens_upper=3,
                            output_tokens_upper=2, quote={**QUOTE, "input_cny_per_million": "0.1",
                                                         "output_cny_per_million": "0.2"}, now=NOW)
    assert result["reserved_microyuan"] == 1
    precise = ledger.reserve("precise", provider="synthetic", model="model-a", input_tokens_upper=10,
                             output_tokens_upper=0, quote={**QUOTE, "input_cny_per_million": "0.10000000000000000000000000001"}, now=NOW)
    assert precise["reserved_microyuan"] == 2


def test_public_id_matches_java_name_uuid():
    assert mapping.public_source_id("550e8400-e29b-41d4-a716-446655440000", "src-1") == "8e12941d-7836-3c6d-87d0-65e9e8b5267b"


def test_trace_maps_unicode_range_and_rejects_wrong_bytes_and_versions():
    source = "甲证据乙".encode("utf-8")
    key = ("runtime-doc", "runtime-content", "runtime-index")
    entry = {"dataset_document_id": "doc", "dataset_content_version_id": "version",
             "source_bytes": source, "source_sha256": sha256(source).hexdigest()}
    row = {"document_id": key[0], "content_version_id": key[1], "index_version_id": key[2],
           "source_id": "src-1", "locator": {"kind": "text_range", "unit": "unicode_code_point", "start": 1, "end": 3},
           "text_sha256": sha256("证据".encode("utf-8")).hexdigest()}
    question = "550e8400-e29b-41d4-a716-446655440000"
    result = mapping.map_retrieval(question, [row], {key: entry})
    assert result == [{"document_id": "doc", "content_version_id": "version", "start": 1, "end": 3,
                       "text_sha256": row["text_sha256"], "source_id": "8e12941d-7836-3c6d-87d0-65e9e8b5267b"}]
    with pytest.raises(ValueError, match="SOURCE_HASH_MISMATCH"):
        mapping.map_retrieval(question, [row], {key: {**entry, "source_bytes": b"tampered"}})
    with pytest.raises(ValueError, match="INVALID_TRACE_MAPPING"):
        mapping.map_retrieval(question, [{**row, "index_version_id": "old-index"}], {key: entry})
    with pytest.raises(ValueError, match="DUPLICATE_SOURCE_ID"):
        mapping.map_retrieval(question, [row, row], {key: entry})
