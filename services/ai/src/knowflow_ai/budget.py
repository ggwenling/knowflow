"""Durable, conservative reservation ledger for evaluation provider calls.

This ledger must be invoked by every provider adapter before each request. It is
not a provider wrapper and does not enforce a budget on calls that bypass it.
"""
from datetime import datetime, timezone
from contextlib import closing
from decimal import Decimal, InvalidOperation, ROUND_CEILING, localcontext
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse


MAX_MICROYUAN = 10_000_000  # CNY 10
SOFT_STOP_MICROYUAN = 8_000_000  # CNY 8
ZERO_PRICE_EMBEDDING_PROVIDER = "siliconflow"
ZERO_PRICE_EMBEDDING_MODEL = "BAAI/bge-m3"
ZERO_PRICE_EMBEDDING_SOURCE = "siliconflow.cn"


def _instant(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (AttributeError, ValueError):
        raise ValueError("INVALID_PRICE_TIME") from None


def _price(value, *, zero_allowed=False):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("UNVERIFIED_PRICE")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise ValueError("UNVERIFIED_PRICE") from None
    if (not amount.is_finite() or amount > 1_000_000 or amount < 0
            or (not zero_allowed and amount == 0) or (amount and amount < Decimal("0.000000000001"))):
        raise ValueError("UNVERIFIED_PRICE")
    return amount


class BudgetLedger:
    def __init__(self, path, *, limit_microyuan=MAX_MICROYUAN):
        if type(limit_microyuan) is not int or not 0 < limit_microyuan <= MAX_MICROYUAN:
            raise ValueError("INVALID_BUDGET")
        self.path = Path(path)
        self.limit = limit_microyuan
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY CHECK(id = 1), limit_microyuan INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS reservations (request_id TEXT PRIMARY KEY, microyuan INTEGER NOT NULL CHECK(microyuan > 0), input_tokens_upper INTEGER NOT NULL, output_tokens_upper INTEGER NOT NULL, price_quote TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS zero_price_reservations (request_id TEXT PRIMARY KEY, input_tokens_upper INTEGER NOT NULL, output_tokens_upper INTEGER NOT NULL CHECK(output_tokens_upper = 0), price_quote TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO budget VALUES (1, ?)", (limit_microyuan,))
            if db.execute("SELECT limit_microyuan FROM budget WHERE id = 1").fetchone()[0] != limit_microyuan:
                raise ValueError("BUDGET_LIMIT_MISMATCH")

    def reserve(self, request_id, *, provider, model, input_tokens_upper, output_tokens_upper,
                quote, now=None, allow_zero_price_embedding=False):
        """Reserve worst-case CNY using explicitly verified CNY per million tokens.

        ``input_tokens_upper`` and ``output_tokens_upper`` must be conservative
        provider-specific upper bounds. Every retry needs a new request ID.
        Reservations are never refunded, including after errors or timeouts.
        """
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id):
            raise ValueError("INVALID_REQUEST_ID")
        if (type(input_tokens_upper) is not int or not 0 < input_tokens_upper <= 1_000_000_000
                or type(output_tokens_upper) is not int or not 0 <= output_tokens_upper <= 1_000_000_000):
            raise ValueError("INVALID_TOKEN_BOUND")
        if not isinstance(quote, dict) or set(quote) != {
            "provider", "model", "input_cny_per_million", "output_cny_per_million",
            "source_url", "verified_by", "verified_at", "valid_until",
        }:
            raise ValueError("UNVERIFIED_PRICE")
        if any(not isinstance(quote[k], str) or not quote[k].strip() for k in ("provider", "model", "verified_by")):
            raise ValueError("UNVERIFIED_PRICE")
        if provider != quote["provider"] or model != quote["model"]:
            raise ValueError("PRICE_MODEL_MISMATCH")
        parsed = urlparse(quote["source_url"]) if isinstance(quote["source_url"], str) else None
        if not parsed or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("UNVERIFIED_PRICE")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("INVALID_PRICE_TIME")
        if not _instant(quote["verified_at"]) <= current.astimezone(timezone.utc) <= _instant(quote["valid_until"]):
            raise ValueError("PRICE_EXPIRED_OR_UNVERIFIED")
        if type(allow_zero_price_embedding) is not bool:
            raise ValueError("UNVERIFIED_PRICE")
        if allow_zero_price_embedding and (output_tokens_upper != 0
                                           or provider != ZERO_PRICE_EMBEDDING_PROVIDER
                                           or model != ZERO_PRICE_EMBEDDING_MODEL
                                           or parsed.hostname not in (
                                               ZERO_PRICE_EMBEDDING_SOURCE,
                                               "www." + ZERO_PRICE_EMBEDDING_SOURCE,
                                               "cloud-rd." + ZERO_PRICE_EMBEDDING_SOURCE)):
            raise ValueError("UNVERIFIED_PRICE")
        input_price = _price(quote["input_cny_per_million"], zero_allowed=allow_zero_price_embedding)
        output_price = _price(quote["output_cny_per_million"], zero_allowed=output_tokens_upper == 0)
        try:
            with localcontext() as context:
                context.prec = 96
                amount = int((input_price * input_tokens_upper + output_price * output_tokens_upper).to_integral_value(rounding=ROUND_CEILING))
        except (InvalidOperation, OverflowError):
            raise ValueError("INVALID_PRICE") from None
        zero_price = amount == 0
        if zero_price and not allow_zero_price_embedding:
            raise ValueError("UNVERIFIED_PRICE")
        if amount > self.limit:
            raise ValueError("BUDGET_EXCEEDED")
        with closing(sqlite3.connect(self.path, timeout=30, isolation_level=None)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            spent = db.execute("SELECT COALESCE(SUM(microyuan), 0) FROM reservations").fetchone()[0]
            if (db.execute("SELECT 1 FROM reservations WHERE request_id = ?", (request_id,)).fetchone()
                    or db.execute("SELECT 1 FROM zero_price_reservations WHERE request_id = ?", (request_id,)).fetchone()):
                raise ValueError("DUPLICATE_REQUEST_ID")
            if spent >= SOFT_STOP_MICROYUAN:
                raise ValueError("BUDGET_SOFT_STOP")
            if spent + amount > self.limit:
                raise ValueError("BUDGET_EXCEEDED")
            if zero_price:
                db.execute("INSERT INTO zero_price_reservations VALUES (?, ?, ?, ?)",
                           (request_id, input_tokens_upper, output_tokens_upper,
                            json.dumps(quote, sort_keys=True, separators=(",", ":"))))
            else:
                db.execute("INSERT INTO reservations VALUES (?, ?, ?, ?, ?)",
                           (request_id, amount, input_tokens_upper, output_tokens_upper,
                            json.dumps(quote, sort_keys=True, separators=(",", ":"))))
            db.commit()
        return {"reserved_microyuan": amount, "total_reserved_microyuan": spent + amount,
                "remaining_microyuan": self.limit - spent - amount}

    def summary(self):
        """Read a consistent reservation snapshot without holding the connection open."""
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.execute("BEGIN")
            limit = db.execute("SELECT limit_microyuan FROM budget WHERE id = 1").fetchone()[0]
            spent, paid_count = db.execute(
                "SELECT COALESCE(SUM(microyuan), 0), COUNT(*) FROM reservations").fetchone()
            zero_count = db.execute("SELECT COUNT(*) FROM zero_price_reservations").fetchone()[0]
        return {"limit_microyuan": limit, "reserved_microyuan": spent,
                "remaining_microyuan": limit - spent, "paid_reservations": paid_count,
                "zero_price_reservations": zero_count}
