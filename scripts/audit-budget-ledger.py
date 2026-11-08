"""Read-only audit of local budget ledgers.

The ledger records reservations/upper bounds, not supplier invoices. This
script reports what the local evidence proves and what it does not prove.
"""

from __future__ import annotations

import glob
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval-out" / "budget-audit-20261108"
SOFT_LIMIT = int(os.environ.get("KNOWFLOW_SOFT_LIMIT_MICROYUAN", "2000000"))
HARD_LIMIT = int(os.environ.get("KNOWFLOW_HARD_LIMIT_MICROYUAN", "10000000"))


def audit(path: Path) -> dict:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in connection.execute("select name from sqlite_master where type = 'table'")}
        limit_row = (
            connection.execute("select limit_microyuan from budget where id = 1").fetchone()
            if "budget" in tables
            else None
        )
        limit = int(limit_row[0]) if limit_row else None
        reservations = (
            list(connection.execute("select microyuan, price_quote from reservations"))
            if "reservations" in tables
            else []
        )
        zero_price = (
            connection.execute("select count(*) from zero_price_reservations").fetchone()[0]
            if "zero_price_reservations" in tables
            else 0
        )
        stops = (
            list(connection.execute("select request_id, reason, reserved_microyuan, created_at from budget_stops"))
            if "budget_stops" in tables
            else []
        )
    finally:
        connection.close()

    paid = sum(int(row[0]) for row in reservations)
    verified_by = set()
    providers = set()
    for row in reservations:
        try:
            quote = json.loads(row[1])
        except (TypeError, ValueError):
            continue
        if quote.get("verified_by"):
            verified_by.add(str(quote["verified_by"]))
        if quote.get("provider"):
            providers.add(str(quote["provider"]))

    return {
        "ledger": str(path.relative_to(ROOT)),
        "limit_microyuan": limit,
        "reservations": len(reservations),
        "reserved_microyuan": paid,
        "reserved_cny": round(paid / 1_000_000, 6),
        "zero_price_reservations": zero_price,
        "soft_limit_microyuan": SOFT_LIMIT,
        "hard_limit_microyuan": HARD_LIMIT,
        "over_soft_microyuan": max(0, paid - SOFT_LIMIT),
        "over_hard_microyuan": max(0, paid - HARD_LIMIT),
        "providers": sorted(providers),
        "verified_by": sorted(verified_by),
        "budget_stops": stops,
        "hard_cap_proven_from_supplier": False,
        "supplier_invoice_reconciled": False,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ledgers = [Path(p) for p in sorted(glob.glob(str(ROOT / "eval-out" / "*" / "budget-ledger.sqlite3")))]
    if not ledgers:
        print("no budget ledgers found", flush=True)
        return 2
    reports = [audit(path) for path in ledgers]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "soft_limit_microyuan": SOFT_LIMIT,
        "hard_limit_microyuan": HARD_LIMIT,
        "ledgers": reports,
        "notes": [
            "reserved_microyuan is a local upper-bound reservation, not an invoice.",
            "hard_cap_proven_from_supplier=false: no supplier-side hard cap evidence in the repository.",
            "supplier_invoice_reconciled=false: no supplier bill export/reconciliation evidence in the repository.",
            "Any verified_by containing 'pending' still needs a human owner signature.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 预算账本审计（只读）",
        "",
        f"生成时间：{summary['generated_at']}",
        "",
        f"软目标：{SOFT_LIMIT / 1_000_000:.2f} CNY；硬上限：{HARD_LIMIT / 1_000_000:.2f} CNY。",
        "",
        "| 账本 | 预留 (CNY) | 超出软目标 | 超出硬上限 | 笔数 | 零价笔数 | verified_by |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in reports:
        lines.append(
            f"| `{item['ledger']}` | {item['reserved_cny']:.5f} | {item['over_soft_microyuan'] / 1_000_000:.5f} | "
            f"{item['over_hard_microyuan'] / 1_000_000:.5f} | {item['reservations']} | {item['zero_price_reservations']} | "
            f"{'; '.join(item['verified_by']) or '—'} |"
        )
    lines += [
        "",
        "## 这组证据不能证明什么",
        "",
        "- 不能证明供应商侧存在硬支出上限或超额拒绝；本地账本只是应用侧预留。",
        "- 不能替代供应商账单、发票、汇率/税费与对账。",
        "- `verified_by` 仍含 `pending` 的条目未获得负责人签核。",
    ]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT / 'summary.json'}")
    print(f"wrote {OUT / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
