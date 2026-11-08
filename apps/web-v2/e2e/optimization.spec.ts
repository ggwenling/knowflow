import { expect, test } from "@playwright/test";
import { base, document, mockWorkspace, question } from "./helpers/workspace";

test("question failures expose the specific error and recovery state", async ({ page }) => {
  await mockWorkspace(page, async (route, url) => {
    if (!url.pathname.endsWith("/questions/stream")) return false;
    await route.fulfill({ status: 503, json: { message: "模型暂不可用，请稍后重试。" } });
    return true;
  });
  await page.goto("/conversations");
  await page.getByRole("textbox", { name: "问题", exact: true }).fill("一个问题");
  await page.getByRole("button", { name: "提问", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "模型暂不可用，请稍后重试。" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重试提问" })).toBeVisible();
});

test("upload is keyboard accessible and rejects unsupported files consistently", async ({ page }) => {
  let uploads = 0;
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname.endsWith("/documents") && route.request().method() === "POST") uploads++;
    return false;
  });
  await page.goto(`/knowledge-bases/${base.id}`);
  const picker = page.getByRole("button", { name: "选择文件", exact: true }).first();
  await picker.focus();
  const chooser = page.waitForEvent("filechooser");
  await page.keyboard.press("Enter");
  await (await chooser).setFiles({ name: "unsupported.exe", mimeType: "application/octet-stream", buffer: Buffer.from("invalid") });
  await expect(page.getByRole("status").filter({ hasText: "不支持此文件格式" })).toBeVisible();
  expect(uploads).toBe(0);
});

test("accepted upload releases controls and failed indexing never claims indexing success", async ({ page }) => {
  let accepted = false;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const failed = { ...document, id: "doc-failed", original_name: "failed.txt", status: "FAILED", latest_task_id: "task-failed", latest_task_status: "FAILED" };
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname.endsWith("/documents") && route.request().method() === "POST") { accepted = true; await route.fulfill({ status: 202, json: { document_id: failed.id, task_id: failed.latest_task_id } }); return true; }
    if (url.pathname === `/api/v1/documents/${failed.id}`) { await route.fulfill({ json: failed }); return true; }
    if (url.pathname === `/api/v1/tasks/${failed.latest_task_id}`) { await gate; await route.fulfill({ json: { task_id: failed.latest_task_id, status: "FAILED", failure_code: "INDEX_FAILED" } }); return true; }
    if (accepted && url.pathname.endsWith("/documents")) { await route.fulfill({ json: { items: [document, failed], has_more: false } }); return true; }
    return false;
  });
  await page.goto(`/knowledge-bases/${base.id}`);
  await page.locator('input[type="file"]').first().setInputFiles({ name: "failed.txt", mimeType: "text/plain", buffer: Buffer.from("content") });
  await expect(page.getByRole("button", { name: "选择文件", exact: true }).first()).toBeEnabled();
  await expect(page.getByText("文件已接受，索引状态见资料列表", { exact: true })).toBeVisible();
  release();
  await expect(page.getByRole("status").filter({ hasText: "INDEX_FAILED" })).toBeVisible();
  await expect(page.getByRole("article").filter({ hasText: "failed.txt" })).toContainText("处理失败");
  await expect(page.getByText("已上传，正在建立索引", { exact: true })).toHaveCount(0);
});

test("document menu supports keyboard navigation, Escape and focus restoration", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto(`/knowledge-bases/${base.id}`);
  const trigger = page.getByRole("button", { name: `${document.original_name} 操作`, exact: true });
  await trigger.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "更新资料" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "重建索引" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(trigger).toBeFocused();
  // A cold keyboard Enter must also restore the first item after async loading.
  await page.reload();
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitem", { name: "更新资料" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});

test("sidebar pagination actually reveals the newly fetched history", async ({ page }) => {
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname !== "/api/v1/questions") return false;
    const offset = Number(url.searchParams.get("offset"));
    await route.fulfill({ json: { items: Array.from({ length: offset ? 10 : 50 }, (_, i) => question(offset + i)), has_more: !offset } });
    return true;
  });
  await page.goto("/");
  await page.getByRole("button", { name: "加载更多问答", exact: true }).click();
  await expect(page.locator('aside a[href="/conversations/q-50"]')).toBeVisible();
});

test("history search keeps pagination reachable for older matching records", async ({ page }) => {
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname !== "/api/v1/questions") return false;
    const offset = Number(url.searchParams.get("offset"));
    await route.fulfill({ json: { items: offset ? [{ ...question(50), question: "独特的旧问题" }] : [question(0)], has_more: !offset } });
    return true;
  });
  await page.goto("/conversations");
  await page.getByRole("textbox", { name: "搜索对话历史" }).fill("独特的旧问题");
  await page.getByRole("button", { name: "加载更多问答", exact: true }).click();
  await expect(page.getByRole("link", { name: /独特的旧问题/ })).toBeVisible();
});

test("status text meets normal-text contrast while status dots retain the palette", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto(`/knowledge-bases/${base.id}`);
  const status = page.getByText("已就绪", { exact: true }).last();
  await expect(status).toBeVisible();
  const contrast = await status.evaluate((element) => {
    const rgb = getComputedStyle(element).color.match(/\d+/g)!.map(Number).map((v) => v / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
    return 1.05 / (rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722 + .05);
  });
  expect(contrast).toBeGreaterThanOrEqual(4.5);
});
