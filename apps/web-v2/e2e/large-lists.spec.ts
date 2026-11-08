import { expect, test } from "@playwright/test";
import { base, document, mockWorkspace } from "./helpers/workspace";

test("large lists retain pagination and keyboard access without speculative detail fan-out", async ({ page }) => {
  test.setTimeout(60_000);
  const bases = Array.from({ length: 500 }, (_, i) => ({ ...base, id: `base-${i + 1}`, name: `资料库 ${i + 1}` }));
  const documents = Array.from({ length: 1000 }, (_, i) => ({ ...document, id: `document-${i + 1}`, original_name: `文档 ${i + 1}.txt` }));
  let speculativeDetails = 0;
  page.on("request", (request) => {
    if (/^\/knowledge-bases\/base-\d+$/.test(new URL(request.url()).pathname) && request.headers()["next-router-prefetch"]) speculativeDetails++;
  });
  await mockWorkspace(page, async (route, url) => {
    const offset = Number(url.searchParams.get("offset"));
    if (url.pathname === "/api/v1/knowledge-bases") {
      await route.fulfill({ json: { items: bases.slice(offset, offset + 50), has_more: offset + 50 < bases.length } }); return true;
    }
    if (url.pathname.endsWith("/documents")) {
      await route.fulfill({ json: { items: documents.slice(offset, offset + 50), has_more: offset + 50 < documents.length } }); return true;
    }
    return false;
  });
  await page.goto("/knowledge-bases");
  await expect(page.getByRole("article")).toHaveCount(500);
  const lastBase = page.locator('article a[href="/knowledge-bases/base-500"]');
  await lastBase.scrollIntoViewIfNeeded(); await lastBase.focus(); await expect(lastBase).toBeFocused();
  expect(speculativeDetails).toBe(0);
  await page.goto("/knowledge-bases/base-1");
  await expect(page.getByRole("article")).toHaveCount(50);
  for (let loaded = 100; loaded <= 1000; loaded += 50) {
    await page.getByRole("button", { name: "加载更多资料", exact: true }).click();
    await expect(page.getByRole("article")).toHaveCount(loaded);
  }
  const last = page.getByRole("button", { name: "文档 1000.txt 操作", exact: true });
  await last.scrollIntoViewIfNeeded(); await last.focus(); await expect(last).toBeFocused();
  await expect(page.getByRole("button", { name: "加载更多资料", exact: true })).toHaveCount(0);
});
