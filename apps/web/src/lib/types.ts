// KnowFlow 前端类型（KF2-008 预研）。
// 字段来源：contracts/api-draft.md（DRAFT 0.2.0-draft.5 候选），KF2-004 未冻结，
// 因此以下形状为候选推断，冻结后以生成客户端为准，不得当作已冻结契约引用。
// 证据类字段（document/content/index/chunk、PDF 页码从 1、TXT/MD 字符区间从 0 且右端不含）
// 与 api-draft.md 的证据一节一致；重建（rebuilds）在冻结前不可公开，故此处不提供重建类型与入口。

export interface ApiErrorBody {
  code: string;
  message: string;
  retryable?: boolean;
}

export class ApiError extends Error {
  status: number;
  code: string;
  retryable: boolean;
  constructor(status: number, body: Partial<ApiErrorBody>) {
    super(body.message || `请求失败（HTTP ${status}）`);
    this.status = status;
    this.code = body.code || "UNKNOWN";
    this.retryable = body.retryable ?? false;
  }
}

export interface User {
  id: string;
  email: string;
  expires_at?: string;
}

export interface AuthResponse {
  token: string;
  user: User;
  expires_at: string;
}

// 注册与登录使用 email + password JSON；密码长度候选为 12–128 字符（draft5 候选）。
export interface AuthRequest {
  email: string;
  password: string;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  status: string;
  document_count?: number;
  created_at?: string;
}

// CreateKnowledgeBase 不接受 owner 字段；列表只返回当前所有者且 ACTIVE 的知识库。
export interface CreateKnowledgeBaseRequest {
  name: string;
}

// 文档状态：draft5 候选提及 QUEUED（已提交未 READY）、READY（已发布索引）、FAILED。
// 完整枚举以 KF2-004 冻结为准；状态响应不返回执行令牌、对象键、原文、向量或内部凭证。
export type DocumentStatus = "QUEUED" | "READY" | "FAILED";

export interface DocumentItem {
  id: string;
  knowledge_base_id: string;
  name: string;
  format: "txt" | "md" | "pdf";
  status: DocumentStatus;
  index_version_id?: string | null;
  task_id?: string | null;
  created_at?: string;
}

export interface DocumentUploadAccepted {
  document_id: string;
  task_id: string;
}

export interface TaskItem {
  id: string;
  document_id?: string;
  status: string;
  attempts?: number;
  failure?: ApiErrorBody | null;
}

export type Locator =
  | { kind: "page"; page: number }
  | { kind: "char_range"; start: number; end: number };

export interface SourceRef {
  source_id: string;
  document_id: string;
  content_version_id?: string;
  index_version_id?: string;
  chunk_id?: string;
  locator: Locator;
  snippet: string;
}

// 问答公开请求只包含问题；客户端不得提交 owner、快照、索引范围或向量。
// 有答案必须有至少一个来源；无证据时 has_answer=false 且来源为空；答案最多 5 条引用。
export interface QuestionAnswer {
  answer: string;
  has_answer: boolean;
  sources: SourceRef[];
  index_version_id?: string;
}

export interface QuestionHistoryItem {
  id: string;
  question: string;
  answer?: string;
  has_answer: boolean;
  created_at?: string;
}
