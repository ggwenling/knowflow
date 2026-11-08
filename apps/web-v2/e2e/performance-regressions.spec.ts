import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { base, document, mockWorkspace, question } from "./helpers/workspace";
import { beginRenderProbe, endRenderProbe, installRenderProbe } from "./helpers/render-probe";

test("draft typing stays local to the composer on home and conversation pages", async ({ page }) => {
  await installRenderProbe(page);
  await mockWorkspace(page);
  await page.goto("/");
  const home = page.getByRole("textbox", { name: "向知识库提问" });
  await expect(page.getByRole("button", { name: "提问", exact: true })).toBeDisabled();
  await expect(page.locator("canvas")).toBeVisible();
  await beginRenderProbe(page);
  await home.pressSequentially("abcdefghij", { delay: 25 });
  const homeCounts = await endRenderProbe(page);
  expect(homeCounts.shell ?? 0).toBe(0);
  expect(homeCounts.home ?? 0).toBe(0);
  await page.goto("/conversations");
  const composer = page.getByRole("textbox", { name: "问题", exact: true });
  await expect(composer).toBeEnabled();
  await beginRenderProbe(page);
  await composer.pressSequentially("abcdefghij", { delay: 25 });
  const counts = await endRenderProbe(page);
  expect(counts.composer).toBe(10);
  expect(counts.shell ?? 0).toBe(0);
  expect(counts.history ?? 0).toBe(0);
  expect(counts.documents ?? 0).toBe(0);
});

test("stream deltas update the answer without re-rendering history or documents", async ({ page }) => {
  await installRenderProbe(page);
  await mockWorkspace(page);
  await page.addInitScript(() => {
    const original = window.fetch;
    const probe = window as unknown as { __finishStreamProbe: boolean };
    probe.__finishStreamProbe = false;
    window.fetch = (input, init) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (!path.endsWith("/questions/stream")) return original(input, init);
      let timer: ReturnType<typeof setInterval>;
      const encoder = new TextEncoder();
      const body = new ReadableStream({ start(controller) {
        let sequence = 0;
        const send = (event: string, data: Record<string, unknown> = {}) => controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify({ event, sequence: ++sequence, contract_version: "0.2.0", request_id: "probe", ...data })}\n\n`));
        send("started");
        let chunk = 0;
        timer = setInterval(() => {
          if (chunk < 12) send("delta", { delta: `part-${++chunk} ` });
          else if (probe.__finishStreamProbe) { send("sources", { has_answer: false, sources: [] }); send("completed"); clearInterval(timer); controller.close(); }
        }, 100);
      }, cancel() { clearInterval(timer); } });
      return Promise.resolve(new Response(body, { headers: { "content-type": "text/event-stream", "x-request-id": "probe" } }));
    };
  });
  await page.goto("/conversations");
  await page.locator("#desk-question").fill("验证流式渲染");
  await page.getByRole("button", { name: "提问", exact: true }).click();
  await expect(page.getByRole("button", { name: "停止生成" })).toBeVisible();
  await beginRenderProbe(page);
  await expect(page.locator('[class*="streamingText"]')).toContainText("part-9");
  const counts = await endRenderProbe(page);
  await page.evaluate(() => { (window as unknown as { __finishStreamProbe: boolean }).__finishStreamProbe = true; });
  expect(counts.answer).toBeGreaterThanOrEqual(3);
  expect(counts.shell ?? 0).toBe(0);
  expect(counts.history ?? 0).toBe(0);
  expect(counts.documents ?? 0).toBe(0);
});

test("settings renders while unrelated history is still pending", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname !== "/api/v1/questions") return false;
    await gate; await route.fulfill({ json: { items: [], has_more: false } }); return true;
  });
  try {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
    await expect(page.getByText("optimization@example.test", { exact: true }).last()).toBeVisible();
  } finally { release(); }
});

test("first knowledge-base page is visible before a slow second page finishes", async ({ page }) => {
  let release!: () => void;
  let secondPage = false;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname !== "/api/v1/knowledge-bases") return false;
    if (!Number(url.searchParams.get("offset"))) { await route.fulfill({ json: { items: [base], has_more: true } }); return true; }
    secondPage = true; await gate; await route.fulfill({ json: { items: [{ ...base, id: "base-2", name: "后续知识库" }], has_more: false } }); return true;
  });
  try {
    await page.goto("/knowledge-bases");
    await expect.poll(() => secondPage).toBe(true);
    await expect(page.getByRole("link").filter({ hasText: base.name }).last()).toBeVisible();
    release();
    await expect(page.getByRole("link").filter({ hasText: "后续知识库" }).last()).toBeVisible();
  } finally { release(); }
});

test("task completion revalidates all loaded document pages", async ({ page }) => {
  let rebuilt = false;
  let revalidated = false;
  const documents = Array.from({ length: 60 }, (_, i) => ({ ...document, id: `doc-${i}`, original_name: `file-${i}.txt` }));
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname.endsWith("/documents")) { const offset = Number(url.searchParams.get("offset")); if (rebuilt && offset === 50) revalidated = true; await route.fulfill({ json: { items: documents.slice(offset, offset + 50), has_more: offset + 50 < documents.length } }); return true; }
    if (url.pathname.endsWith("/rebuilds")) { rebuilt = true; await route.fulfill({ status: 202, json: { task_id: "task-complete" } }); return true; }
    if (url.pathname === "/api/v1/documents/doc-0") { await route.fulfill({ json: { ...documents[0], latest_task_id: "task-complete", latest_task_status: "SUCCEEDED" } }); return true; }
    if (url.pathname === "/api/v1/tasks/task-complete") { await route.fulfill({ json: { task_id: "task-complete", status: "SUCCEEDED", failure_code: null } }); return true; }
    return false;
  });
  await page.goto(`/knowledge-bases/${base.id}`);
  await page.getByRole("button", { name: "加载更多资料" }).click();
  await expect(page.getByRole("article")).toHaveCount(60);
  await page.getByRole("button", { name: "file-0.txt 操作", exact: true }).click();
  await page.getByRole("menuitem", { name: "重建索引" }).click();
  await expect.poll(() => rebuilt).toBe(true);
  await expect.poll(() => revalidated).toBe(true);
  await expect.poll(() => page.getByRole("article").count()).toBe(60);
  await expect(page.getByRole("article").filter({ hasText: "file-59.txt" })).toBeVisible();
});

test("unchanged polling results preserve document subscriptions", async ({ page }) => {
  await installRenderProbe(page);
  let polls = 0;
  const pending = { ...document, status: "QUEUED", latest_task_id: "same-task", latest_task_status: "RUNNING" };
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname.endsWith("/documents")) { await route.fulfill({ json: { items: [pending], has_more: false } }); return true; }
    if (url.pathname === `/api/v1/documents/${document.id}`) { await route.fulfill({ json: pending }); return true; }
    if (url.pathname === "/api/v1/tasks/same-task") { polls++; await route.fulfill({ json: { task_id: "same-task", status: "RUNNING", failure_code: null } }); return true; }
    return false;
  });
  await page.goto("/conversations");
  await expect.poll(() => polls).toBeGreaterThanOrEqual(1);
  await beginRenderProbe(page);
  await expect.poll(() => polls).toBeGreaterThanOrEqual(2);
  await page.evaluate(async () => { await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame); });
  const counts = await endRenderProbe(page);
  expect(counts.documents ?? 0).toBe(0);
  expect(counts.shell ?? 0).toBe(0);
  expect(counts.history ?? 0).toBe(0);
});

test("polling concurrency is bounded and logout cancels its old scope", async ({ page }) => {
  let concurrent = 0; let maximum = 0; let polls = 0; let loggedOut = false;
  const pending = Array.from({ length: 12 }, (_, i) => ({ ...document, id: `pending-${i}`, status: "QUEUED", latest_task_id: `task-${i}`, latest_task_status: "RUNNING" }));
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname.endsWith("auth/logout")) { loggedOut = true; await route.fulfill({ status: 204 }); return true; }
    if (loggedOut && url.pathname === "/api/v1/me") { await route.fulfill({ status: 401, json: { code: "UNAUTHENTICATED" } }); return true; }
    if (url.pathname.endsWith("/documents")) { await route.fulfill({ json: { items: pending, has_more: false } }); return true; }
    if (/\/(documents|tasks)\/(pending-|task-)/.test(url.pathname)) {
      concurrent++; maximum = Math.max(maximum, concurrent); polls++;
      await new Promise((resolve) => setTimeout(resolve, 80));
      concurrent--;
      const id = Number(url.pathname.split("-").at(-1));
      await route.fulfill({ json: url.pathname.includes("/tasks/") ? { task_id: `task-${id}`, status: "RUNNING", failure_code: null } : pending[id] }).catch(() => {});
      return true;
    }
    return false;
  });
  await page.goto(`/knowledge-bases/${base.id}`);
  await expect.poll(() => polls).toBeGreaterThanOrEqual(8);
  expect(maximum).toBeLessThanOrEqual(4);
  await page.getByRole("button", { name: "退出", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  const stopped = polls;
  await page.waitForTimeout(2200); // Observe beyond the original 1.5s interval.
  expect(polls).toBe(stopped);
});

test("PDF sources use the native viewer without a main-frame probe GET", async ({ page }) => {
  const pdf = await readFile(resolve(process.cwd(), "../../services/ai/tests/fixtures/pdf/chinese-pages.pdf"));
  const source = { source_id: "pdf-source", document_id: document.id, content_version_id: "v1", quote: "PDF 原文依据", locator: { kind: "pdf_page", page: 1, start: null, end: null, unit: null } };
  let probeGets = 0; let fileGets = 0;
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname === "/api/v1/questions/q-1") { await route.fulfill({ json: { ...question(1), answer: "PDF 回答", has_answer: true, failure_code: null, sources: [source] } }); return true; }
    if (url.pathname === "/api/v1/sources/pdf-source") { await route.fulfill({ json: { ...source, state: "AVAILABLE" } }); return true; }
    if (url.pathname.endsWith("/file")) { fileGets++; if (route.request().resourceType() === "fetch") probeGets++; await route.fulfill({ contentType: "application/pdf", body: pdf }); return true; }
    return false;
  });
  await page.goto("/conversations/q-1");
  await page.getByRole("button").filter({ hasText: source.quote }).click();
  await expect(page.getByRole("dialog").locator("iframe")).toHaveAttribute("src", /#page=1$/);
  await expect.poll(() => fileGets).toBeGreaterThanOrEqual(1);
  expect(probeGets).toBe(0);
  await expect(page.getByRole("link", { name: "在新窗口打开 PDF 原文" })).toBeVisible();
  await expect(page.locator("iframe")).not.toHaveAttribute("tabindex", "-1");
});
