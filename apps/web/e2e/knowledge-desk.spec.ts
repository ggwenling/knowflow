import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

let firstPage: Page | undefined;
let firstKnowledgeBase = "";
let secondKnowledgeBase = "";

function parseSseEvents(body: string) {
  return body.split(/\r?\n\r?\n/).filter((frame) => frame.includes("data:")).map((frame) => {
    const lines = frame.split(/\r?\n/);
    return {
      name: lines.find((line) => line.startsWith("event:"))?.slice(6).trim(),
      data: JSON.parse(lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n")),
    };
  });
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
  await page.setViewportSize({ width: 390, height: 844 });
  const email = `web-${randomUUID()}@example.test`;
  const password = "KnowFlow-e2e-only-2026!";
  await page.goto("/");
  await page.getByRole("button", { name: "还没有账户？创建账户" }).click();
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "创建账户" }).click();

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
  await page.getByPlaceholder("例如：这个接口有哪些必填字段？").fill("什么时候允许使用这份资料进行问答？");
  await page.getByRole("button", { name: "提问" }).click();
  const streamEvents = parseSseEvents(await (await streamResponse).text());
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

  const secondContext = await browser.newContext();
  const secondPage = await secondContext.newPage();
  const secondEmail = `other-${randomUUID()}@example.test`;
  await secondPage.goto("/");
  await secondPage.getByRole("button", { name: "还没有账户？创建账户" }).click();
  await secondPage.getByLabel("邮箱").fill(secondEmail);
  await secondPage.getByLabel("密码").fill(password);
  await secondPage.getByRole("button", { name: "创建账户" }).click();
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
  const pdfBody = await (await pdfStream).text();
  expect(pdfBody).toMatch(/event:[ \t]*completed/);
  const pdfEvents = parseSseEvents(pdfBody);
  const pdfSource = (pdfEvents.find(({ name }) => name === "sources")!.data.sources[0]) as { document_id: string; content_version_id: string; locator: { page: number } };
  expect(pdfSource.document_id).toBeTruthy();
  expect(pdfSource.content_version_id).toBeTruthy();
  expect([1, 3]).toContain(pdfSource.locator.page);
  await page.getByRole("button").filter({ hasText: pdfName }).filter({ hasText: `第 ${pdfSource.locator.page} 页` }).first().click();
  await expect(page.getByRole("dialog", { name: "原文依据" }).locator("iframe")).toHaveAttribute("src", new RegExp(`#page=${pdfSource.locator.page}$`));
  expect(uploaded.document_id).toBe(source.document_id);
  const capturePath = process.env.KNOWFLOW_E2E_STREAM_CAPTURE;
  if (!capturePath) throw new Error("KNOWFLOW_E2E_STREAM_CAPTURE is required");
  await writeFile(capturePath, JSON.stringify({ text: streamEvents, pdf: pdfEvents }, null, 2), "utf8");
});
