// Mock 数据与 Mock 客户端（KF2-008 预研，仅用于开发）。
// Mock 模式必须可见地区分，不能代替真实端到端验收；字段以 DRAFT 0.2.0-draft.5 候选为准，
// KF2-004 冻结后以生成客户端替换。本文件不含任何真实用户数据，示例内容均为虚构。

import {
  DocumentItem,
  KnowledgeBase,
  QuestionAnswer,
  TaskItem,
} from "./types";

export const MOCK_NOTICE =
  "Mock 模式：当前为开发用模拟数据，非真实接口；字段以 DRAFT 0.2.0-draft.5 候选为准，KF2-004 冻结后替换为生成客户端。";

export const mockUser = { id: "mock-user-1", email: "demo@example.com" };

export const mockKnowledgeBases: KnowledgeBase[] = [
  { id: "kb-demo-1", name: "示例知识库：项目规范", status: "ACTIVE", document_count: 2 },
  { id: "kb-demo-2", name: "示例知识库：故障记录", status: "ACTIVE", document_count: 1 },
];

export const mockDocuments: Record<string, DocumentItem[]> = {
  "kb-demo-1": [
    {
      id: "doc-demo-1",
      knowledge_base_id: "kb-demo-1",
      name: "项目规范示例.md",
      format: "md",
      status: "READY",
      index_version_id: "idx-demo-1",
      task_id: "task-demo-1",
    },
    {
      id: "doc-demo-2",
      knowledge_base_id: "kb-demo-1",
      name: "接口说明示例.pdf",
      format: "pdf",
      status: "QUEUED",
      index_version_id: null,
      task_id: "task-demo-2",
    },
  ],
  "kb-demo-2": [
    {
      id: "doc-demo-3",
      knowledge_base_id: "kb-demo-2",
      name: "故障记录示例.txt",
      format: "txt",
      status: "READY",
      index_version_id: "idx-demo-2",
      task_id: "task-demo-3",
    },
  ],
};

export const mockTasks: Record<string, TaskItem> = {
  "task-demo-1": { id: "task-demo-1", document_id: "doc-demo-1", status: "SUCCEEDED", attempts: 1 },
  "task-demo-2": { id: "task-demo-2", document_id: "doc-demo-2", status: "QUEUED", attempts: 0 },
  "task-demo-3": { id: "task-demo-3", document_id: "doc-demo-3", status: "SUCCEEDED", attempts: 1 },
};

const delay = (ms = 250) => new Promise((resolve) => setTimeout(resolve, ms));

export const mockApi = {
  async login(): Promise<{ token: string; user: typeof mockUser; expires_at: string }> {
    await delay();
    return { token: "mock-token", user: mockUser, expires_at: "2099-01-01T00:00:00Z" };
  },

  async listKnowledgeBases(): Promise<KnowledgeBase[]> {
    await delay();
    return mockKnowledgeBases;
  },

  async listDocuments(kbId: string): Promise<DocumentItem[]> {
    await delay();
    return mockDocuments[kbId] || [];
  },

  async getTask(taskId: string): Promise<TaskItem> {
    await delay();
    const task = mockTasks[taskId];
    if (!task) throw new Error("任务不存在（Mock）");
    return task;
  },

  async askQuestion(kbId: string, question: string): Promise<QuestionAnswer> {
    await delay(400);
    if (kbId === "kb-demo-2" && question.includes("不存在")) {
      return { answer: "", has_answer: false, sources: [], index_version_id: "idx-demo-2" };
    }
    return {
      answer:
        "示例回答（Mock）：删除文档后，相关引用不再可访问；删除前已到达客户端的内容无法撤回。此结论来自示例文档，与真实接口无关。",
      has_answer: true,
      sources: [
        {
          source_id: "src-demo-1",
          document_id: "doc-demo-1",
          content_version_id: "cv-demo-1",
          index_version_id: "idx-demo-1",
          chunk_id: "chunk-demo-1",
          locator: { kind: "char_range", start: 120, end: 240 },
          snippet: "删除提交后开始的新请求不能检索、查看原文或引用。进行中的回答在输出答案/来源前再次检查可见性。",
        },
        {
          source_id: "src-demo-2",
          document_id: "doc-demo-2",
          content_version_id: "cv-demo-2",
          index_version_id: "idx-demo-1",
          chunk_id: "chunk-demo-2",
          locator: { kind: "page", page: 3 },
          snippet: "示例 PDF 第 3 页片段（Mock）：引用需绑定文档、内容版本与索引版本，缺一不可。",
        },
      ],
      index_version_id: "idx-demo-1",
    };
  },
};
