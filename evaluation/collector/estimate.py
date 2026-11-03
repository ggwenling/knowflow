"""Estimate a sequence of provider reservations without making network calls.

Input is a JSON array of objects accepted by BudgetLedger.reserve, each with
its own request_id. Quotes and token bounds must already have been verified.
"""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from budget import BudgetLedger


def estimate(requests):
    if not isinstance(requests, list):
        raise ValueError("INVALID_REQUEST_LIST")
    results = []
    with TemporaryDirectory(prefix="knowflow-estimate-") as temp:
        ledger = BudgetLedger(Path(temp) / "budget.sqlite3")
        for index, request in enumerate(requests):
            if not isinstance(request, dict):
                raise ValueError("INVALID_REQUEST")
            try:
                result = ledger.reserve(**request)
            except (TypeError, ValueError) as error:
                return {"status": "stopped", "stopped_at": index,
                        "reason": str(error) if isinstance(error, ValueError) else "INVALID_REQUEST",
                        "reservations": results, "summary": ledger.summary()}
            results.append(result)
        return {"status": "complete", "reservations": results, "summary": ledger.summary()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requests", type=Path, help="JSON file containing reservation inputs")
    args = parser.parse_args()
    try:
        result = estimate(json.loads(args.requests.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError):
        result = {"status": "stopped", "reason": "INVALID_REQUEST_FILE"}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
