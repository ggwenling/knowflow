import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

let firstPage: Page | undefined;
let firstKnowledgeBase = "";
let secondKnowledgeBase = "";

async function capturedStream(page: Page, question: string) {
  return page.evaluate((text) => (window as unknown as {
    sseCaptures: Record<string, Promise<string>>;
  }).sseCaptures[text], question);
}

function parseSseEvents(body: string) {
  return body.split(/\r?\n\r?\n/).filter((frame) => frame.includes("data:")).map((frame) => {
    const lines = frame.split(/\r?\n/);
    return {
      name: lines.find((line) => line.startsWith("event:"))?.slice(6).trim(),
      data: JSON.parse(lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n")),
    };
  });
}

function expectStream(events: ReturnType<typeof parseSseEvents>, terminal: string) {
  expect(events[0].name).toBe("started");
  // Answer text is buffered until citation validation finishes (see services/ai/docs/answer-streaming.md).
  // Failure terminals (error/cancelled) therefore may have no delta; completed still emits validated text.
  if (terminal === "completed") {
    expect(events.some(({ name }) => name === "delta")).toBeTruthy();
  } else {
    expect(events.some(({ name }) => name === "delta")).toBeFalsy();
    expect(events.some(({ name }) => name === "sources")).toBeFalsy();
  }
  expect(events.at(-1)?.name).toBe(terminal);
  expect(events.filter(({ name }) => ["completed", "error", "cancelled"].includes(name ?? ""))).toHaveLength(1);
  events.forEach(({ name, data }, index) => {
    expect(data).toMatchObject({ contract_version: "0.2.0-draft.10",
      request_id: events[0].data.request_id, sequence: index + 1, event: name });
  });
}

async function expectUnfinishedHistory(page: Page, question: string, status: "FAILED" | "CANCELLED", failureCode = "AI_PROCESSING_FAILED") {
  const history = async () => page.evaluate(async (text) => {
    const list = await (await fetch("/api/v1/questions?limit=100")).json();
    const item = list.items.find((row: { question: string }) => row.question === text);
    return item ? (await fetch(`/api/v1/questions/${item.question_id}`)).json() : null;
  }, question);
  await expect.poll(async () => (await history())?.status).toBe(status);
  const detail = await history();
  expect(detail).toMatchObject({ answer: null, has_answer: null, sources: [],
    failure_code: status === "FAILED" ? failureCode : null });
  expect(detail.finished_at).toBeTruthy();
  return detail;
}

test.afterEach(async () => {
  if (firstPage) {
    for (const id of [firstKnowledgeBase, secondKnowledgeBase]) {
      if (id) await firstPage.evaluate(async (baseId) => fetch(`/api/v1/knowledge-bases/${baseId}`, { method: "DELETE" }), id).catch(() => undefined);
    }
  }
  await firstPage?.context().close();
  firstPage = undefined;
  firstKnowledgeBase = "";
  secondKnowledgeBase = "";
});

test("register, index, stream, verify source, enforce ownership, delete and preview PDF", async ({ page, browser }) => {
  firstPage = page;
  // Keep a wire copy when the real consumer cancels its reader at a terminal.
  // The active-stop scenario must retain the unmodified cancellation path.
  await page.addInitScript(() => {
    const captures: Record<string, Promise<string>> = {};
    (window as unknown as { sseCaptures: typeof captures }).sseCaptures = captures;
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const response = await originalFetch(input, init);
      if (String(input).endsWith("/questions/stream") && typeof init?.body === "string") {
        const question = JSON.parse(init.body).question as string;
        if (!question.startsWith("[e2e:slow]")) captures[question] = response.clone().text();
      }
      return response;
    };
  });
  await page.setViewportSize({ width: 390, height: 844 });
  const email = `web-${randomUUID()}@example.test`;
  const password = "KnowFlow-e2e-only-2026!";
  await page.goto("/");
  await page.getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account", exact: true }).click();

  await expect(page.getByRole("heading", { name: "KnowFlow", exact: true })).toBeVisible();
  await expect(page.getByText("这里还没有知识库。")).toBeVisible();
  await page.getByRole("button", { name: "创建知识库" }).click();
  await expect(page.getByLabel("新知识库名称")).toBeFocused();
  await page.getByRole("button", { name: "对话", exact: true }).click();
  await expect(page.getByRole("heading", { name: "开始整理你的资料" })).toBeVisible();
  await expect(page.getByLabel("新知识库名称")).toBeVisible();
  await expect(page.getByText("我的知识库")).toBeVisible();
  await expect(page.getByText("最近问答")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
  const baseResponse = page.waitForResponse((response) => response.url().endsWith("/api/v1/knowledge-bases") && response.request().method() === "POST");
  const firstBaseName = `浏览器验收 ${randomUUID().slice(0, 8)}`;
  await page.getByLabel("新知识库名称").fill(firstBaseName);
  await page.getByRole("button", { name: "创建知识库" }).click();
  firstKnowledgeBase = (await (await baseResponse).json()).id;
  await expect(page.getByRole("button", { name: new RegExp(firstBaseName) })).toBeVisible();

  const secondBaseResponse = page.waitForResponse((response) => response.url().endsWith("/api/v1/knowledge-bases") && response.request().method() === "POST");
  const secondBaseName = `移动端切换 ${randomUUID().slice(0, 8)}`;
  await page.getByLabel("新知识库名称").fill(secondBaseName);
  await page.getByRole("button", { name: "创建知识库" }).click();
  secondKnowledgeBase = (await (await secondBaseResponse).json()).id;
  await page.getByRole("button", { name: new RegExp(secondBaseName) }).click();
  await expect(page.getByRole("heading", { name: secondBaseName })).toBeVisible();
  await page.getByRole("button", { name: new RegExp(firstBaseName) }).click();
  await expect(page.getByRole("heading", { name: firstBaseName })).toBeVisible();

  const markdown = "KnowFlow 合成验收资料。\n索引状态只有 READY 时才会参与问答。\n上传文件大小上限为 8 MiB。\n";
  const markdownName = "流程规则.md";
  const uploadResponse = page.waitForResponse((response) => response.url().includes("/documents") && response.request().method() === "POST");
  await page.locator('input[type="file"]').first().setInputFiles({ name: markdownName, mimeType: "text/markdown", buffer: Buffer.from(markdown) });
  const uploaded = await (await uploadResponse).json();
  const markdownCard = page.getByRole("article").filter({ hasText: markdownName });
  await expect(markdownCard).toContainText("已就绪", { timeout: 90_000 });

  const streamResponse = page.waitForResponse((response) => response.url().includes("/questions/stream"));
  await page.getByRole("button", { name: "首页", exact: true }).click();
  await page.getByRole("button", { name: "总结最新的产品功能" }).click();
  const homeQuestion = page.getByRole("textbox", { name: "向知识库提问" });
  await expect(homeQuestion).toHaveValue("总结最新的产品功能");
  await homeQuestion.fill("什么时候允许使用这份资料进行问答？");
  await page.getByRole("button", { name: "提问" }).click();
  const firstStream = await streamResponse;
  const streamEvents = parseSseEvents(await capturedStream(page, "什么时候允许使用这份资料进行问答？"));
  expect(firstStream.headers()["x-request-id"]).toBe(streamEvents[0].data.request_id);
  expect(streamEvents[0].name).toBe("started");
  expect(streamEvents.some(({ name }) => name === "delta")).toBeTruthy();
  expect(streamEvents.at(-1)?.name).toBe("completed");
  const requestId = streamEvents[0].data.request_id;
  streamEvents.forEach(({ name, data }, index) => {
    expect(data).toMatchObject({ contract_version: "0.2.0-draft.10", request_id: requestId, sequence: index + 1, event: name });
  });
  const sourceEvent = streamEvents.find(({ name }) => name === "sources");
  expect(sourceEvent).toBeTruthy();
  const source = sourceEvent!.data.sources[0] as { source_id: string; document_id: string; content_version_id: string };
  await expect(page.getByText("本地合成验证", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: /什么时候允许使用这份资料进行问答/ })).toBeVisible();
  const citationButton = page.getByRole("button").filter({ hasText: "索引状态只有 READY" }).first();
  await citationButton.click();
  const textDialog = page.getByRole("dialog", { name: "原文依据" });
  await expect(textDialog.locator("pre")).toContainText("索引状态只有 READY");
  await expect(textDialog.locator("pre")).toContainText(markdown.trim());
  const closeSource = page.getByRole("button", { name: "关闭原文" });
  await expect(closeSource).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(closeSource).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(textDialog).toHaveCount(0);
  await expect(citationButton).toBeFocused();

  const failureCaptures: Record<string, ReturnType<typeof parseSseEvents>> = {};
  for (const [mode, status, label] of [["error", "FAILED", "处理失败"], ["cancelled", "CANCELLED", "已取消"], ["timeout", "FAILED", "处理失败"]] as const) {
    const question = `[e2e:${mode}] 流中终止验收`;
    const response = page.waitForResponse((item) => item.url().includes("/questions/stream"));
    await page.getByPlaceholder("例如：这个接口有哪些必填字段？").fill(question);
    await page.getByRole("button", { name: "提问" }).click();
    const wire = await response;
    const frames = parseSseEvents(await capturedStream(page, question));
    expectStream(frames, mode === "timeout" ? "error" : mode);
    expect(wire.headers()["x-request-id"]).toBe(frames[0].data.request_id);
    if (mode === "timeout") expect(frames.at(-1)?.data).toMatchObject({ code: "PROCESSING_TIMEOUT", retryable: true });
    expect(frames.some(({ name }) => name === "sources")).toBeFalsy();
    failureCaptures[mode] = frames;
    await expect(page.getByText(`此问答状态：${label}。可在历史记录中查看。`)).toBeVisible();
    await expectUnfinishedHistory(page, question, status, mode === "timeout" ? "PROCESSING_TIMEOUT" : "AI_PROCESSING_FAILED");
    await expect(page.getByRole("button", { name: new RegExp(question.replace(/[\[\]]/g, "\\$&")) })).toContainText(label);
  }

  const refusalQuestion = "[e2e:refusal] 证据不足验收";
  const refusalResponse = page.waitForResponse((item) => item.url().includes("/questions/stream"));
  await page.getByPlaceholder("例如：这个接口有哪些必填字段？").fill(refusalQuestion);
  await page.getByRole("button", { name: "提问" }).click();
  const refusalWire = await refusalResponse;
  const refusalFrames = parseSseEvents(await capturedStream(page, refusalQuestion));
  expectStream(refusalFrames, "completed");
  expect(refusalWire.headers()["x-request-id"]).toBe(refusalFrames[0].data.request_id);
  expect(refusalFrames.find(({ name }) => name === "sources")?.data).toMatchObject({ has_answer: false, sources: [] });
  failureCaptures.refusal = refusalFrames;
  await expect(page.getByText("没有足够的资料证据回答这个问题。", { exact: true })).toBeVisible();
  await expect(page.getByText("合成拒答草稿不得显示")).toHaveCount(0);
  await expect.poll(async () => page.evaluate(async (question) => {
    const list = await (await fetch("/api/v1/questions?limit=100")).json();
    const item = list.items.find((row: { question: string }) => row.question === question);
    return item ? (await fetch(`/api/v1/questions/${item.question_id}`)).json() : null;
  }, refusalQuestion)).toMatchObject({ status: "SUCCEEDED", has_answer: false, sources: [],
    answer: "没有足够的资料证据回答这个问题。", failure_code: null });

  const conflictId = `browser-conflict-${randomUUID()}`;
  const conflict = await page.evaluate(async ({ base, key, requestId }) => {
    const response = await fetch(`/api/v1/knowledge-bases/${base}/questions/stream`, {
      method: "POST", headers: { "content-type": "application/json", "idempotency-key": key, "x-request-id": requestId },
      body: JSON.stringify({ question: "重复付费请求不得重发" }),
    });
    return { requestId: response.headers.get("x-request-id"), body: await response.text() };
  }, { base: firstKnowledgeBase, key: firstStream.request().headers()["idempotency-key"], requestId: conflictId });
  const conflictFrames = parseSseEvents(conflict.body);
  expect(conflict.requestId).toBe(conflictId);
  expect(conflictFrames).toHaveLength(1);
  expect(conflictFrames[0]).toMatchObject({ name: "error", data: { sequence: 1, request_id: conflictId, code: "QUESTION_REQUEST_CONFLICT" } });

  const slowQuestion = "[e2e:slow] 主动停止验收";
  let slowRequests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/questions/stream") && request.postDataJSON()?.question === slowQuestion) slowRequests++;
  });
  await page.getByPlaceholder("例如：这个接口有哪些必填字段？").fill(slowQuestion);
  await page.getByRole("button", { name: "提问" }).click();
  await expect(page.getByText("合成中断片段", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "停止生成" }).click();
  await expect(page.getByText("此问答状态：已取消。可在历史记录中查看。")).toBeVisible();
  const stopped = await expectUnfinishedHistory(page, slowQuestion, "CANCELLED");
  // The synthetic model would finish in four seconds if the abort were lost.
  await expect.poll(async () => {
    const detail = await page.evaluate(async (id) => (await fetch(`/api/v1/questions/${id}`)).json(), stopped.question_id);
    expect(detail).toMatchObject({ status: "CANCELLED", answer: null, has_answer: null, sources: [] });
    return Date.now() - Date.parse(stopped.finished_at) >= 4500;
  }, { timeout: 10_000 }).toBe(true);
  expect(slowRequests).toBe(1);
  await page.getByRole("button", { name: /主动停止验收/ }).click();
  await expect(page.getByText("此问答状态：已取消。可在历史记录中查看。")).toBeVisible();

  const secondContext = await browser.newContext();
  const secondPage = await secondContext.newPage();
  const secondEmail = `other-${randomUUID()}@example.test`;
  await secondPage.goto("/");
  await secondPage.getByRole("button", { name: "Create an account" }).click();
  await secondPage.getByLabel("Email").fill(secondEmail);
  await secondPage.getByLabel("Password", { exact: true }).fill(password);
  await secondPage.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(secondPage.getByText("这里还没有知识库。")).toBeVisible();
  const sourceStatus = await secondPage.evaluate((id) => fetch(`/api/v1/sources/${id}`).then((response) => response.status), source.source_id);
  const fileStatus = await secondPage.evaluate(({ documentId, versionId }) => fetch(`/api/v1/documents/${documentId}/contents/${versionId}/file`).then((response) => response.status), { documentId: source.document_id, versionId: source.content_version_id });
  expect(sourceStatus).toBe(404);
  expect(fileStatus).toBe(404);
  await secondContext.close();

  page.once("dialog", (dialog) => dialog.accept());
  await markdownCard.getByRole("button", { name: `${markdownName} 操作` }).click();
  await page.getByRole("menuitem", { name: "删除资料" }).click();
  await expect(markdownCard).toHaveCount(0);
  const deletedSourceStatus = await page.evaluate((id) => fetch(`/api/v1/sources/${id}`).then((response) => response.status), source.source_id);
  expect(deletedSourceStatus).toBe(404);

  const pdfBytes = await readFile(resolve(process.cwd(), "../../services/ai/tests/fixtures/pdf/chinese-pages.pdf"));
  const pdfName = "合成中文原文.pdf";
  const pdfUpload = page.waitForResponse((response) => response.url().includes("/documents") && response.request().method() === "POST");
  await page.locator('input[type="file"]').first().setInputFiles({ name: pdfName, mimeType: "application/pdf", buffer: pdfBytes });
  await pdfUpload;
  const pdfCard = page.getByRole("article").filter({ hasText: pdfName });
  await expect(pdfCard).toContainText("已就绪", { timeout: 90_000 });
  await expect(pdfCard).toContainText("PDF");
  const pdfStream = page.waitForResponse((response) => response.url().includes("/questions/stream"));
  await page.getByPlaceholder("例如：这个接口有哪些必填字段？").fill("请根据 PDF 原文给出引用依据。");
  await page.getByRole("button", { name: "提问" }).click();
  const pdfWire = await pdfStream;
  const pdfBody = await capturedStream(page, "请根据 PDF 原文给出引用依据。");
  expect(pdfBody).toMatch(/event:[ \t]*completed/);
  const pdfEvents = parseSseEvents(pdfBody);
  expect(pdfWire.headers()["x-request-id"]).toBe(pdfEvents[0].data.request_id);
  const pdfSource = (pdfEvents.find(({ name }) => name === "sources")!.data.sources[0]) as { document_id: string; content_version_id: string; locator: { page: number } };
  expect(pdfSource.document_id).toBeTruthy();
  expect(pdfSource.content_version_id).toBeTruthy();
  expect([1, 3]).toContain(pdfSource.locator.page);
  await page.getByRole("button").filter({ hasText: pdfName }).filter({ hasText: `第 ${pdfSource.locator.page} 页` }).first().click();
  await expect(page.getByRole("dialog", { name: "原文依据" }).locator("iframe")).toHaveAttribute("src", new RegExp(`#page=${pdfSource.locator.page}$`));
  expect(uploaded.document_id).toBe(source.document_id);

  await page.reload();
  await expect(page.getByRole("heading", { name: "KnowFlow", exact: true })).toBeVisible();
  await page.getByLabel("账户菜单").click();
  await page.getByRole("button", { name: "退出", exact: true }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password + "-wrong");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "KnowFlow", exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toHaveCount(0);
  const capturePath = process.env.KNOWFLOW_E2E_STREAM_CAPTURE;
  if (!capturePath) throw new Error("KNOWFLOW_E2E_STREAM_CAPTURE is required");
  await writeFile(capturePath, JSON.stringify({ text: streamEvents, pdf: pdfEvents, ...failureCaptures }, null, 2), "utf8");
});
