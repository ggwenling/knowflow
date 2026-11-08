import { expect, test } from "@playwright/test";

test("failed session lookup can be retried and a later 401 clears the workspace", async ({ page }) => {
  let mode = "offline";
  await page.route("**/api/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (mode === "offline") return route.fulfill({ status: 503, json: {} });
    if (pathname.endsWith("/me")) return route.fulfill({ json: { user_id: "test", email: "session@example.test" } });
    if (mode === "expired") return route.fulfill({ status: 401, json: {} });
    if (pathname.endsWith("/knowledge-bases")) return route.fulfill({
      json: { items: [{ id: "fixture", name: "会话测试知识库", status: "ACTIVE" }] },
    });
    return route.fulfill({ json: { items: [], has_more: false } });
  });
  await page.goto("/");
  await expect(page.getByText("服务暂时不可用，请稍后重试。")).toBeVisible();
  mode = "online";
  await page.getByRole("button", { name: "重试连接" }).click();
  await expect(page.getByRole("link", { name: "会话测试知识库", exact: true })).toBeVisible();
  mode = "expired";
  await page.getByRole("link", { name: "会话测试知识库", exact: true }).click();
  await page.waitForURL("**/login");
  await expect(page.getByLabel("Email", { exact: true })).toBeVisible();
  await expect(page.getByText("会话测试知识库")).toHaveCount(0);
});
