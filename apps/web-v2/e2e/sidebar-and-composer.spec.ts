import { expect, test } from "@playwright/test";
import { base, mockWorkspace } from "./helpers/workspace";
import { beginRenderProbe, endRenderProbe, installRenderProbe } from "./helpers/render-probe";

const preferenceKey = "knowflow.sidebar.collapsed";
const sidebar = (page: import("@playwright/test").Page) => page.locator("#workspace-sidebar");

for (const width of [1440, 900]) {
  test(`sidebar collapses to an accessible rail and persists at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const hydrationErrors: string[] = [];
    page.on("console", (message) => { if (message.type() === "error" && /hydration|hydrating|didn.t match|server rendered/i.test(message.text())) hydrationErrors.push(message.text()); });
    await mockWorkspace(page);
    await page.goto("/");
    const mainColumn = page.locator("#main-content").locator("..");
    const toggle = page.getByRole("button", { name: "收起侧栏", exact: true });
    await expect(toggle).toHaveAttribute("aria-controls", "workspace-sidebar");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    const mainBefore = await mainColumn.boundingBox();
    await toggle.click();
    await expect(page.getByRole("button", { name: "展开侧栏", exact: true })).toHaveAttribute("aria-expanded", "false");
    await expect.poll(() => sidebar(page).evaluate((node) => node.getBoundingClientRect().width)).toBeCloseTo(64, 0);
    await expect.poll(async () => (await mainColumn.boundingBox())!.width).toBeGreaterThan(mainBefore!.width + 100);

    const navLink = page.getByRole("navigation", { name: "主导航" }).getByRole("link", { name: "知识库", exact: true });
    await navLink.hover();
    await expect(page.getByRole("tooltip", { name: "知识库", exact: true })).toBeVisible();
    await page.getByRole("tooltip", { name: "知识库", exact: true }).hover();
    await expect(page.getByRole("tooltip", { name: "知识库", exact: true })).toBeVisible();
    await page.mouse.move(width - 20, 400);
    await navLink.focus();
    await expect(page.getByRole("tooltip", { name: "知识库", exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("tooltip", { name: "知识库", exact: true })).toHaveCount(0);

    await expect.poll(() => page.evaluate((key) => localStorage.getItem(key), preferenceKey)).toBe("true");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-sidebar-collapsed", "true");
    await expect(sidebar(page)).toBeVisible();
    await expect.poll(() => sidebar(page).evaluate((node) => node.getBoundingClientRect().width)).toBeCloseTo(64, 0);
    await expect(page.getByRole("button", { name: "展开侧栏", exact: true })).toHaveAttribute("aria-expanded", "false");
    expect(hydrationErrors).toEqual([]);

    await page.keyboard.press("Control+b");
    await expect(page.getByRole("button", { name: "收起侧栏", exact: true })).toHaveAttribute("aria-expanded", "true");
    await expect.poll(() => sidebar(page).evaluate((node) => node.getBoundingClientRect().width)).toBeGreaterThan(200);
    await page.keyboard.press("Meta+b");
    await expect(page.getByRole("button", { name: "展开侧栏", exact: true })).toHaveAttribute("aria-expanded", "false");
    await page.keyboard.press("Meta+b");
    await expect(page.getByRole("button", { name: "收起侧栏", exact: true })).toHaveAttribute("aria-expanded", "true");
  });
}

test("collapsed preference is applied before content mounts; account menu and create still work", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript((key) => localStorage.setItem(key, "true"), preferenceKey);
  await mockWorkspace(page);
  await page.goto("/knowledge-bases");
  await expect(page.locator("html")).toHaveAttribute("data-sidebar-collapsed", "true");
  await expect.poll(() => sidebar(page).evaluate((node) => node.getBoundingClientRect().width)).toBeCloseTo(64, 0);
  const account = page.getByLabel("账户菜单", { exact: true });
  await account.focus();
  await expect(page.getByRole("tooltip", { name: "optimization@example.test", exact: true })).toBeVisible();
  await account.click();
  await expect(page.getByRole("link", { name: /账户设置/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "新建知识库", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "新知识库名称" })).toBeFocused();
  await expect(page.getByRole("button", { name: "收起侧栏", exact: true })).toBeVisible();
});

test("mobile ignores the desktop rail preference and exposes the existing account menu", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript((key) => localStorage.setItem(key, "true"), preferenceKey);
  await mockWorkspace(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "KnowFlow", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /收起侧栏|展开侧栏/ })).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "主导航" }).getByRole("link", { name: "知识库", exact: true })).toBeVisible();
  await expect.poll(() => sidebar(page).evaluate((node) => node.getBoundingClientRect().width)).toBeCloseTo(390, 0);
  await page.keyboard.press("Control+b");
  await expect(page.locator("html")).toHaveAttribute("data-sidebar-collapsed", "true");
  await page.getByLabel("账户菜单", { exact: true }).click();
  await expect(page.getByRole("link", { name: /账户设置/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

for (const width of [390, 1440]) {
  test(`home and conversation use only their outer focus ring at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockWorkspace(page);
    await page.goto("/");
    const input = page.getByRole("textbox", { name: "向知识库提问", exact: true });
    await input.focus();
    const frame = input.locator('xpath=ancestor::*[@data-composite-field][1]');
    await expect(input).toHaveCSS("border-width", "0px");
    await expect(input).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(input).toHaveCSS("outline-style", "none");
    await expect(input).toHaveCSS("box-shadow", "none");
    await expect(frame).toHaveCSS("outline-style", "solid");
    await expect(frame).toHaveCSS("outline-width", "2px");
    await expect(frame.locator("kbd")).toHaveCount(0);
    await expect(frame.getByText("↵", { exact: true })).toHaveCount(0);
    await expect(frame.getByRole("button", { name: "提问", exact: true })).toBeVisible();

    await page.goto("/conversations");
    const composer = page.getByRole("textbox", { name: "问题", exact: true });
    await expect(composer).toBeEnabled();
    await composer.focus();
    await expect(composer).toHaveCSS("outline-style", "none");
    await expect(composer).toHaveCSS("border-width", "0px");
    await expect(composer.locator('xpath=ancestor::*[@data-composite-field][1]')).toHaveCSS("outline-width", "2px");
    if (width === 1440) {
      const hint = page.locator("form kbd").first();
      await expect(hint).toHaveCSS("border-top-width", "0px");
      await expect(hint).toHaveCSS("box-shadow", "none");
    }
  });
}

test("sidebar toggle does not render home or composer, and create reveals a collapsed sidebar", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installRenderProbe(page);
  await mockWorkspace(page);
  await page.goto("/");
  await expect(page.getByRole("textbox", { name: "向知识库提问" })).toBeVisible();
  await expect(page.getByText("1 个文档", { exact: true })).toBeVisible();
  await beginRenderProbe(page);
  await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
  await expect(page.getByRole("button", { name: "展开侧栏", exact: true })).toBeVisible();
  const counts = await endRenderProbe(page);
  expect(counts.shell ?? 0).toBe(0);
  expect(counts.home ?? 0).toBe(0);
  expect(counts.composer ?? 0).toBe(0);
  await page.getByRole("link", { name: "创建知识库", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "新知识库名称" })).toBeFocused();
  await expect(page.getByRole("button", { name: "收起侧栏", exact: true })).toBeVisible();
});

test("conversation retains its three columns after collapsing the sidebar", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockWorkspace(page);
  await page.goto("/conversations");
  await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
  await expect(sidebar(page).locator("..")).toHaveCSS("transition-duration", "0s");
  await expect(page.getByRole("heading", { name: "对话历史", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^资料/ })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "问题", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("search and selector focus rings belong to their composite frames", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname !== "/api/v1/knowledge-bases") return false;
    await route.fulfill({ json: { items: [base, { ...base, id: "base-2", name: "第二资料库" }], has_more: false } });
    return true;
  });
  for (const [path, role, name] of [["/knowledge-bases", "textbox", "搜索知识库"], ["/conversations", "combobox", "切换知识库"], ["/", "combobox", "选择知识库"]] as const) {
    await page.goto(path);
    const control = page.getByRole(role, { name, exact: true });
    await control.focus();
    await expect(control).toHaveCSS("outline-style", "none");
    await expect(control.locator('xpath=ancestor::*[@data-composite-field][1]')).toHaveCSS("outline-width", "2px");
  }
});

for (const width of [390, 1440]) {
  test(`settings sections have native anchor state and a separate danger area at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockWorkspace(page);
    await page.goto("/settings");
    const navigation = page.getByRole("navigation", { name: "设置分区" });
    await expect(navigation.getByRole("link", { name: "账户", exact: true })).toHaveAttribute("aria-current", "location");
    await navigation.getByRole("link", { name: "模型与数据", exact: true }).click();
    await expect(page).toHaveURL(/#settings-model$/);
    await expect(navigation.getByRole("link", { name: "模型与数据", exact: true })).toHaveAttribute("aria-current", "location");
    await expect(page.locator("#settings-model")).toContainText("单轮问答 · 每次提问独立检索");
    await navigation.getByRole("link", { name: "账户", exact: true }).click();
    await expect(page.getByRole("heading", { name: "危险操作", exact: true })).toBeVisible();
    await expect(page.locator("#settings-account").getByRole("button", { name: "退出登录", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}
