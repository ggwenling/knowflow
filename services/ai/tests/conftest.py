"""Test-session environment isolation.

The suite must not depend on how the host machine configures egress proxies.
httpx parses every ``NO_PROXY`` entry as a URL pattern, so a bracketed literal
such as ``[::1]`` is read as host ``[`` with port ``:1]`` and aborts client
construction inside test helpers. Such entries are dropped here; everything else
is kept verbatim. Adapter clients handle any other malformed form by degrading
(see ``knowflow_ai.http_client``).
"""
import os
import json
from datetime import datetime, timedelta, timezone

import pytest


def _acceptable(entry: str) -> bool:
    return "[" not in entry and "]" not in entry


def _normalized_no_proxy(raw: str) -> str:
    return ",".join(entry.strip() for entry in raw.split(",")
                    if entry.strip() and _acceptable(entry.strip()))


def pytest_configure(config):
    for name in ("NO_PROXY", "no_proxy"):
        raw = os.environ.get(name)
        if raw:
            os.environ[name] = _normalized_no_proxy(raw)


@pytest.fixture(autouse=True)
def synthetic_provider_budget(tmp_path_factory, monkeypatch):
    """Give existing mock-transport tests an explicit, isolated fake budget policy."""
    monkeypatch.delenv("KNOWFLOW_BUDGET_RUN_ID", raising=False)
    monkeypatch.delenv("KNOWFLOW_BUDGET_RUN_LIMIT_MICROYUAN", raising=False)
    tmp_path = tmp_path_factory.mktemp("synthetic-provider-budget")
    now = datetime.now(timezone.utc)
    times = {"verified_at": (now - timedelta(hours=1)).isoformat(),
             "valid_until": (now + timedelta(hours=1)).isoformat()}
    prices, policies = {}, {}
    for provider, model, source in (
            ("deepseek", "deepseek-flash", "https://example.test/prices"),
            ("siliconflow", "BAAI/bge-m3", "https://siliconflow.cn/pricing")):
        prices[model] = {"provider": provider, "model": model, "input_cny_per_million": "1",
                         "output_cny_per_million": "2", "source_url": source,
                         "verified_by": "fake-provider-test", **times}
        policies[model] = {"provider": provider, "bound_kind": "provider_context_limit",
                           "source_url": source, "verified_by": "fake-provider-test", **times,
                           "input_tokens_upper": 100_000, "output_tokens_upper": 1024,
                           "max_payload_bytes": 1_000_000}
    for suffix, content in (("PRICE_FILE", prices), ("POLICY_FILE", policies)):
        path = tmp_path / (suffix + ".json")
        path.write_text(json.dumps(content), encoding="utf-8")
        monkeypatch.setenv("KNOWFLOW_BUDGET_" + suffix, str(path))
    monkeypatch.setenv("KNOWFLOW_BUDGET_LEDGER_PATH", str(tmp_path / "provider-budget.sqlite3"))
