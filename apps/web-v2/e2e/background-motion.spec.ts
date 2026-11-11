import { expect, test } from "@playwright/test";

for (const home of [false, true]) {
  test(`${home ? "home loom" : "login ribbon"} pauses without replacing its canvas`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/v1/me") return route.fulfill(home
        ? { json: { user_id: "motion-test", email: "motion@example.test" } }
        : { status: 401, json: {} });
      return route.fulfill({ json: { items: [], has_more: false } });
    });
    await page.goto(home ? "/" : "/login");
    const canvas = page.locator(home ? ".home-wave canvas" : ".loginCanvas canvas");
    await expect(canvas).toBeVisible();
    const identity = await canvas.elementHandle();
    const pause = page.getByRole("button", { name: home ? "暂停背景动画" : "Pause background animation", exact: true });
    await pause.click();
    await expect(pause).toHaveAttribute("aria-pressed", "true");
    const still = await canvas.screenshot();
    await page.waitForTimeout(150); // Enough frames for a running scene to change.
    expect(still.equals(await canvas.screenshot())).toBe(true);
    await pause.click();
    await expect(pause).toHaveAttribute("aria-pressed", "false");
    expect(await canvas.evaluate((node, previous) => node === previous, identity)).toBe(true);
    await expect.poll(async () => !still.equals(await canvas.screenshot())).toBe(true);
  });
}
