import { expect, test } from "@playwright/test";

test("desktop history scrolls to pagination while account controls stay accessible", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown;
    if (path === "/api/mode") body = { mode: "synthetic" };
    else if (path === "/api/v1/me") body = { user_id: "layout-user", email: "layout@example.test" };
    else if (path === "/api/v1/llm-models") body = { enabled: false, models: [] };
    else if (path === "/api/v1/knowledge-bases") body = { items: [{ id: "layout-base", name: "布局资料库", status: "ACTIVE" }] };
    else if (path.endsWith("/documents")) body = { items: [] };
    else if (path === "/api/v1/questions") body = {
      items: Array.from({ length: 50 }, (_, index) => ({
        question_id: `layout-${index}`, knowledge_base_id: "layout-base", question: `历史问题 ${index + 1}`,
        status: "SUCCEEDED", finished_at: "2026-11-03T00:00:00Z",
      })), has_more: true,
    };
    else throw new Error(`Unexpected layout API: ${path}`);
    await route.fulfill({ json: body });
  });
  await page.goto("/");
  await page.getByRole("link", { name: "对话", exact: true }).click();
  const oldest = page.getByRole("link", { name: /^历史问题 50/ });
  await expect(oldest).toBeAttached();
  const history = oldest.locator("..");
  await expect.poll(() => history.evaluate((element) => {
    const style = getComputedStyle(element);
    return ["auto", "scroll"].includes(style.overflowY) && element.scrollHeight > element.clientHeight;
  })).toBe(true);
  const logout = page.getByRole("button", { name: "退出", exact: true });
  await expect(logout).toBeInViewport();
  await history.evaluate((element) => { element.scrollTop = element.scrollHeight; });
  await expect(oldest).toBeInViewport();
  await expect(page.getByRole("button", { name: "加载更多问答" })).toBeInViewport();
  await expect(logout).toBeInViewport();
  await page.getByRole("link", { name: /^历史问题 1\s/ }).focus();
  await expect(page.getByRole("link", { name: /^历史问题 1\s/ })).toBeInViewport();
  await expect(logout).toBeInViewport();
});
