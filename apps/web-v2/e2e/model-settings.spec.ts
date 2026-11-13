import { test, expect, type Page } from "@playwright/test";
import { mockWorkspace } from "./helpers/workspace";
import { modelErrorMessage } from "../src/lib/model-errors";

const stored = {
  id: "model-1", base_url: "https://provider.example.test/v1", protocol: "chat_completions",
  model_id: "existing-model", supports_tools: true,
  last_probe_at: "2026-11-12T01:02:03Z", last_probe_status: "success",
};
function gate() {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => { release = resolve; });
  return { promise, release };
}
async function form(page: Page) {
  await page.getByRole("button", { name: "添加自定义模型" }).click();
  await page.getByLabel("Base URL").fill("https://provider.example.test/v1");
  await page.getByLabel("API 密钥", { exact: true }).fill("fixture-key");
  await page.getByLabel("模型 ID", { exact: true }).fill("new-model");
}

for (const name of ["shows testing until save probe completes", "shows success only after successful save"]) {
  test(name, async ({ page }) => {
    const entered = gate(), complete = gate();
    let saves = 0;
    await mockWorkspace(page, async (route, url) => {
      if (url.pathname !== "/api/v1/llm-models") return false;
      if (route.request().method() === "GET") await route.fulfill({ json: { enabled: true, models: [] } });
      else {
        saves++;
        entered.release();
        await complete.promise;
        await route.fulfill({ status: 201, json: { ...stored, model_id: "new-model", supports_tools: false } });
      }
      return true;
    });
    await page.goto("/settings#settings-model");
    await form(page);
    await page.getByRole("button", { name: "测试并保存" }).click();
    await entered.promise;
    try {
      await expect(page.getByRole("button", { name: "正在测试连接…" })).toBeDisabled();
      await expect(page.getByRole("button", { name: "取消", exact: true })).toBeDisabled();
      await expect(page.getByText("连接测试通过，模型已保存。", { exact: true })).toHaveCount(0);
      await expect(page.getByText("new-model", { exact: true })).toHaveCount(0);
      expect(saves).toBe(1);
    } finally { complete.release(); }
    await expect(page.getByRole("status")).toContainText("连接测试通过，模型已保存。");
    await expect(page.getByText("new-model", { exact: true })).toBeVisible();
    await expect(page.getByText(/基础问答/)).toBeVisible();
    await expect(page.getByLabel("API 密钥", { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "添加自定义模型" }).click();
    await expect(page.getByLabel("API 密钥", { exact: true })).toHaveValue("");
    await expect(page.getByText("连接测试通过，模型已保存。", { exact: true })).toHaveCount(0);
  });
}

test("shows accurate URL key and model rejection reasons", async ({ page }) => {
  const codes = ["LLM_MODEL_URL_INVALID", "LLM_MODEL_AUTH_FAILED", "LLM_MODEL_NOT_FOUND",
    "LLM_MODEL_ENDPOINT_NOT_FOUND", "LLM_MODEL_UNREACHABLE", "LLM_MODEL_TIMEOUT", "LLM_MODEL_RATE_LIMITED",
    "LLM_MODEL_PROTOCOL_ERROR", "LLM_MODEL_PROBE_FAILED", "LLM_MODEL_PROBE_LIMIT", "UNKNOWN_SECRET_CODE"];
  let attempt = 0;
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname !== "/api/v1/llm-models") return false;
    if (route.request().method() === "GET") await route.fulfill({ json: { enabled: true, models: [] } });
    else {
      const code = codes[attempt++];
      await route.fulfill({ status: code === "LLM_MODEL_URL_INVALID" ? 400 : code === "LLM_MODEL_PROBE_LIMIT" ? 429 : 422,
        json: { code, message: "PRIVATE_PROVIDER_BODY fixture-key https://user:password@private.example", retryable: false } });
    }
    return true;
  });
  await page.goto("/settings#settings-model");
  await form(page);
  for (const code of codes) {
    await page.getByRole("button", { name: "测试并保存" }).click();
    await expect(page.getByRole("alert").filter({ hasText: modelErrorMessage(code) })).toHaveText(modelErrorMessage(code));
    await expect(page.getByLabel("API 密钥", { exact: true })).toHaveValue("fixture-key");
    await expect(page.getByLabel("模型 ID", { exact: true })).toHaveValue("new-model");
    await expect(page.getByText("连接测试通过，模型已保存。", { exact: true })).toHaveCount(0);
    await expect(page.getByText("new-model", { exact: true })).toHaveCount(0);
    await expect(page.getByText(/PRIVATE_PROVIDER_BODY/)).toHaveCount(0);
  }
  expect(attempt).toBe(codes.length);
});

test("failed edit retains the existing catalog entry", async ({ page }) => {
  await mockWorkspace(page, async (route, url) => {
    if (!url.pathname.startsWith("/api/v1/llm-models")) return false;
    if (route.request().method() === "GET") await route.fulfill({ json: { enabled: true, models: [stored] } });
    else await route.fulfill({ status: 422, json: { code: "LLM_MODEL_AUTH_FAILED", message: "PRIVATE_PROVIDER_BODY" } });
    return true;
  });
  await page.goto("/settings#settings-model");
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await page.getByLabel("模型 ID", { exact: true }).fill("rejected-edit");
  await page.getByRole("button", { name: "测试并保存" }).click();
  await expect(page.getByRole("alert").filter({ hasText: modelErrorMessage("LLM_MODEL_AUTH_FAILED") })).toHaveText(modelErrorMessage("LLM_MODEL_AUTH_FAILED"));
  await expect(page.getByText("existing-model", { exact: true })).toBeVisible();
  await expect(page.getByText(/支持补充检索/)).toBeVisible();
  await expect(page.locator("time")).toHaveAttribute("datetime", stored.last_probe_at);
  await expect(page.getByText("rejected-edit", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("模型 ID", { exact: true })).toHaveValue("rejected-edit");
  await expect(page.getByText("连接测试通过，模型已保存。", { exact: true })).toHaveCount(0);
});

test("displays stored probe time and tool support", async ({ page }) => {
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname !== "/api/v1/llm-models") return false;
    await route.fulfill({ json: { enabled: true, models: [stored, { ...stored, id: "old-model",
      model_id: "legacy-model", supports_tools: false, last_probe_at: null, last_probe_status: null }] } });
    return true;
  });
  await page.goto("/settings#settings-model");
  await expect(page.locator("time")).toHaveAttribute("datetime", stored.last_probe_at);
  await expect(page.getByText(/最近通过检测：/)).toBeVisible();
  await expect(page.getByText("尚无检测记录", { exact: true })).toBeVisible();
  await expect(page.getByText(/支持补充检索/)).toBeVisible();
  await expect(page.getByText(/基础问答/)).toBeVisible();
});
