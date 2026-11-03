"""Environment-configured launcher for the real evaluation AI service.

The provider adapters retain their normal per-request budget reservation. This
module only validates their environment-backed configuration and wires them
into the evaluation-only application.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit


_VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)
_REQUIRED_ENVIRONMENT = (
    "KNOWFLOW_BUDGET_LEDGER_PATH",
    "KNOWFLOW_BUDGET_PRICE_FILE",
    "KNOWFLOW_BUDGET_POLICY_FILE",
    "KNOWFLOW_INTERNAL_SHARED_SECRET",
    "KNOWFLOW_EVALUATION_CONTROL_SECRET",
    "KNOWFLOW_AI_DATABASE_URL",
    "KNOWFLOW_EMBEDDING_KEY_ENV",
    "KNOWFLOW_EMBEDDING_BASE_URL",
    "KNOWFLOW_EMBEDDING_MODEL",
    "KNOWFLOW_EMBEDDING_DIMENSIONS",
    "KNOWFLOW_LLM_KEY_ENV",
    "KNOWFLOW_LLM_BASE_URL",
    "KNOWFLOW_LLM_MODEL",
)
_PRICE_FIELDS = {
    "provider", "model", "input_cny_per_million", "output_cny_per_million",
    "source_url", "verified_by", "verified_at", "valid_until",
}
_POLICY_FIELDS = {
    "provider", "bound_kind", "source_url", "verified_by", "verified_at",
    "valid_until", "input_tokens_upper", "output_tokens_upper", "max_payload_bytes",
}


def _not_ready(*keys):
    names = tuple(dict.fromkeys(name for name in keys if name))
    raise RuntimeError("EVALUATION_SERVICE_NOT_READY: " + ", ".join(names)) from None


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _read_json_file(environment, variable):
    try:
        content = Path(environment[variable]).read_text(encoding="utf-8")
        value = json.loads(content, object_pairs_hook=_unique_object)
    except (KeyError, OSError, UnicodeError, TypeError, ValueError):
        _not_ready(variable)
    if not isinstance(value, dict):
        _not_ready(variable)
    return value


def _instant(value):
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError
        return instant.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        raise ValueError from None


def _validate_policy(policy, *, provider, model, variable):
    if not isinstance(policy, dict) or set(policy) != _POLICY_FIELDS:
        _not_ready(variable)
    if (policy.get("provider") != provider or policy.get("bound_kind") != "provider_context_limit"
            or not isinstance(policy.get("verified_by"), str)
            or not policy["verified_by"].strip()):
        _not_ready(variable)
    try:
        source = urlsplit(policy["source_url"])
        now = datetime.now(timezone.utc)
        verified_at = _instant(policy["verified_at"])
        valid_until = _instant(policy["valid_until"])
        if (source.scheme != "https" or not source.hostname or source.username or source.password
                or source.query or source.fragment or not verified_at <= now <= valid_until):
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        _not_ready(variable)
    input_bound = policy["input_tokens_upper"]
    output_bound = policy["output_tokens_upper"]
    payload_bound = policy["max_payload_bytes"]
    if (type(input_bound) is not int or not 0 < input_bound <= 1_000_000_000
            or type(output_bound) is not int or not 0 <= output_bound <= 1_000_000_000
            or type(payload_bound) is not int or payload_bound <= 0
            or (provider == "deepseek" and output_bound < 1024)):
        _not_ready(variable)

    policy_id = hashlib.sha256(json.dumps(
        policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()

    def token_bounds(operation, *_inputs):
        if operation == "embed":
            return input_bound, 0
        if operation in ("generate", "stream"):
            return input_bound, output_bound
        return None

    token_bounds.policy_id = policy_id
    bound_evidence = {
        "provider": provider,
        "model": model,
        "policy_id": policy_id,
        "source_url": policy["source_url"],
        "verified_by": policy["verified_by"],
        "verified_at": policy["verified_at"],
        "valid_until": policy["valid_until"],
    }
    return token_bounds, bound_evidence


def _load_wiring():
    if __package__:
        from . import wiring
        return wiring
    spec = importlib.util.spec_from_file_location(
        "knowflow_evaluation_wiring", Path(__file__).with_name("wiring.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _adapter_configuration(environment, *, selector_name, base_url_name,
                           model_name, dimensions_name=None):
    selector = environment.get(selector_name, "").strip()
    if not _VARIABLE_NAME.fullmatch(selector):
        _not_ready(selector_name)
    if not environment.get(selector, "").strip():
        _not_ready(selector)
    required = [selector_name, selector, base_url_name, model_name]
    if dimensions_name:
        required.append(dimensions_name)
    return required


def create_real_app():
    """Build the real evaluation app; all configuration comes from environment variables."""
    environment = os.environ
    missing = [name for name in _REQUIRED_ENVIRONMENT
               if not environment.get(name, "").strip()]
    for selector_name in ("KNOWFLOW_EMBEDDING_KEY_ENV", "KNOWFLOW_LLM_KEY_ENV"):
        selector = environment.get(selector_name, "").strip()
        if selector and not _VARIABLE_NAME.fullmatch(selector):
            missing.append(selector_name)
        elif selector and not environment.get(selector, "").strip():
            missing.append(selector)
    if len(environment.get("KNOWFLOW_EVALUATION_CONTROL_SECRET", "")) < 32:
        missing.append("KNOWFLOW_EVALUATION_CONTROL_SECRET")
    if missing:
        _not_ready(*missing)

    try:
        port = int(environment.get("KNOWFLOW_EVALUATION_AI_PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        _not_ready("KNOWFLOW_EVALUATION_AI_PORT")

    try:
        from knowflow_ai.answering import DeepSeekAdapter, LlmSettings
        from knowflow_ai.config import Settings
        from knowflow_ai.embedding import EmbeddingSettings, SiliconFlowEmbeddingAdapter
        service_settings = Settings.from_environment()
    except Exception:
        _not_ready("KNOWFLOW_INTERNAL_SHARED_SECRET", "KNOWFLOW_AI_DATABASE_URL",
                   "KNOWFLOW_JAVA_BASE_URL", "KNOWFLOW_CONTRACT_PATH",
                   "KNOWFLOW_QUESTION_MAX_CONCURRENT")

    embedding_environment = _adapter_configuration(
        environment, selector_name="KNOWFLOW_EMBEDDING_KEY_ENV",
        base_url_name="KNOWFLOW_EMBEDDING_BASE_URL", model_name="KNOWFLOW_EMBEDDING_MODEL",
        dimensions_name="KNOWFLOW_EMBEDDING_DIMENSIONS")
    try:
        embedding_settings = EmbeddingSettings.from_environment()
    except Exception:
        _not_ready(*embedding_environment)
    llm_environment = _adapter_configuration(
        environment, selector_name="KNOWFLOW_LLM_KEY_ENV",
        base_url_name="KNOWFLOW_LLM_BASE_URL", model_name="KNOWFLOW_LLM_MODEL")
    try:
        llm_settings = LlmSettings.from_environment()
    except Exception:
        _not_ready(*llm_environment)

    embedding_model = embedding_settings.model
    llm_model = llm_settings.model
    prices = _read_json_file(environment, "KNOWFLOW_BUDGET_PRICE_FILE")
    policies = _read_json_file(environment, "KNOWFLOW_BUDGET_POLICY_FILE")
    if embedding_model not in prices:
        _not_ready("KNOWFLOW_BUDGET_PRICE_FILE", "embedding.model")
    if llm_model not in prices:
        _not_ready("KNOWFLOW_BUDGET_PRICE_FILE", "llm.model")
    if embedding_model not in policies:
        _not_ready("KNOWFLOW_BUDGET_POLICY_FILE", "embedding.model")
    if llm_model not in policies:
        _not_ready("KNOWFLOW_BUDGET_POLICY_FILE", "llm.model")

    embedding_quote = prices[embedding_model]
    llm_quote = prices[llm_model]
    for quote, provider, model in ((embedding_quote, "siliconflow", embedding_model),
                                   (llm_quote, "deepseek", llm_model)):
        if (not isinstance(quote, dict) or set(quote) != _PRICE_FIELDS
                or quote.get("provider") != provider or quote.get("model") != model):
            _not_ready("KNOWFLOW_BUDGET_PRICE_FILE", "quote")

    embedding_bounds, embedding_evidence = _validate_policy(
        policies[embedding_model], provider="siliconflow", model=embedding_model,
        variable="KNOWFLOW_BUDGET_POLICY_FILE")
    llm_bounds, llm_evidence = _validate_policy(
        policies[llm_model], provider="deepseek", model=llm_model,
        variable="KNOWFLOW_BUDGET_POLICY_FILE")

    try:
        wiring = _load_wiring()
        from knowflow_ai.budget import SOFT_STOP_MICROYUAN
        ledger = wiring.BudgetLedger(environment["KNOWFLOW_BUDGET_LEDGER_PATH"])
    except Exception:
        _not_ready("KNOWFLOW_BUDGET_LEDGER_PATH")
    try:
        snapshot = ledger.summary()
    except Exception:
        _not_ready("KNOWFLOW_BUDGET_LEDGER_PATH")
    if (not isinstance(snapshot, dict)
            or type(snapshot.get("reserved_microyuan")) is not int
            or snapshot["reserved_microyuan"] < 0
            or snapshot["reserved_microyuan"] >= SOFT_STOP_MICROYUAN):
        _not_ready("KNOWFLOW_BUDGET_LEDGER_PATH")
    try:
        app = wiring.create_evaluation_app(
            service_settings,
            ledger=ledger,
            embedding={
                "adapter_factory": lambda: SiliconFlowEmbeddingAdapter(embedding_settings),
                "provider": "siliconflow",
                "model": embedding_model,
                "quote": embedding_quote,
                "token_bounds": embedding_bounds,
                "bound_evidence": embedding_evidence,
            },
            llm={
                "adapter_factory": lambda: DeepSeekAdapter(llm_settings),
                "provider": "deepseek",
                "model": llm_model,
                "quote": llm_quote,
                "token_bounds": llm_bounds,
                "bound_evidence": llm_evidence,
            },
            control_secret=environment["KNOWFLOW_EVALUATION_CONTROL_SECRET"],
        )
    except Exception:
        _not_ready("KNOWFLOW_BUDGET_LEDGER_PATH", "KNOWFLOW_BUDGET_PRICE_FILE",
                   "KNOWFLOW_BUDGET_POLICY_FILE", "KNOWFLOW_AI_DATABASE_URL",
                   "KNOWFLOW_INTERNAL_SHARED_SECRET", "KNOWFLOW_EVALUATION_CONTROL_SECRET")
    app.state.evaluation_ai_port = port
    return app


def main():
    app = create_real_app()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=app.state.evaluation_ai_port,
                log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
