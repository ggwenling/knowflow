import { expect, test, type Page, type Route } from "@playwright/test";

type Account = { user_id: string; email: string };

const accountA: Account = { user_id: "user-a", email: "a@example.test" };
const accountB: Account = { user_id: "user-b", email: "b@example.test" };
const password = "workspace-password";

const pagePath = (route: Route) => new URL(route.request().url()).pathname.replace("/api/v1/", "");

function json(route: Route, body: unknown) {
  return route.fulfill({ json: body });
}

async function signIn(page: Page, email: string) {
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("switching accounts never shows the previous account's knowledge bases", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  let current: Account | null = accountA;
  let baseDelay = 0;

  await page.addInitScript(() => {
    const state = window as Window & { __leakCount?: number; __watchLeaks?: boolean };
    state.__leakCount = 0;
    state.__watchLeaks = false;
    new MutationObserver(() => {
      if (state.__watchLeaks && document.body?.textContent?.includes("账户 A 的知识库")) {
        state.__leakCount = (state.__leakCount ?? 0) + 1;
      }
    }).observe(document.documentElement, { subtree: true, childList: true, characterData: true });
  });

  await page.route("**/api/v1/**", async (route) => {
    const path = pagePath(route);
    const method = route.request().method();
    if (path === "me") {
      if (!current) return route.fulfill({ status: 401, json: { code: "UNAUTHENTICATED", message: "登录状态已失效" } });
      return json(route, current);
    }
    if (path === "auth/logout") {
      current = null;
      return route.fulfill({ status: 204 });
    }
    if (path === "auth/login") {
      current = accountB;
      return json(route, {});
    }
    if (path === "knowledge-bases" && method === "GET") {
      if (baseDelay) await new Promise((resolve) => setTimeout(resolve, baseDelay));
      const owner = current ?? accountB;
      return json(route, {
        items: [{
          id: owner === accountA ? "base-a" : "base-b",
          name: owner === accountA ? "账户 A 的知识库" : "账户 B 的知识库",
          status: "ACTIVE",
        }],
        has_more: false,
      });
    }
    if (path === "questions") return json(route, { items: [], has_more: false });
    if (path.endsWith("/documents")) return json(route, { items: [], has_more: false });
    throw new Error(`Unexpected workspace API: ${method} ${path}`);
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: "账户 A 的知识库", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "退出", exact: true }).click();
  await page.waitForURL("**/login");
  await page.evaluate(() => {
    const state = window as Window & { __leakCount?: number; __watchLeaks?: boolean };
    state.__leakCount = 0;
    state.__watchLeaks = true;
  });

  // Delay account B's payload so the loading gate has to cover the whole switch.
  baseDelay = 1200;
  await signIn(page, accountB.email);
  await expect(page.getByText("正在准备你的工作区…")).toBeVisible();
  await expect(page.getByRole("link", { name: "账户 B 的知识库", exact: true })).toBeVisible();
  await expect(page.getByText("账户 A 的知识库")).toHaveCount(0);
  const leaks = await page.evaluate(() => (window as Window & { __leakCount?: number }).__leakCount ?? 0);
  expect(leaks).toBe(0);
});

test("a create that finishes after an account switch neither reports success nor navigates", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  let current: Account | null = accountA;

  await page.route("**/api/v1/**", async (route) => {
    const path = pagePath(route);
    const method = route.request().method();
    if (path === "me") {
      if (!current) return route.fulfill({ status: 401, json: { code: "UNAUTHENTICATED", message: "登录状态已失效" } });
      return json(route, current);
    }
    if (path === "auth/logout") {
      current = null;
      return route.fulfill({ status: 204 });
    }
    if (path === "auth/login") {
      current = accountB;
      return json(route, {});
    }
    if (path === "knowledge-bases" && method === "GET") {
      const owner = current ?? accountB;
      return json(route, {
        items: [{
          id: owner === accountA ? "base-a" : "base-b",
          name: owner === accountA ? "账户 A 的知识库" : "账户 B 的知识库",
          status: "ACTIVE",
        }],
        has_more: false,
      });
    }
    if (path === "knowledge-bases" && method === "POST") {
      await new Promise((resolve) => setTimeout(resolve, 1800));
      return json(route, { id: "a-created", name: "A 新建的知识库", status: "ACTIVE" });
    }
    if (path === "questions") return json(route, { items: [], has_more: false });
    if (path.endsWith("/documents")) return json(route, { items: [], has_more: false });
    throw new Error(`Unexpected workspace API: ${method} ${path}`);
  });

  await page.goto("/knowledge-bases");
  await expect(page.getByRole("link", { name: "账户 A 的知识库", exact: true })).toBeVisible();
  await page.getByLabel("新知识库名称").fill("A 新建的知识库");
  await page.getByRole("button", { name: "创建知识库", exact: true }).click();

  // Leave the workspace while the create request is still open.
  await page.getByRole("button", { name: "退出", exact: true }).click();
  await page.waitForURL("**/login");
  await signIn(page, accountB.email);
  await expect(page.getByRole("link", { name: "账户 B 的知识库", exact: true })).toBeVisible();

  await page.waitForTimeout(2200);
  expect(new URL(page.url()).pathname).toBe("/");
  await expect(page.getByText("已创建「A 新建的知识库」")).toHaveCount(0);
  await expect(page.getByText("知识库未能创建，请稍后重试。")).toHaveCount(0);
});

test("a failed question history load is surfaced with a working retry", async ({ page }) => {
  let failing = true;

  await page.route("**/api/v1/**", async (route) => {
    const path = pagePath(route);
    const method = route.request().method();
    if (path === "me") return json(route, accountA);
    if (path === "knowledge-bases") {
      return json(route, { items: [{ id: "base-a", name: "账户 A 的知识库", status: "ACTIVE" }], has_more: false });
    }
    if (path === "questions" && method === "GET") {
      if (failing) {
        failing = false;
        return route.fulfill({ status: 500, json: { code: "HISTORY_UNAVAILABLE", message: "问答历史暂时不可用" } });
      }
      return json(route, {
        items: [{
          question_id: "q-1",
          knowledge_base_id: "base-a",
          question: "历史问题一",
          status: "SUCCEEDED",
          finished_at: "2026-11-03T00:00:00Z",
        }],
        has_more: false,
      });
    }
    if (path.endsWith("/documents")) return json(route, { items: [], has_more: false });
    throw new Error(`Unexpected workspace API: ${method} ${path}`);
  });

  await page.goto("/");
  const alert = page.getByRole("alert").filter({ hasText: "问答历史加载失败" });
  await expect(alert).toBeVisible();
  await expect(alert).toContainText("服务暂时不可用，请稍后重试。");

  await alert.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.getByRole("link", { name: /历史问题一/ }).first()).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "问答历史加载失败" })).toHaveCount(0);
});

test("opening a stored answer stops the running stream and frees the composer", async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const path = pagePath(route);
    const method = route.request().method();
    if (path === "me") return json(route, accountA);
    if (path === "knowledge-bases") {
      return json(route, { items: [{ id: "kb-1", name: "竞态知识库", status: "ACTIVE" }], has_more: false });
    }
    if (path === "questions") {
      return json(route, {
        items: [{
          question_id: "q-1",
          knowledge_base_id: "kb-1",
          question: "历史问题一",
          status: "SUCCEEDED",
          finished_at: "2026-11-03T00:00:00Z",
        }],
        has_more: false,
      });
    }
    if (path === "questions/q-1") {
      return json(route, {
        question_id: "q-1",
        knowledge_base_id: "kb-1",
        question: "历史问题一",
        status: "SUCCEEDED",
        finished_at: "2026-11-03T00:00:00Z",
        answer: "历史答案正文",
        has_answer: true,
        failure_code: null,
        sources: [],
      });
    }
    if (path === "knowledge-bases/kb-1/documents") {
      return json(route, {
        items: [{
          id: "doc-1",
          original_name: "资料.pdf",
          status: "READY",
          format: "PDF",
          byte_size: 1024,
          active_index_version_id: "index-1",
        }],
        has_more: false,
      });
    }
    if (path === "knowledge-bases/kb-1/questions/stream" && method === "POST") {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      try {
        return await route.fulfill({ status: 500, json: { code: "STREAM_ABORTED", message: "请求已被取消" } });
      } catch {
        return undefined;
      }
    }
    throw new Error(`Unexpected workspace API: ${method} ${path}`);
  });

  await page.goto("/conversations");
  const composer = page.getByLabel("问题");
  await expect(composer).toBeEnabled();
  await composer.fill("正在生成的问题");
  await page.getByRole("button", { name: "提问", exact: true }).click();
  await expect(page.getByRole("button", { name: "停止生成" })).toBeVisible();
  await expect(composer).toBeDisabled();

  await page.getByRole("link", { name: /历史问题一/ }).click();
  await expect(page).toHaveURL(/\/conversations\/q-1$/);
  await expect(composer).toBeEnabled();
  await expect(page.getByRole("button", { name: "停止生成" })).toHaveCount(0);
  await expect(page.getByText("历史答案正文")).toBeVisible();
});

test("a failed document delete reports the failure instead of success", async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const path = pagePath(route);
    const method = route.request().method();
    if (path === "me") return json(route, accountA);
    if (path === "knowledge-bases") {
      return json(route, { items: [{ id: "kb-1", name: "知识库一", status: "ACTIVE" }], has_more: false });
    }
    if (path === "knowledge-bases/kb-1") {
      return json(route, { id: "kb-1", name: "知识库一", status: "ACTIVE" });
    }
    if (path === "questions") return json(route, { items: [], has_more: false });
    if (path === "knowledge-bases/kb-1/documents") {
      return json(route, {
        items: [{
          id: "doc-1",
          original_name: "无法删除.pdf",
          status: "READY",
          format: "PDF",
          byte_size: 2048,
          active_index_version_id: "index-1",
        }],
        has_more: false,
      });
    }
    if (path === "documents/doc-1" && method === "DELETE") {
      return route.fulfill({ status: 500, json: { code: "DELETE_FAILED", message: "资料暂时无法删除" } });
    }
    throw new Error(`Unexpected workspace API: ${method} ${path}`);
  });

  await page.goto("/knowledge-bases/kb-1");
  await expect(page.getByText("无法删除.pdf")).toBeVisible();
  await page.getByRole("button", { name: "无法删除.pdf 操作" }).click();
  await page.getByRole("menuitem", { name: "删除资料" }).click();
  await page.getByRole("button", { name: "确认删除" }).click();

  await expect(page.getByText("资料未能删除，请稍后重试。")).toBeVisible();
  await expect(page.getByText("已删除「无法删除.pdf」")).toHaveCount(0);
  await expect(page.getByText("无法删除.pdf")).toBeVisible();
});
