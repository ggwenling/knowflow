import { expect, test } from "@playwright/test";
import { base, mockWorkspace } from "./helpers/workspace";

test("performance events contain normalized routes and no user or query data", async ({ page }) => {
  await page.addInitScript(() => {
    const target = window as unknown as { __metricEvents: unknown[] };
    target.__metricEvents = [];
    window.addEventListener("knowflow-performance", (event) => target.__metricEvents.push((event as CustomEvent).detail));
  });
  await mockWorkspace(page);
  await page.goto(`/knowledge-bases/${base.id}?private=do-not-collect`);
  await expect(page.getByRole("heading", { name: base.name, exact: true })).toBeVisible();
  const events = await page.evaluate(() => (window as unknown as { __metricEvents: Array<{ name: string; route: string; value: number }> }).__metricEvents);
  expect(events.some((item) => item.name === "api_headers_ms")).toBe(true);
  expect(events.every((item) => item.route === "/knowledge-bases/[baseId]" && Number.isFinite(item.value))).toBe(true);
  const serialized = JSON.stringify(events);
  expect(serialized).not.toContain("optimization@example.test");
  expect(serialized).not.toContain("base-1");
  expect(serialized).not.toContain("do-not-collect");
});

test("an external query change cancels an older debounced search commit", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/knowledge-bases?q=initial");
  const search = page.getByRole("textbox", { name: "搜索知识库" });
  await search.fill("uncommitted");
  await page.evaluate(() => window.history.pushState(null, "", "?q=external"));
  await expect(search).toHaveValue("external");
  await page.waitForTimeout(350); // Observe past the 200ms debounce boundary.
  expect(new URL(page.url()).searchParams.get("q")).toBe("external");
});
