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

beforeEach(() => {
  document = { id: "doc", original_name: "当前资料.md", format: "md", status: "READY", byte_size: 20, active_index_version_id: "old-index" };
  taskStatus = "RUNNING";
  historical.sources = [source];
  fileResponse = new Response("%PDF-old", { headers: { "content-type": "application/pdf" } });
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "me") return { user_id: "user", email: "user@example.test" };
    if (path.startsWith("knowledge-bases?")) return { items: [{ id: "kb", name: "资料库", status: "ACTIVE" }] };
    if (path.startsWith("knowledge-bases/kb/documents?")) return { items: [document] };
    if (path.startsWith("questions?")) return { items: [historical] };
    if (path === "questions/old-question") return historical;
    if (path === "documents/doc") return document;
    if (path === "documents/doc/rebuilds" || path === "documents/doc/contents") return { document_id: "doc", task_id: "new-task" };
    if (path === "tasks/new-task") return { task_id: "new-task", status: taskStatus, failure_code: "NEW_INDEX_FAILED" };
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
});

describe("question view isolation", () => {
  it.each(["completed", "error"])("ignores late deltas, sources and %s after opening history", async (terminal) => {
    let onDelta!: (value: string) => void;
    let onSources!: (value: Source[]) => void;
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
      onSources([{ ...source, quote: "新来源" }]);
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
});
