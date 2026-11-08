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

test("home retains a readable backdrop without WebGL", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
      value(this: HTMLCanvasElement, type: string, options?: unknown) {
        return type.startsWith("webgl") ? null : Reflect.apply(getContext, this, [type, options]);
      },
    });
  });
  await page.route("**/api/v1/**", async (route) => {
    const isSession = new URL(route.request().url()).pathname.endsWith("/me");
    return route.fulfill({ json: isSession ? { user_id: "test", email: "test@example.test" } : { items: [], has_more: false } });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "KnowFlow", exact: true })).toBeVisible();
  await expect(page.locator(".home-art")).toHaveCSS("background-image", /home-wave\.webp/);
  expect((await page.request.get("/home-wave.webp")).ok()).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
