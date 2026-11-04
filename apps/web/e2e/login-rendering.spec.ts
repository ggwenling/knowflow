import { expect, test } from "@playwright/test";

test("login remains usable on mobile when WebGL is unavailable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
      value(this: HTMLCanvasElement, type: string, options?: unknown) {
        return type.startsWith("webgl") ? null : Reflect.apply(getContext, this, [type, options]);
      },
    });
  });
  await page.goto("/");
  const form = page.getByRole("button", { name: "Sign in", exact: true });
  await expect(form).toBeInViewport();
  const fallback = page.locator(".loginFlow");
  await expect(fallback).toHaveCSS("background-image", /login-ribbon\.webp/);
  expect((await page.request.get("/login-ribbon.webp")).ok()).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
});
