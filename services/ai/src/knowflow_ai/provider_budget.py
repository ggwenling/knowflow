"""Mandatory reservation boundary for every product provider request."""
import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from .adapters import ProcessingError
from .budget import BudgetLedger, _instant


def _reserve_provider_call(provider, model, payload, environ):
    try:
        env = os.environ if environ is None else environ
        ledger_path = env["KNOWFLOW_BUDGET_LEDGER_PATH"]
        prices = json.loads(Path(env["KNOWFLOW_BUDGET_PRICE_FILE"]).read_text(encoding="utf-8"))
        policies = json.loads(Path(env["KNOWFLOW_BUDGET_POLICY_FILE"]).read_text(encoding="utf-8"))
        policy = policies[model]
        quote = prices[model]
        source = urlsplit(policy["source_url"])
        now = datetime.now(timezone.utc)
        if (policy["provider"] != provider
                or not isinstance(policy["verified_by"], str) or not policy["verified_by"].strip()
                or policy["verified_by"].strip().lower() in {
                    "draft", "unsigned", "unverified", "draft-not-owner-signed", "not-owner-signed"}
                or source.scheme != "https" or not source.hostname or source.username or source.password
                or source.query or source.fragment
                or not _instant(policy["verified_at"]) <= now <= _instant(policy["valid_until"])
                or policy["bound_kind"] != "provider_context_limit"
                or type(policy["max_payload_bytes"]) is not int
                or len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > policy["max_payload_bytes"]):
            raise ValueError("INVALID_POLICY")
        output = payload.get("max_tokens", 0)
        if type(output) is not int or not 0 <= output <= policy["output_tokens_upper"]:
            raise ValueError("INVALID_OUTPUT_BOUND")
        ledger = BudgetLedger(ledger_path)
        ledger.reserve("provider:" + uuid4().hex, provider=provider, model=model,
            input_tokens_upper=policy["input_tokens_upper"], output_tokens_upper=output,
            quote=quote, allow_zero_price_embedding=(
                provider == "siliconflow" and isinstance(quote, dict)
                and quote.get("input_cny_per_million") == "0"))
    except (KeyError, TypeError, ValueError, OSError, sqlite3.Error) as error:
        reason = str(error) if isinstance(error, ValueError) else "BUDGET_CONFIGURATION_REQUIRED"
        if reason not in ("BUDGET_SOFT_STOP", "BUDGET_EXCEEDED"):
            reason = "BUDGET_CONFIGURATION_REQUIRED"
        logging.getLogger(__name__).warning("provider_budget_stopped reason=%s", reason)
        raise ProcessingError("AI_PROCESSING_FAILED", 503, retryable=False) from None


async def reserve_provider_call(provider, model, payload, *, environ=None):
    """Reserve a verified model-context upper bound for each individual attempt."""
    await asyncio.to_thread(_reserve_provider_call, provider, model, payload, environ)


def reserve_provider_call_sync(provider, model, payload, *, environ=None):
    """Synchronous counterpart for the standard-library live smoke client."""
    _reserve_provider_call(provider, model, payload, environ)
