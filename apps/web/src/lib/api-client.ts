// 统一 API 客户端（KF2-008 预研）。
// 基地址来自 NEXT_PUBLIC_API_BASE_URL（默认 http://localhost:8080，与 apps/web/.env.example 一致）。
// 浏览器只访问 Java API，不直接携带模型 API Key 调用供应商；密钥不得放进 NEXT_PUBLIC 变量。
// 注意：KF2-004 未冻结，本客户端按 DRAFT 0.2.0-draft.5 候选端点编写；冻结后以生成客户端替换。
// 令牌存放策略（持久化、CSRF、刷新、限速）为 draft5 尚待决定项；此处暂用 localStorage，冻结前需复核。
// 重建（POST /documents/{id}/rebuilds）冻结前不可公开，故本客户端不提供重建入口。

import {
  ApiError,
  AuthRequest,
  AuthResponse,
  CreateKnowledgeBaseRequest,
  DocumentItem,
  DocumentUploadAccepted,
  KnowledgeBase,
  QuestionAnswer,
  QuestionHistoryItem,
  SourceRef,
  TaskItem,
  User,
} from "./types";

const TOKEN_KEY = "knowflow_token";

export function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080";
}

export function isMockMode(): boolean {
  return process.env.NEXT_PUBLIC_USE_MOCK === "true";
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {}),
    },
  });
  const text = await res.text();
  const body = text ? safeJson(text) : null;
  if (!res.ok) {
    throw new ApiError(res.status, {
      code:
        body && typeof body.code === "string" ? body.code : defaultCode(res.status),
      message:
        body && typeof body.message === "string"
          ? body.message
          : `请求失败（HTTP ${res.status}）`,
      retryable: body && typeof body.retryable === "boolean" ? body.retryable : undefined,
    });
  }
  return body as T;
}

function safeJson(text: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}

function defaultCode(status: number): string {
  if (status === 401) return "UNAUTHENTICATED";
  if (status === 404) return "RESOURCE_NOT_FOUND";
  if (status === 413) return "RESOURCE_LIMIT";
  if (status === 415) return "INVALID_REQUEST";
  return "UNKNOWN";
}

function as<T>(value: unknown): T {
  return value as T;
}

export const api = {
  async login(req: AuthRequest): Promise<AuthResponse> {
    const data = await request<Record<string, unknown>>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(req),
    });
    const auth = as<AuthResponse>(data);
    setToken(auth.token);
    return auth;
  },

  async register(req: AuthRequest): Promise<AuthResponse> {
    const data = await request<Record<string, unknown>>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(req),
    });
    const auth = as<AuthResponse>(data);
    setToken(auth.token);
    return auth;
  },

  async logout(): Promise<void> {
    try {
      await request("/api/v1/auth/logout", { method: "POST" });
    } finally {
      setToken(null);
    }
  },

  getToken,

  async me(): Promise<User> {
    return request<User>("/api/v1/me");
  },

  async listKnowledgeBases(limit = 50, offset = 0): Promise<KnowledgeBase[]> {
    const data = await request<unknown>(`/api/v1/knowledge-bases?limit=${limit}&offset=${offset}`);
    if (Array.isArray(data)) return data as KnowledgeBase[];
    const obj = data as { items?: KnowledgeBase[] };
    return obj.items || [];
  },

  async createKnowledgeBase(req: CreateKnowledgeBaseRequest): Promise<KnowledgeBase> {
    return request<KnowledgeBase>("/api/v1/knowledge-bases", {
      method: "POST",
      body: JSON.stringify(req),
    });
  },

  async getKnowledgeBase(kbId: string): Promise<KnowledgeBase> {
    return request<KnowledgeBase>(`/api/v1/knowledge-bases/${kbId}`);
  },

  async deleteKnowledgeBase(kbId: string): Promise<void> {
    await request(`/api/v1/knowledge-bases/${kbId}`, { method: "DELETE" });
  },

  async listDocuments(kbId: string, limit = 50, offset = 0): Promise<DocumentItem[]> {
    const data = await request<unknown>(
      `/api/v1/knowledge-bases/${kbId}/documents?limit=${limit}&offset=${offset}`,
    );
    if (Array.isArray(data)) return data as DocumentItem[];
    const obj = data as { items?: DocumentItem[] };
    return obj.items || [];
  },

  async uploadDocument(kbId: string, file: File): Promise<DocumentUploadAccepted> {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentUploadAccepted>(`/api/v1/knowledge-bases/${kbId}/documents`, {
      method: "POST",
      body: form,
    });
  },

  async getDocument(documentId: string): Promise<DocumentItem> {
    return request<DocumentItem>(`/api/v1/documents/${documentId}`);
  },

  async deleteDocument(documentId: string): Promise<void> {
    await request(`/api/v1/documents/${documentId}`, { method: "DELETE" });
  },

  async getTask(taskId: string): Promise<TaskItem> {
    return request<TaskItem>(`/api/v1/tasks/${taskId}`);
  },

  async askQuestion(kbId: string, question: string): Promise<QuestionAnswer> {
    return request<QuestionAnswer>(`/api/v1/knowledge-bases/${kbId}/questions`, {
      method: "POST",
      body: JSON.stringify({ question }),
    });
  },

  // SSE：事件顺序 started → delta（零到多次）→ sources → completed，异常为 error/cancelled 且只有一个终态。
  // 本预研只实现事件解析骨架；流式页面体验属 KF2-032，不在此处展开。
  async askQuestionStream(
    kbId: string,
    question: string,
    onEvent: (event: { type: string; data: unknown }) => void,
  ): Promise<void> {
    const token = getToken();
    const res = await fetch(`${getApiBaseUrl()}/api/v1/knowledge-bases/${kbId}/questions/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ question }),
    });
    if (!res.ok || !res.body) {
      throw new ApiError(res.status, { code: defaultCode(res.status), message: "流式问答请求失败" });
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const chunk = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        let type = "message";
        let dataText = "";
        for (const line of chunk.split("\n")) {
          if (line.startsWith("event:")) type = line.slice(6).trim();
          else if (line.startsWith("data:")) dataText += line.slice(5).trim();
        }
        let data: unknown = dataText;
        try {
          data = JSON.parse(dataText);
        } catch {
          // 非 JSON 事件体按原文透传
        }
        onEvent({ type, data });
      }
    }
  },

  async getSource(sourceId: string): Promise<SourceRef> {
    return request<SourceRef>(`/api/v1/sources/${sourceId}`);
  },

  async listQuestions(): Promise<QuestionHistoryItem[]> {
    const data = await request<unknown>("/api/v1/questions");
    if (Array.isArray(data)) return data as QuestionHistoryItem[];
    const obj = data as { items?: QuestionHistoryItem[] };
    return obj.items || [];
  },

  async deleteQuestion(questionId: string): Promise<void> {
    await request(`/api/v1/questions/${questionId}`, { method: "DELETE" });
  },
};
