import { expect, test, type Page } from "@playwright/test";

async function mockWorkspace(page: Page) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/mode") return route.fulfill({ json: { mode: "synthetic" } });
    if (path === "/api/v1/me") return route.fulfill({ json: { user_id: "responsive", email: "responsive@example.test" } });
    if (path === "/api/v1/knowledge-bases") {
      return route.fulfill({ json: { items: [{ id: "base-1", name: "响应式资料库", status: "ACTIVE", updated_at: new Date().toISOString() }], has_more: false } });
    }
    if (path.endsWith("/documents")) {
      return route.fulfill({ json: { items: [{ id: "doc-1", original_name: "规则.md", status: "READY", active_index_version_id: "idx-1", format: "MD", byte_size: 1024 }], has_more: false } });
    }
    if (path === "/api/v1/questions") return route.fulfill({ json: { items: [], has_more: false } });
    return route.fulfill({ json: { items: [], has_more: false } });
  });
}

for (const width of [390, 768, 1440]) {
  test(`home has no horizontal overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await mockWorkspace(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "KnowFlow", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(page.getByRole("link", { name: "首页", exact: true })).toBeVisible();
  });
}

test("mobile chat exposes history and documents as accessible drawers", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockWorkspace(page);
  await page.goto("/conversations");
  await expect(page.getByRole("heading", { name: "对话", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await page.getByRole("button", { name: "历史记录", exact: true }).click();
  const historyDialog = page.getByRole("dialog", { name: "对话历史" });
  await expect(historyDialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(historyDialog).toHaveCount(0);

  await page.getByRole("button", { name: "资料", exact: true }).click();
  const docsDialog = page.getByRole("dialog", { name: "资料" });
  await expect(docsDialog).toBeVisible();
  await expect(docsDialog.getByText("规则.md")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(docsDialog).toHaveCount(0);
});

test("desktop chat keeps the three-column rail and documents panel", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockWorkspace(page);
  await page.goto("/conversations");
  await expect(page.getByRole("heading", { name: "对话历史", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^资料/ })).toBeVisible();
  await expect(page.getByText("规则.md")).toBeVisible();
});
