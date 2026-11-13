const errors: Readonly<Record<string, string>> = {
  "LLM_MODEL_URL_INVALID": "服务地址不符合要求，请使用不含账号密码的公网 HTTPS 地址。",
  "LLM_MODEL_AUTH_FAILED": "服务拒绝了密钥或访问权限，请检查 API 密钥及其模型权限。",
  "LLM_MODEL_NOT_FOUND": "模型不存在，请核对模型 ID。",
  "LLM_MODEL_ENDPOINT_NOT_FOUND": "接口路径或模型不可用，请检查 Base URL、接口协议和模型 ID。",
  "LLM_MODEL_UNREACHABLE": "无法连接到服务，请检查公网 HTTPS 地址和网络可达性。",
  "LLM_MODEL_TIMEOUT": "连接测试超时，请稍后重试或检查服务响应速度。",
  "LLM_MODEL_RATE_LIMITED": "模型服务暂时限流，请稍后再试。",
  "LLM_MODEL_PROTOCOL_ERROR": "服务返回与所选协议或模型 ID 不匹配，请检查配置。",
  "INVALID_REQUEST": "请检查模型 ID、密钥和 HTTPS 地址。更改地址或协议时需要重新输入密钥。",
  "LLM_MODEL_PROBE_FAILED": "连接测试失败。请检查地址、密钥、协议和模型 ID。",
  "LLM_MODEL_PROBE_LIMIT": "连接测试过于频繁，请一分钟后再试。",
  "LLM_MODEL_CONFLICT": "模型已存在或已在其他页面修改。请刷新后重试。",
  "LLM_MODELS_DISABLED": "当前部署未启用自定义模型。",
  "RESOURCE_LIMIT": "模型请求繁忙，请稍后重试。"
};

export function modelErrorMessage(code: unknown): string {
  return typeof code === "string" && Object.hasOwn(errors, code)
    ? errors[code] : errors.LLM_MODEL_PROBE_FAILED;
}
