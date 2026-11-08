import { expect, test, type Page } from "@playwright/test";

async function mockWorkspace(page: Page) {
  const base = { id: "base-1", name: "流程资料库", status: "ACTIVE", updated_at: new Date().toISOString() };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/mode") return route.fulfill({ json: { mode: "synthetic" } });
    if (path === "/api/v1/me") return route.fulfill({ json: { user_id: "a11y", email: "a11y@example.test" } });
    if (path === "/api/v1/knowledge-bases") return route.fulfill({ json: { items: [base], has_more: false } });
    if (path === "/api/v1/knowledge-bases/base-1") return route.fulfill({ json: base });
    if (path.endsWith("/documents")) {
      return route.fulfill({ json: {
        items: [
          { id: "doc-1", original_name: "流程规则.md", status: "READY", active_index_version_id: "idx-1", format: "MD", byte_size: 2048 },
          { id: "doc-2", original_name: "发布清单.pdf", status: "QUEUED", format: "PDF", byte_size: 4096 },
        ],
        has_more: false,
      } });
    }
    if (path === "/api/v1/questions") {
      return route.fulfill({ json: {
        items: [
          { question_id: "q1", knowledge_base_id: "base-1", question: "什么时候允许问答？", status: "SUCCEEDED", finished_at: new Date().toISOString() },
        ],
        has_more: false,
      } });
    }
    return route.fulfill({ json: { items: [], has_more: false } });
  });
}

test("skip link reaches the main landmark and primary navigation uses links", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockWorkspace(page);
  await page.goto("/");
  await expect(page.getByRole("main")).toBeVisible();

  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "跳到主要内容" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

  const nav = page.getByRole("navigation", { name: "主导航" });
  await expect(nav.getByRole("link", { name: "首页" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "对话" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "知识库" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "工作流" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "设置" })).toBeVisible();
});

test("inputs expose a visible focus ring", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockWorkspace(page);
  await page.goto("/knowledge-bases");
  const search = page.getByRole("textbox", { name: "搜索知识库" });
  await search.focus();
  await expect(search).toHaveCSS("outline-style", "solid");

  await page.goto("/conversations");
  const composer = page.getByRole("textbox", { name: "问题" });
  await expect(composer).toBeEnabled();
  await composer.focus();
  await expect(composer).toHaveCSS("outline-style", "solid");
});

test("search and filter state survive reload through the URL", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockWorkspace(page);

  await page.goto("/knowledge-bases");
  const search = page.getByRole("textbox", { name: "搜索知识库" });
  await search.fill("流程");
  await expect.poll(() => new URL(page.url()).searchParams.get("q")).toBe("流程");
  await page.reload();
  await expect(page.getByRole("textbox", { name: "搜索知识库" })).toHaveValue("流程");

  await page.goto("/knowledge-bases/base-1");
  const ready = page.getByRole("button", { name: /^已就绪/ });
  await ready.click();
  await expect.poll(() => new URL(page.url()).searchParams.get("status")).toBe("ready");
  await page.reload();
  await expect(page.getByRole("button", { name: /^已就绪/ })).toHaveAttribute("aria-pressed", "true");

  await page.goto("/conversations");
  const history = page.getByRole("textbox", { name: "搜索对话历史" });
  await history.fill("规则");
  await expect.poll(() => new URL(page.url()).searchParams.get("history")).toBe("规则");
  await page.reload();
  await expect(page.getByRole("textbox", { name: "搜索对话历史" })).toHaveValue("规则");
});
