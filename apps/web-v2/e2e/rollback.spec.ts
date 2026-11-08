import { expect, test } from "@playwright/test";

test("旧版回退可读取新版写入的数据", async ({ browser, baseURL }) => {
  const storageState = process.env.KNOWFLOW_E2E_ROLLBACK_STATE;
  test.skip(!storageState, "Requires the isolated migration test session");
  const context = await browser.newContext({ baseURL, storageState });
  try {
    const page = await context.newPage();
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "KnowFlow", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: /浏览器验收/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /请根据 PDF 原文给出引用依据/ })).toBeVisible();
  } finally { await context.close(); }
});
