"""Save-time capability checks and safe diagnostics; unrelated to readiness."""
from datetime import datetime, timezone
import json
import re

from .adapters import ProcessingError

MESSAGES = {
    'LLM_MODEL_URL_INVALID': '服务地址不符合要求，请使用不含账号密码的公网 HTTPS 地址。',
    'LLM_MODEL_AUTH_FAILED': '服务拒绝了密钥或访问权限，请检查 API 密钥及其模型权限。',
    'LLM_MODEL_NOT_FOUND': '模型不存在，请核对模型 ID。',
    'LLM_MODEL_ENDPOINT_NOT_FOUND': '接口路径或模型不可用，请检查 Base URL、接口协议和模型 ID。',
    'LLM_MODEL_UNREACHABLE': '无法连接到服务，请检查公网 HTTPS 地址和网络可达性。',
    'LLM_MODEL_TIMEOUT': '连接测试超时，请稍后重试或检查服务响应速度。',
    'LLM_MODEL_RATE_LIMITED': '模型服务暂时限流，请稍后再试。',
    'LLM_MODEL_PROTOCOL_ERROR': '服务返回与所选协议或模型 ID 不匹配，请检查配置。',
    'LLM_MODEL_PROBE_FAILED': '连接测试失败。请检查地址、密钥、协议和模型 ID。',
}
# Only matching constants survive the HTTP boundary. Never retain message text.
_FIELDS = {
    'code': frozenset(('model_not_found', 'invalid_model', 'unsupported_parameter', 'unsupported_value',
                       'not_implemented', 'unsupported_capability')),
    'type': frozenset(('model_not_found', 'invalid_model', 'invalid_request_error', 'not_implemented',
                       'unsupported_capability')),
    'param': frozenset(('model', 'tools', 'tool_choice')),
}


def machine_evidence(body, *, status=None, host=None, model_id=None):
    try:
        error = json.loads(body).get('error')
        if isinstance(error, dict):
            # DeepSeek uses a generic code for unknown models. Require its exact
            # diagnostic shape, including the requested model, on its own endpoint.
            message = error.get('message')
            if (host == 'api.deepseek.com' and status == 400 and model_id
                    and error.get('code') == error.get('type') == 'invalid_request_error'
                    and error.get('param') is None and isinstance(message, str)
                    and re.fullmatch(r'The supported API model names are [\w., /:-]+, but you passed '
                                     + re.escape(model_id)
                                     + r'\.(?: \(request_id: [0-9a-fA-F-]{36}\))?', message)):
                return frozenset({('code', 'model_not_found')})
            return frozenset((field, value) for field, allowed in _FIELDS.items()
                             if isinstance(value := error.get(field), str) and value in allowed)
    except (ValueError, AttributeError, UnicodeError):
        pass
    return frozenset()


def model_missing(evidence):
    return (any((field, value) in evidence for field in ('code', 'type')
                for value in ('model_not_found', 'invalid_model'))
            or ('param', 'model') in evidence)


def tools_rejected(error):
    evidence = getattr(error, 'provider_evidence', frozenset())
    if error.provider_status not in (400, 422, 501) or model_missing(evidence):
        return False
    points_to_tools = any(('param', param) in evidence for param in ('tools', 'tool_choice'))
    # 501 is capability evidence only when explicitly named as such, and scoped
    # to tools. A generic not-implemented endpoint must never trigger fallback.
    if error.provider_status == 501:
        return points_to_tools and any((field, value) in evidence for field in ('code', 'type')
                                      for value in ('not_implemented', 'unsupported_capability'))
    return points_to_tools


class ModelProbeError(Exception):
    def __init__(self, code):
        self.code = code if code in MESSAGES else 'LLM_MODEL_PROBE_FAILED'
        self.status = 400 if self.code == 'LLM_MODEL_URL_INVALID' else 422
        super().__init__(self.code)


def classify_probe_error(error):
    code = 'LLM_MODEL_PROBE_FAILED'
    if isinstance(error, TimeoutError):
        code = 'LLM_MODEL_TIMEOUT'
    elif isinstance(error, ProcessingError):
        status, reason = error.provider_status, error.retry_reason
        if status in (401, 403):
            code = 'LLM_MODEL_AUTH_FAILED'
        elif status == 429:
            code = 'LLM_MODEL_RATE_LIMITED'
        elif status in (400, 404, 405, 422) and model_missing(getattr(error, 'provider_evidence', ())):
            code = 'LLM_MODEL_NOT_FOUND'
        elif status in (404, 405):
            code = 'LLM_MODEL_ENDPOINT_NOT_FOUND'
        elif error.code == 'PROCESSING_TIMEOUT':
            code = 'LLM_MODEL_TIMEOUT'
        elif error.code == 'INVALID_REQUEST' or reason == 'invalid_url':
            code = 'LLM_MODEL_URL_INVALID'
        elif reason in ('connect_failure', 'connection_reset', 'redirect', 'proxy_unavailable'):
            code = 'LLM_MODEL_UNREACHABLE'
        elif status is None and reason in (None, 'completion_validation', 'model_mismatch', 'sdk_parse',
                                          'parse', 'garbage', 'encoding', 'content_filter', 'refusal',
                                          'length_truncation', 'response_too_large'):
            code = 'LLM_MODEL_PROTOCOL_ERROR'
    return ModelProbeError(code)


def utc_now():
    return datetime.now(timezone.utc)


async def run_model_probe(factory, *, runner, deadline, clock=utc_now):
    model = None
    try:
        try:
            model = factory()
            supports_tools = await runner.run(model.probe_capabilities, deadline=deadline, timeout_kind='total_timeout')
            if type(supports_tools) is not bool:
                raise ModelProbeError('LLM_MODEL_PROBE_FAILED')
            return {'supports_tools': supports_tools, 'status': 'success',
                    'checked_at': clock().astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')}
        finally:
            if model is not None:
                await model.aclose()
    except ModelProbeError:
        raise
    except Exception as error:
        # Admission/breaker remain the existing trusted busy contract.
        if isinstance(error, ProcessingError) and error.code == 'RESOURCE_LIMIT':
            raise
        raise classify_probe_error(error) from None
