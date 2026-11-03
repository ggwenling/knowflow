import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, streamQuestion, type Document, type QuestionDetail, type Source } from "@/lib/api";
import Workspace from "./workspace";

vi.mock("@/lib/api", () => ({ api: vi.fn(), streamQuestion: vi.fn() }));

const source: Source = {
  source_id: "old-source", document_id: "doc", content_version_id: "old-version",
  quote: "历史引用", locator: { kind: "pdf_page", page: 3, start: null, end: null, unit: null },
};
const historical: QuestionDetail = {
  question_id: "old-question", knowledge_base_id: "kb", question: "历史问题",
  status: "FAILED", finished_at: null, answer: "历史回答", has_answer: true,
  failure_code: "MODEL_FAILURE", sources: [source],
};
let document: Document;
let fileResponse: Response;
let taskStatus: string;

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  document = { id: "doc", original_name: "当前资料.md", format: "md", status: "READY", byte_size: 20, active_index_version_id: "old-index" };
  taskStatus = "RUNNING";
  historical.sources = [source];
  fileResponse = new Response("%PDF-old", { headers: { "content-type": "application/pdf" } });
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "me") return { user_id: "user", email: "user@example.test" };
    if (path.startsWith("knowledge-bases?")) return { items: [{ id: "kb", name: "资料库", status: "ACTIVE" }] };
    if (path.startsWith("knowledge-bases/kb/documents?")) return { items: [taskStatus === "SUCCEEDED" ? { ...document, status: "READY", active_index_version_id: "ready-index" } : document] };
    if (path.startsWith("questions?")) return { items: [historical] };
    if (path === "questions/old-question") return historical;
    if (path === "documents/doc") return taskStatus === "SUCCEEDED" ? { ...document, status: "READY", active_index_version_id: "ready-index" } : document;
    if (path === "documents/doc/rebuilds" || path === "documents/doc/contents") return { document_id: "doc", task_id: "new-task" };
    if (path === "tasks/new-task") return { task_id: "new-task", status: taskStatus, failure_code: "NEW_INDEX_FAILED" };
    if (path === "tasks/recovered-task") return { task_id: "recovered-task", status: taskStatus, failure_code: null };
    if (path === "sources/old-source") return source;
    throw new Error(`Unexpected API path: ${path}`);
  });
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (url === "/api/mode") return Response.json({ mode: "synthetic" });
    if (url.endsWith("/file")) return fileResponse;
    if (url.endsWith("/questions/stream")) return new Response();
    throw new Error(`Unexpected fetch: ${url}`);
  }));
  vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:historical-pdf"), revokeObjectURL: vi.fn() });
});

afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks(); vi.unstubAllGlobals(); });

async function openWorkspace() {
  render(<Workspace />);
  await screen.findByText(document.original_name);
}

it("shows the ninth history item and loads the next document and history pages", async () => {
  const history = Array.from({ length: 50 }, (_, index) => ({ ...historical, question_id: `q${index}`, question: `问题 ${index}` }));
  const docs = Array.from({ length: 50 }, (_, index) => ({ ...document, id: `d${index}`, original_name: `资料${index}.md` }));
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "me") return { user_id: "user", email: "user@example.test" };
    if (path.startsWith("knowledge-bases?")) return { items: [{ id: "kb", name: "资料库", status: "ACTIVE" }] };
    if (path.includes("/documents?")) return path.includes("offset=0") ? { items: docs, has_more: true } : { items: [{ ...document, id: "d50", original_name: "第51份.md" }], has_more: false };
    if (path.startsWith("questions?")) return path.includes("offset=0") ? { items: history, has_more: true } : { items: [{ ...historical, question_id: "q50", question: "第51个问题" }], has_more: false };
    throw new Error(`Unexpected API path: ${path}`);
  });
  render(<Workspace />);
  expect(await screen.findByText("问题 8")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "加载更多资料" }));
  expect(await screen.findByText("第51份.md")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "加载更多问答" }));
  expect(await screen.findByText("第51个问题")).toBeVisible();
  expect(api).toHaveBeenCalledWith("knowledge-bases/kb/documents?limit=50&offset=50");
  expect(api).toHaveBeenCalledWith("questions?limit=50&offset=50");
});

it("ignores a late document page after switching knowledge bases", async () => {
  const pending = deferred<{ items: Document[]; has_more: boolean }>();
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "me") return { user_id: "user", email: "user@example.test" };
    if (path.startsWith("knowledge-bases?")) return { items: [{ id: "kb", name: "资料库", status: "ACTIVE" }, { id: "kb-b", name: "第二资料库", status: "ACTIVE" }] };
    if (path === "knowledge-bases/kb/documents?limit=50&offset=0") return { items: [document], has_more: true };
    if (path === "knowledge-bases/kb/documents?limit=50&offset=1") return pending.promise;
    if (path.startsWith("knowledge-bases/kb-b/documents?")) return { items: [] };
    if (path.startsWith("questions?")) return { items: [] };
    throw new Error(`Unexpected API path: ${path}`);
  });
  await openWorkspace();
  fireEvent.click(screen.getByRole("button", { name: "加载更多资料" }));
  fireEvent.click(screen.getByRole("button", { name: /第二资料库/ }));
  await screen.findByRole("heading", { name: "第二资料库" });
  await act(async () => { pending.resolve({ items: [{ ...document, original_name: "迟到资料.md" }], has_more: false }); });
  expect(screen.queryByText("迟到资料.md")).not.toBeInTheDocument();
});

it("blocks pagination while refreshing and resumes at the refreshed offset", async () => {
  const pending = deferred<{ items: Document[]; has_more: boolean }>();
  const first = Array.from({ length: 50 }, (_, i) => ({ ...document, id: `d${i}`, original_name: `资料${i}.md` }));
  const second = Array.from({ length: 50 }, (_, i) => ({ ...document, id: `d${i + 50}`, original_name: `资料${i + 50}.md` }));
  let firstPageCalls = 0;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "me") return { user_id: "user", email: "user@example.test" };
    if (path.startsWith("knowledge-bases?")) return { items: [{ id: "kb", name: "资料库", status: "ACTIVE" }] };
    if (path === "knowledge-bases/kb/documents?limit=50&offset=0") return ++firstPageCalls === 1 ? { items: first, has_more: true } : pending.promise;
    if (path === "knowledge-bases/kb/documents?limit=50&offset=50") return { items: second, has_more: true };
    if (path.startsWith("questions?")) return { items: [], has_more: true };
    throw new Error(`Unexpected API path: ${path}`);
  });
  render(<Workspace />);
  await screen.findByText("资料0.md");
  fireEvent.click(screen.getByRole("button", { name: "加载更多资料" }));
  await screen.findByText("资料99.md");
  fireEvent.click(screen.getByRole("button", { name: /^▤\s*资料库$/ }));
  await waitFor(() => expect(firstPageCalls).toBe(2));
  expect(screen.getByRole("button", { name: "加载更多资料" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "加载更多问答" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "加载更多资料" }));
  expect(api).not.toHaveBeenCalledWith("knowledge-bases/kb/documents?limit=50&offset=100");
  await act(async () => { pending.resolve({ items: first, has_more: true }); });
  await waitFor(() => expect(screen.getByRole("button", { name: "加载更多资料" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "加载更多资料" }));
  await screen.findByText("资料99.md");
  expect(vi.mocked(api).mock.calls.filter(([path]) => path === "knowledge-bases/kb/documents?limit=50&offset=50")).toHaveLength(2);
});

it("keeps pagination blocked until the newest overlapping refresh finishes", async () => {
  const old = deferred<{ items: Document[]; has_more: boolean }>();
  const latest = deferred<{ items: Document[]; has_more: boolean }>();
  let calls = 0;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "me") return { user_id: "user", email: "user@example.test" };
    if (path.startsWith("knowledge-bases?")) return { items: [{ id: "kb", name: "资料库", status: "ACTIVE" }] };
    if (path.startsWith("knowledge-bases/kb/documents?")) return ++calls === 1 ? { items: [document], has_more: true } : calls === 2 ? old.promise : latest.promise;
    if (path.startsWith("questions?")) return { items: [] };
    throw new Error(`Unexpected API path: ${path}`);
  });
  await openWorkspace();
  const base = screen.getByRole("button", { name: /^▤\s*资料库$/ });
  fireEvent.click(base); fireEvent.click(base);
  await waitFor(() => expect(calls).toBe(3));
  await act(async () => { old.reject(new Error("旧刷新失败")); });
  expect(screen.getByRole("button", { name: "加载更多资料" })).toBeDisabled();
  expect(screen.queryByText("旧刷新失败")).not.toBeInTheDocument();
  await act(async () => { latest.resolve({ items: [document], has_more: true }); });
  await waitFor(() => expect(screen.getByRole("button", { name: "加载更多资料" })).toBeEnabled());
});

describe("index task polling", () => {
  it.each(["重建索引", "更新资料"])("waits for the new task when %s retains a READY index", async (action) => {
    await openWorkspace();
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: `${document.original_name} 操作` }));
    if (action === "重建索引") fireEvent.click(screen.getByRole("menuitem", { name: action }));
    else {
      fireEvent.click(screen.getByRole("menuitem", { name: action }));
      fireEvent.change(window.document.getElementById("update-doc")!, { target: { files: [new File(["new"], "new.md")] } });
    }
    await act(async () => {});
    const upload = window.document.querySelector('input[type="file"]')!;
    expect(upload).toBeDisabled();
    expect(api).toHaveBeenCalledWith("tasks/new-task");
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(upload).toBeDisabled();
    taskStatus = "FAILED";
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(screen.getByText("NEW_INDEX_FAILED")).toBeVisible();
    expect(upload).not.toBeDisabled();
  });

  it("resumes polling an in-flight task after workspace load even with a READY index", async () => {
    document = { ...document, status: "READY", active_index_version_id: "old-index", latest_task_id: "recovered-task", latest_task_status: "RUNNING" };
    await openWorkspace();
    await waitFor(() => expect(api).toHaveBeenCalledWith("tasks/recovered-task"));
    await act(async () => {});
    vi.useFakeTimers();
    taskStatus = "SUCCEEDED";
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(screen.getByText(document.original_name).closest("article")).toHaveTextContent("已就绪");
  });
});

describe("knowledge-base refresh isolation", () => {
  it.each(["documents", "history"])("clears deleted-source answers even when the %s refresh fails", async (failedList) => {
    const originalApi = vi.mocked(api).getMockImplementation()!;
    let deleted = false;
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(api).mockImplementation(async (path, init) => {
      if (path === "documents/doc" && init?.method === "DELETE") { deleted = true; return; }
      if (deleted && (failedList === "documents" ? path.includes("/documents?") : path.startsWith("questions?"))) {
        throw new Error("列表刷新失败");
      }
      return originalApi(path, init);
    });
    await openWorkspace();
    fireEvent.click(screen.getByRole("button", { name: /历史问题/ }));
    await screen.findByText("历史回答");
    fireEvent.click(screen.getByRole("button", { name: "当前资料.md 操作" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "删除资料" }));
    await screen.findByText("列表刷新失败");
    expect(screen.queryByText("历史回答")).not.toBeInTheDocument();
    expect(screen.queryByText("历史引用")).not.toBeInTheDocument();
  });

  it.each(["resolve", "reject"])("preserves B's answer when A's post-delete refresh later %s", async (outcome) => {
    const originalApi = vi.mocked(api).getMockImplementation()!;
    const pendingRefresh = deferred<{ items: Document[] }>();
    const secondHistory = { ...historical, question_id: "question-b", knowledge_base_id: "kb-b", question: "第二问题", answer: "第二回答", sources: [] };
    let deleted = false;
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(api).mockImplementation(async (path, init) => {
      if (path.startsWith("knowledge-bases?")) return { items: [
        { id: "kb", name: "资料库", status: "ACTIVE" }, { id: "kb-b", name: "第二资料库", status: "ACTIVE" },
      ] };
      if (path === "documents/doc" && init?.method === "DELETE") { deleted = true; return; }
      if (deleted && path.startsWith("knowledge-bases/kb/documents?")) return pendingRefresh.promise;
      if (path.startsWith("knowledge-bases/kb-b/documents?")) return { items: [] };
      if (path.startsWith("questions?")) return { items: [historical, secondHistory] };
      if (path === "questions/question-b") return secondHistory;
      return originalApi(path, init);
    });
    await openWorkspace();
    fireEvent.click(screen.getByRole("button", { name: /历史问题/ }));
    await screen.findByText("历史回答");
    fireEvent.click(screen.getByRole("button", { name: "当前资料.md 操作" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "删除资料" }));
    await waitFor(() => expect(vi.mocked(api).mock.calls.filter(([path]) => path.startsWith("knowledge-bases/kb/documents?"))).toHaveLength(3));
    fireEvent.click(screen.getByRole("button", { name: /第二资料库/ }));
    await screen.findByRole("heading", { name: "第二资料库" });
    fireEvent.click(await screen.findByRole("button", { name: /第二问题/ }));
    await screen.findByText("第二回答");
    const closeNotice = screen.queryByRole("button", { name: "关闭提示" });
    if (closeNotice) fireEvent.click(closeNotice);
    await act(async () => {
      if (outcome === "resolve") pendingRefresh.resolve({ items: [] });
      else pendingRefresh.reject(new Error("旧知识库刷新失败"));
    });
    expect(screen.getByText("第二回答")).toBeVisible();
    expect(screen.queryByText("该文档已删除，相关来源已失效。")).not.toBeInTheDocument();
    expect(screen.queryByText("旧知识库刷新失败")).not.toBeInTheDocument();
  });

  it("does not invalidate B's pending refresh when deletion in A completes", async () => {
    const deletion = deferred<void>();
    const secondRefresh = deferred<{ items: Document[] }>();
    const secondDocument = { ...document, id: "doc-b", original_name: "第二资料.md" };
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(api).mockImplementation(async (path, init) => {
      if (path === "me") return { user_id: "user", email: "user@example.test" };
      if (path.startsWith("knowledge-bases?")) return { items: [
        { id: "kb", name: "资料库", status: "ACTIVE" }, { id: "kb-b", name: "第二资料库", status: "ACTIVE" },
      ] };
      if (path === "documents/doc" && init?.method === "DELETE") return deletion.promise;
      if (path.startsWith("knowledge-bases/kb/documents?")) return { items: [document] };
      if (path.startsWith("knowledge-bases/kb-b/documents?")) return secondRefresh.promise;
      if (path.startsWith("questions?")) return { items: [] };
      throw new Error(`Unexpected API path: ${path}`);
    });
    await openWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "当前资料.md 操作" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "删除资料" }));
    await waitFor(() => expect(api).toHaveBeenCalledWith("documents/doc", { method: "DELETE" }));
    fireEvent.click(screen.getByRole("button", { name: /第二资料库/ }));
    await waitFor(() => expect(api).toHaveBeenCalledWith("knowledge-bases/kb-b/documents?limit=50&offset=0"));
    await act(async () => { deletion.resolve(); });
    await act(async () => { secondRefresh.resolve({ items: [secondDocument] }); });
    expect(await screen.findByText("第二资料.md")).toBeVisible();
    expect(screen.queryByText("当前资料.md")).not.toBeInTheDocument();
    expect(vi.mocked(api).mock.calls.filter(([path]) => path.startsWith("knowledge-bases/kb/documents?"))).toHaveLength(1);
  });

  it("ignores a stale response after switching A to B and back to A", async () => {
    const stale = deferred<{ items: Document[] }>();
    let calls = 0;
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "me") return { user_id: "user", email: "user@example.test" };
      if (path.startsWith("knowledge-bases?")) return { items: [
        { id: "kb", name: "资料库", status: "ACTIVE" }, { id: "kb-b", name: "第二资料库", status: "ACTIVE" },
      ] };
      if (path.startsWith("knowledge-bases/kb/documents?")) {
        calls += 1;
        return calls === 2 ? stale.promise : { items: [document] };
      }
      if (path.startsWith("knowledge-bases/kb-b/documents?")) return { items: [] };
      if (path.startsWith("questions?")) return { items: [] };
      throw new Error(`Unexpected API path: ${path}`);
    });
    await openWorkspace();
    fireEvent.click(screen.getByRole("button", { name: /^▤\s*资料库$/ }));
    await waitFor(() => expect(calls).toBe(2));
    fireEvent.click(screen.getByRole("button", { name: /第二资料库/ }));
    fireEvent.click(screen.getByRole("button", { name: /^▤\s*资料库$/ }));
    await waitFor(() => expect(calls).toBe(3));
    await screen.findByText(document.original_name);
    await act(async () => { stale.resolve({ items: [{ ...document, original_name: "旧结果.md", status: "PROCESSING" }] }); });
    expect(screen.getByText(document.original_name)).toBeVisible();
    expect(screen.queryByText("旧结果.md")).not.toBeInTheDocument();
  });
  it("ignores an old knowledge-base response after the user switches bases", async () => {
    const secondDocument: Document = { ...document, id: "doc-b", original_name: "第二资料.md" };
    const staleRefresh = deferred<{ items: Document[] }>();
    let firstBaseDocumentCalls = 0;
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "me") return { user_id: "user", email: "user@example.test" };
      if (path.startsWith("knowledge-bases?")) return { items: [
        { id: "kb", name: "资料库", status: "ACTIVE" },
        { id: "kb-b", name: "第二资料库", status: "ACTIVE" },
      ] };
      if (path.startsWith("knowledge-bases/kb/documents?")) {
        firstBaseDocumentCalls += 1;
        return firstBaseDocumentCalls === 1 ? { items: [document] } : staleRefresh.promise;
      }
      if (path.startsWith("knowledge-bases/kb-b/documents?")) return { items: [secondDocument] };
      if (path.startsWith("questions?")) return { items: [historical] };
      if (path === "questions/old-question") return historical;
      throw new Error(`Unexpected API path: ${path}`);
    });

    await openWorkspace();
    fireEvent.click(screen.getByRole("button", { name: /历史问题/ }));
    await waitFor(() => expect(firstBaseDocumentCalls).toBe(2));
    fireEvent.click(screen.getByRole("button", { name: /第二资料库/ }));
    await screen.findByText("第二资料.md");
    await act(async () => { staleRefresh.resolve({ items: [document] }); });
    expect(screen.getByText("第二资料.md")).toBeVisible();
    expect(screen.queryByText("当前资料.md")).not.toBeInTheDocument();
  });
});

describe("question view isolation", () => {
  it.each(["error", "cancelled"])("clears provisional sources after %s", async (terminal) => {
    vi.mocked(streamQuestion).mockImplementation(async (_response, delta, sources) => {
      delta("未完成回答");
      sources([source], true);
      throw terminal === "error" ? new Error("AI_PROCESSING_FAILED") : new DOMException("取消", "AbortError");
    });
    await openWorkspace();
    fireEvent.change(screen.getByRole("textbox", { name: "" }), { target: { value: "未完成问题" } });
    fireEvent.click(screen.getByRole("button", { name: /^提问/ }));
    await screen.findByText(terminal === "error" ? /此问答状态：处理失败/ : /此问答状态：已取消/);
    expect(screen.queryByText("历史引用")).not.toBeInTheDocument();
    expect(screen.getByText("未完成回答")).toBeVisible();
  });

  it("shows an upstream cancellation as cancelled and refreshes history", async () => {
    vi.mocked(streamQuestion).mockRejectedValue(new DOMException("问答未能完成", "AbortError"));
    await openWorkspace();
    fireEvent.change(screen.getByRole("textbox", { name: "" }), { target: { value: "取消的问题" } });
    fireEvent.click(screen.getByRole("button", { name: /^提问/ }));
    expect(await screen.findByText(/此问答状态：已取消/)).toBeVisible();
    expect(screen.queryByText(/此问答状态：处理失败/)).not.toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: "停止生成" })).not.toBeInTheDocument());
  });

  it.each(["completed", "error"])("ignores late deltas, sources and %s after opening history", async (terminal) => {
    let onDelta!: (value: string) => void;
    let onSources!: (value: Source[], hasAnswer: boolean) => void;
    let finish!: () => void;
    let fail!: (error: Error) => void;
    vi.mocked(streamQuestion).mockImplementation((_response, delta, sources) => {
      onDelta = delta; onSources = sources;
      return new Promise<void>((resolve, reject) => { finish = resolve; fail = reject; });
    });
    await openWorkspace();
    fireEvent.change(screen.getByRole("textbox", { name: "" }), { target: { value: "新问题" } });
    fireEvent.click(screen.getByRole("button", { name: /^提问/ }));
    await waitFor(() => expect(streamQuestion).toHaveBeenCalled());
    const streamCall = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/questions/stream"))!;
    fireEvent.click(screen.getByRole("button", { name: /历史问题/ }));
    await screen.findByText("历史回答");
    expect((streamCall[1] as RequestInit).signal?.aborted).toBe(true);
    await act(async () => {
      onDelta("新回答的迟到片段");
      onSources([{ ...source, quote: "新来源" }], true);
      if (terminal === "completed") finish(); else fail(new Error("旧请求失败"));
    });
    expect(screen.getByText("历史回答")).toBeVisible();
    expect(screen.getByText("历史引用")).toBeVisible();
    expect(screen.getByText(/此问答状态：处理失败/)).toBeVisible();
    expect(screen.queryByText(/新回答的迟到片段|新来源|旧请求失败/)).not.toBeInTheDocument();
  });
});

describe("historical source format", () => {
  it.each(["pdf", "text"])("previews the referenced %s version using its response type", async (format) => {
    document.format = format === "pdf" ? "md" : "pdf";
    if (format === "text") historical.sources = [{ ...source, locator: { kind: "text_range", start: 0, end: 6, page: null, unit: "unicode_code_point" } }];
    fileResponse = new Response(format === "pdf" ? "%PDF-old" : "历史文本原文", {
      headers: { "content-type": format === "pdf" ? "Application/PDF; charset=binary" : "text/markdown; charset=utf-8" },
    });
    await openWorkspace();
    fireEvent.click(screen.getByRole("button", { name: /历史问题/ }));
    await screen.findByText("历史回答");
    fireEvent.click(screen.getByRole("button", { name: /历史引用/ }));
    const dialog = await screen.findByRole("dialog", { name: "原文依据" });
    if (format === "pdf") {
      await waitFor(() => expect(within(dialog).getByTitle(/PDF 原文/)).toHaveAttribute("src", "blob:historical-pdf#page=3"));
    } else {
      await waitFor(() => expect(dialog.querySelector("pre")).toHaveTextContent("历史文本原文"));
      expect(dialog.querySelector("iframe")).toBeNull();
    }
    expect(fetch).toHaveBeenCalledWith("/api/v1/documents/doc/contents/old-version/file", expect.anything());
  });

  it("ignores a late source lookup after the viewer is replaced", async () => {
    const sourceA: Source = { ...source, source_id: "source-a", quote: "引用 A" };
    const sourceB: Source = { ...source, source_id: "source-b", content_version_id: "version-b", quote: "引用 B", locator: { kind: "text_range", start: 0, end: 10, page: null, unit: "unicode_code_point" } };
    const pendingSource = deferred<Source>();
    historical.sources = [sourceA, sourceB];
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "me") return { user_id: "user", email: "user@example.test" };
      if (path.startsWith("knowledge-bases?")) return { items: [{ id: "kb", name: "资料库", status: "ACTIVE" }] };
      if (path.startsWith("knowledge-bases/kb/documents?")) return { items: [document] };
      if (path.startsWith("questions?")) return { items: [historical] };
      if (path === "questions/old-question") return historical;
      if (path === "sources/source-a") return pendingSource.promise;
      if (path === "sources/source-b") return sourceB;
      throw new Error(`Unexpected API path: ${path}`);
    });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/mode") return Response.json({ mode: "synthetic" });
      if (url.endsWith("/version-b/file")) return new Response("B original", { headers: { "content-type": "text/markdown" } });
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    await openWorkspace();
    fireEvent.click(screen.getByRole("button", { name: /历史问题/ }));
    await screen.findByText("历史回答");
    fireEvent.click(screen.getByRole("button", { name: /引用 A/ }));
    await waitFor(() => expect(api).toHaveBeenCalledWith("sources/source-a", expect.anything()));
    fireEvent.click(screen.getByRole("button", { name: "关闭原文" }));
    fireEvent.click(screen.getByRole("button", { name: /引用 B/ }));
    const dialog = await screen.findByRole("dialog", { name: "原文依据" });
    await waitFor(() => expect(dialog.querySelector("pre")).toHaveTextContent("B original"));
    await act(async () => { pendingSource.resolve(sourceA); });
    expect(dialog.querySelector("pre")).toHaveTextContent("B original");
    expect(fetch).not.toHaveBeenCalledWith("/api/v1/documents/doc/contents/old-version/file", expect.anything());
  });

  it("ignores a late source file response after the viewer is replaced", async () => {
    const sourceA: Source = { ...source, source_id: "source-a", content_version_id: "version-a", quote: "引用 A", locator: { kind: "text_range", start: 0, end: 10, page: null, unit: "unicode_code_point" } };
    const sourceB: Source = { ...source, source_id: "source-b", content_version_id: "version-b", quote: "引用 B", locator: { kind: "text_range", start: 0, end: 10, page: null, unit: "unicode_code_point" } };
    const pendingFile = deferred<Response>();
    historical.sources = [sourceA, sourceB];
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "me") return { user_id: "user", email: "user@example.test" };
      if (path.startsWith("knowledge-bases?")) return { items: [{ id: "kb", name: "资料库", status: "ACTIVE" }] };
      if (path.startsWith("knowledge-bases/kb/documents?")) return { items: [document] };
      if (path.startsWith("questions?")) return { items: [historical] };
      if (path === "questions/old-question") return historical;
      if (path === "sources/source-a") return sourceA;
      if (path === "sources/source-b") return sourceB;
      throw new Error(`Unexpected API path: ${path}`);
    });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/mode") return Response.json({ mode: "synthetic" });
      if (url.endsWith("/version-a/file")) return pendingFile.promise;
      if (url.endsWith("/version-b/file")) return new Response("B original", { headers: { "content-type": "text/markdown" } });
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    await openWorkspace();
    fireEvent.click(screen.getByRole("button", { name: /历史问题/ }));
    await screen.findByText("历史回答");
    fireEvent.click(screen.getByRole("button", { name: /引用 A/ }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/documents/doc/contents/version-a/file", expect.anything()));
    fireEvent.click(screen.getByRole("button", { name: "关闭原文" }));
    fireEvent.click(screen.getByRole("button", { name: /引用 B/ }));
    const dialog = await screen.findByRole("dialog", { name: "原文依据" });
    await waitFor(() => expect(dialog.querySelector("pre")).toHaveTextContent("B original"));
    await act(async () => { pendingFile.resolve(new Response("A stale original", { headers: { "content-type": "text/markdown" } })); });
    expect(dialog.querySelector("pre")).toHaveTextContent("B original");
    expect(dialog.querySelector("pre")).not.toHaveTextContent("A stale original");
  });
});
