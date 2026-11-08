import { expect, test } from "@playwright/test";

const source = {
  source_id: "s1",
  document_id: "doc-1",
  content_version_id: "v1",
  quote: "索引状态只有 READY 时才会参与问答。",
  locator: { kind: "text", page: null, start: null, end: null, unit: null },
};

const answer = "## 结论\n\n只有在索引状态为 **READY** 时，资料才会参与问答。\n\n- 上传后先进入处理队列\n- 索引发布后状态变为已就绪";

function frame(event: string, sequence: number, payload: Record<string, unknown>) {
  return `event: ${event}\ndata: ${JSON.stringify({
    sequence,
    contract_version: "0.2.0",
    request_id: "req-chat-flow",
    event,
    ...payload,
  })}\n\n`;
}

test.beforeEach(async ({ page }) => {
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/mode") return route.fulfill({ json: { mode: "synthetic" } });
    if (path === "/api/v1/me") return route.fulfill({ json: { user_id: "chat", email: "chat@example.test" } });
    if (path === "/api/v1/knowledge-bases") {
      return route.fulfill({ json: { items: [{ id: "base-1", name: "流程资料库", status: "ACTIVE" }], has_more: false } });
    }
    if (path.endsWith("/documents")) {
      return route.fulfill({ json: {
        items: [{ id: "doc-1", original_name: "流程规则.md", status: "READY", active_index_version_id: "idx-1", format: "MD", byte_size: 2048 }],
        has_more: false,
      } });
    }
    if (path === "/api/v1/questions") return route.fulfill({ json: { items: [], has_more: false } });
    if (path === "/api/v1/knowledge-bases/base-1/questions/stream") {
      const body = [
        frame("started", 1, {}),
        frame("delta", 2, { delta: answer }),
        frame("sources", 3, { has_answer: true, sources: [source] }),
        frame("completed", 4, {}),
      ].join("");
      return route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body });
    }
    if (path === "/api/v1/sources/s1") return route.fulfill({ json: { ...source, state: "AVAILABLE" } });
    if (path === "/api/v1/documents/doc-1/contents/v1/file") {
      return route.fulfill({ status: 200, headers: { "content-type": "text/plain; charset=utf-8" }, body: source.quote });
    }
    return route.fulfill({ status: 404, json: {} });
  });
});

test("streamed answer renders markdown, citations, copy and keyboard-dismissed source", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/conversations");
  await expect(page.getByRole("heading", { name: "对话", exact: true })).toBeVisible();

  const composer = page.getByPlaceholder("例如：这个接口有哪些必填字段？");
  await composer.fill("什么时候允许使用这份资料进行问答？");
  await page.getByRole("button", { name: "提问", exact: true }).click();

  await expect(page.getByRole("heading", { name: "结论", exact: true })).toBeVisible();
  await expect(page.getByText("READY", { exact: true })).toBeVisible();
  await expect(page.getByText("已完成", { exact: false })).toBeVisible();

  const citation = page.getByRole("button").filter({ hasText: source.quote }).first();
  await expect(citation).toBeVisible();
  await citation.click();
  const dialog = page.getByRole("dialog", { name: "原文依据" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("pre")).toContainText(source.quote);
  const close = page.getByRole("button", { name: "关闭原文" });
  await expect(close).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(citation).toBeFocused();

  await page.getByRole("button", { name: "复制回答" }).click();
  await expect(page.getByText("回答已复制")).toBeVisible();
});
