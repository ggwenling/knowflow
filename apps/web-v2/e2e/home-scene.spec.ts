import { expect, test } from "@playwright/test";

type SceneWindow = typeof window & {
  homeDraws: number;
  restoreHomeContext?: () => void;
};

test.use({ deviceScaleFactor: 3 });

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/me") return route.fulfill({ json: { user_id: "scene", email: "scene@example.test" } });
    if (path === "/api/mode") return route.fulfill({ json: { mode: "synthetic" } });
    if (path === "/api/v1/knowledge-bases") return route.fulfill({ json: {
      items: ["product", "research"].map((id) => ({ id, name: id, status: "ACTIVE", updated_at: "2026-11-10T00:00:00Z" })),
      has_more: false,
    } });
    return route.fulfill({ json: { items: [], has_more: false } });
  });
  await page.addInitScript(() => {
    const state = window as SceneWindow;
    state.homeDraws = 0;
    const prototype = WebGL2RenderingContext.prototype;
    const drawArrays = prototype.drawArrays;
    const drawElements = prototype.drawElements;
    prototype.drawArrays = function (...args: Parameters<typeof drawArrays>) {
      state.homeDraws++;
      return drawArrays.apply(this, args);
    };
    prototype.drawElements = function (...args: Parameters<typeof drawElements>) {
      state.homeDraws++;
      return drawElements.apply(this, args);
    };
  });
});

for (const width of [1440, 390]) {
  test(`home scene leaves the composer and scope clear at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const artwork = page.locator(".home-art");
    await expect(artwork).toBeVisible();
    const reserved = await artwork.boundingBox();
    const canvas = page.locator(".home-wave canvas");
    await expect(canvas).toBeVisible();
    expect(await artwork.boundingBox()).toEqual(reserved);
    await expect(page.getByRole("combobox", { name: "选择知识库" })).toBeVisible();
    await expect.poll(() => page.evaluate(() => (window as SceneWindow).homeDraws)).toBeGreaterThan(6);
    const result = await canvas.evaluate((node: HTMLCanvasElement) => new Promise<{
      artworkPixels: number; controlAlpha: number; belowInputAlpha: number; samples: number;
    }>((done) => {
      requestAnimationFrame(() => {
        const gl = node.getContext("webgl2")!;
        const pixels = new Uint8Array(node.width * node.height * 4);
        gl.readPixels(0, 0, node.width, node.height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
        const bounds = node.getBoundingClientRect();
        const form = document.querySelector('[aria-label="向知识库提问"]')!.closest("form")!.getBoundingClientRect();
        const scope = document.querySelector('[aria-label="选择知识库"]')!.closest("label")!.getBoundingClientRect();
        const controls = [form, scope];
        let artworkPixels = 0;
        let controlAlpha = 0;
        let belowInputAlpha = 0;
        let samples = 0;
        for (let y = 0; y < node.height; y++) {
          for (let x = 0; x < node.width; x++) {
            const alpha = pixels[((node.height - 1 - y) * node.width + x) * 4 + 3];
            if (alpha > 0) artworkPixels++;
            const screenX = bounds.left + (x + .5) * bounds.width / node.width;
            const screenY = bounds.top + (y + .5) * bounds.height / node.height;
            for (const rect of controls) {
              if (screenX >= rect.left && screenX <= rect.right && screenY >= rect.top && screenY <= rect.bottom) {
                controlAlpha = Math.max(controlAlpha, alpha);
                samples++;
              }
            }
            if (window.innerWidth <= 760 && screenY >= form.top) belowInputAlpha = Math.max(belowInputAlpha, alpha);
          }
        }
        done({ artworkPixels, controlAlpha, belowInputAlpha, samples });
      });
    }));
    // Check actual WebGL alpha, so opaque form styling cannot hide a collision.
    expect(result.artworkPixels).toBeGreaterThan(300);
    expect(result.samples).toBeGreaterThan(300);
    expect(result.controlAlpha).toBe(0);
    expect(result.belowInputAlpha).toBe(0);
  });
}

test("home scene stops GPU draws offscreen, in hidden tabs, for reduced motion and after unmount", async ({ page }) => {
  const shaderErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") shaderErrors.push(message.text());
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const canvas = page.locator(".home-wave canvas");
  const draws = () => page.evaluate(() => (window as SceneWindow).homeDraws);
  await expect(canvas).toBeVisible();
  await expect.poll(draws).toBeGreaterThan(6);
  expect(await canvas.evaluate((node: HTMLCanvasElement) => node.width / node.clientWidth)).toBeLessThanOrEqual(2);
  await expect(canvas).toHaveAttribute("aria-hidden", "true");
  await expect(page.locator(".home-wave")).toHaveCSS("pointer-events", "none");

  async function expectPaused() {
    // Let observer/media-query notifications and any queued frame settle first.
    await page.waitForTimeout(150);
    const before = await draws();
    await page.waitForTimeout(180);
    expect(await draws()).toBe(before);
  }
  async function expectResumed() {
    const before = await draws();
    await expect.poll(draws).toBeGreaterThan(before);
  }

  await page.locator(".home-wave").evaluate((node: HTMLElement) => { node.style.transform = "translateY(200vh)"; });
  await expectPaused();
  await page.locator(".home-wave").evaluate((node: HTMLElement) => { node.style.transform = ""; });
  await expectResumed();

  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expectPaused();
  await page.evaluate(() => {
    Reflect.deleteProperty(document, "hidden");
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expectResumed();

  await page.emulateMedia({ reducedMotion: "reduce" });
  await expectPaused();
  const still = await canvas.screenshot();
  await page.waitForTimeout(180);
  expect(still.equals(await canvas.screenshot())).toBe(true);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expectResumed();

  await page.getByRole("link", { name: "创建工作流", exact: true }).click();
  await expect(canvas).toHaveCount(0);
  await expectPaused();
  expect(shaderErrors).toEqual([]);
});

test("mobile caps resolution and restores the static fallback during WebGL context loss", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const canvas = page.locator(".home-wave canvas");
  await expect(canvas).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as SceneWindow).homeDraws)).toBeGreaterThan(6);
  expect(await canvas.evaluate((node: HTMLCanvasElement) => node.width / node.clientWidth)).toBeLessThanOrEqual(1.5);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const reserved = await page.locator(".home-art").boundingBox();
  await canvas.evaluate((node: HTMLCanvasElement) => {
    const extension = node.getContext("webgl2")!.getExtension("WEBGL_lose_context")!;
    (window as SceneWindow).restoreHomeContext = () => extension.restoreContext();
    extension.loseContext();
  });
  await expect(canvas).toHaveCount(0);
  await expect(page.locator(".home-art")).toHaveCSS("background-image", /home-wave\.webp/);
  await expect(page.locator(".home-art")).toHaveCSS("height", "216px");
  expect(await page.locator(".home-art").boundingBox()).toEqual(reserved);
  const before = await page.evaluate(() => (window as SceneWindow).homeDraws);
  await page.waitForTimeout(180);
  expect(await page.evaluate(() => (window as SceneWindow).homeDraws)).toBe(before);
  await page.evaluate(() => (window as SceneWindow).restoreHomeContext!());
  await expect(canvas).toBeVisible();
  await expect(canvas).toHaveCSS("height", "216px");
  expect(await page.locator(".home-art").boundingBox()).toEqual(reserved);
  await expect.poll(() => page.evaluate(() => (window as SceneWindow).homeDraws)).toBeGreaterThan(before);
});
