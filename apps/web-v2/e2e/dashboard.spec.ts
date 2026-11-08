import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const bases = [
  { id: "product", name: "产品文档库", status: "ACTIVE", updated_at: new Date(Date.now() - 3 * 3600000).toISOString() },
  { id: "dev", name: "研发知识库", status: "ACTIVE", updated_at: new Date(Date.now() - 86400000).toISOString() },
  { id: "research", name: "行业研究库", status: "ACTIVE", updated_at: new Date(Date.now() - 2 * 86400000).toISOString() },
];
const history = ["RAG 的核心原理是什么？", "如何在 KnowFlow 中构建知识库？", "多模型在 RAG 场景下的选择建议"].map((question, index) => ({
  question_id: `q${index}`, knowledge_base_id: "product", question, status: "SUCCEEDED",
  finished_at: new Date(Date.now() - [10 * 60000, 42 * 60000, 86400000][index]).toISOString(),
}));

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/mode") return route.fulfill({ json: { mode: "synthetic" } });
    if (path === "/api/v1/me") return route.fulfill({ json: { user_id: "preview", email: "knowflow@example.test" } });
    if (path === "/api/v1/knowledge-bases") return route.fulfill({ json: { items: bases, has_more: false } });
    if (path.endsWith("/documents")) return route.fulfill({ json: { items: [{ id: "doc", original_name: "产品指南.md", status: "READY", active_index_version_id: "index-1", format: "MD", byte_size: 512 }], has_more: false } });
    if (path === "/api/v1/questions") return route.fulfill({ json: { items: history, has_more: false } });
    return route.fulfill({ status: 404, json: {} });
  });
});

test("home renders a live WebGL wave and keeps dashboard actions usable", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1672, height: 941 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "我的知识库" })).toBeVisible();
  const canvas = page.locator(".home-wave canvas");
  await expect(canvas).toBeVisible();
  // Capture inside the animation frame, before WebGL's default buffer is cleared.
  const readFrame = () => canvas.evaluate((element: HTMLCanvasElement) => new Promise<string>((done) => {
    requestAnimationFrame(() => done(element.toDataURL()));
  }));
  const first = await readFrame();
  await expect.poll(readFrame).not.toBe(first);
  await expect(page.getByRole("button", { name: "提问", exact: true })).toBeDisabled();
  await page.getByRole("textbox", { name: "向知识库提问" }).fill("RAG 的核心原理是什么？");
  await expect(page.getByRole("button", { name: "提问", exact: true })).toBeEnabled();
  await page.getByRole("textbox", { name: "向知识库提问" }).fill("");
  await page.getByRole("textbox", { name: "向知识库提问" }).blur();
  await mkdir(resolve("../../eval-out/homepage"), { recursive: true });
  await page.screenshot({ path: resolve("../../eval-out/homepage/desktop.png") });
  await page.getByRole("link", { name: "创建工作流", exact: true }).click();
  await expect(page).toHaveURL(/\/workflow$/);
  await expect(page.getByText("工作流功能暂未开放")).toBeVisible();
  await page.getByRole("link", { name: "设置", exact: true }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole("definition").filter({ hasText: "knowflow@example.test" })).toBeVisible();
  await page.getByRole("link", { name: "首页", exact: true }).click();
  await page.getByRole("link", { name: "上传文档", exact: true }).click();
  await expect(page).toHaveURL(/\/knowledge-bases\/product$/);
  expect(errors).toEqual([]);
});

test("mobile fits the viewport and reduced motion freezes the WebGL wave", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "我的知识库" })).toBeVisible();
  const canvas = page.locator(".home-wave canvas");
  await expect(canvas).toBeVisible();
  // Screenshots force a composited frame even when the render loop is paused.
  const first = await canvas.screenshot();
  const second = await canvas.screenshot();
  expect(first.equals(second)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await mkdir(resolve("../../eval-out/homepage"), { recursive: true });
  await page.screenshot({ path: resolve("../../eval-out/homepage/mobile.png"), fullPage: true });
  await page.getByRole("link", { name: "创建知识库", exact: true }).click();
  await expect(page).toHaveURL(/\/knowledge-bases\?create=1$/);
  await expect(page.getByLabel("新知识库名称")).toBeFocused();
});
