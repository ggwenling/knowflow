import { expect, test } from "@playwright/test";

test("旧版回退可读取新版写入的数据", async ({ browser, baseURL }) => {
  const storageState = process.env.KNOWFLOW_E2E_ROLLBACK_STATE;
  test.skip(!storageState, "Requires the isolated migration test session");
  const context = await browser.newContext({ baseURL, storageState });
  try {
    const page = await context.newPage();
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "KnowFlow", exact: true })).toBeVisible();
    // This spec runs against both the old button-based UI and the new link-based UI.
    const base = page.getByRole("link", { name: /浏览器验收/ }).or(page.getByRole("button", { name: /浏览器验收/ }));
    const question = page
      .getByRole("link", { name: /请根据 PDF 原文给出引用依据/ })
      .or(page.getByRole("button", { name: /请根据 PDF 原文给出引用依据/ }));
    await expect(base.first()).toBeVisible();
    await expect(question.first()).toBeVisible();
  } finally {
    await context.close();
  }
});
