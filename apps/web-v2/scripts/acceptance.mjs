import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const outDir = process.env.KNOWFLOW_ACCEPTANCE_OUT_DIR
  ? resolve(process.env.KNOWFLOW_ACCEPTANCE_OUT_DIR)
  : resolve(here, "../../../eval-out/acceptance-20261108");
const baseURL = process.env.KNOWFLOW_ACCEPTANCE_BASE_URL ?? "http://127.0.0.1:3000";
const email = process.env.KNOWFLOW_ACCEPTANCE_EMAIL;
const password = process.env.KNOWFLOW_ACCEPTANCE_PASSWORD;

if (!email || !password) {
  console.error("Set KNOWFLOW_ACCEPTANCE_EMAIL and KNOWFLOW_ACCEPTANCE_PASSWORD (credentials are never written to disk).");
  process.exit(2);
}

const manifest = {
  started_at: new Date().toISOString(),
  base_url: baseURL,
  account: email,
  steps: [],
  screenshots: [],
  created: { knowledge_base: "", question: "" },
  agent_execution: { model: process.env.KNOWFLOW_ACCEPTANCE_MODEL ?? "unverified", scope: "smoke and responsive screenshots" },
};

await mkdir(outDir, { recursive: true });

function record(name, status = "passed", detail = "") {
  manifest.steps.push({ name, status, detail, at: new Date().toISOString() });
  console.log(`${status === "passed" ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
}

async function save() {
  manifest.finished_at = new Date().toISOString();
  await writeFile(resolve(outDir, "manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
}

const browser = await chromium.launch();
manifest.agent_execution.browser = `Chromium ${browser.version()}`;
manifest.agent_execution.environment = `${process.platform}/${process.arch}; ${process.version}; ${baseURL}`;
let context;
let page;
let baseId = "";

try {
  context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  page = await context.newPage();

  await page.goto(`${baseURL}/login`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL((url) => url.pathname === "/", { timeout: 30_000 });
  await page.getByRole("heading", { name: "KnowFlow", exact: true }).waitFor();
  record("登录");

  const baseName = `验收资料库 ${Date.now()}`;
  await page.getByRole("link", { name: "创建知识库", exact: true }).click();
  await page.waitForURL(/\/knowledge-bases\?create=1$/);
  await page.getByLabel("新知识库名称").fill(baseName);
  await page.getByRole("button", { name: "创建知识库" }).click();
  await page.waitForURL(/\/knowledge-bases\/[^/]+$/);
  baseId = new URL(page.url()).pathname.split("/").pop();
  manifest.created.knowledge_base = baseId;
  await page.getByRole("heading", { name: baseName }).waitFor();
  record("创建知识库", "passed", baseId);

  const fileName = "验收资料.md";
  const content = "KnowFlow 验收资料。\n索引状态只有 READY 时才会参与问答。\n上传文件大小上限为 8 MiB。\n";
  await page.locator('input[type="file"]').first().setInputFiles({
    name: fileName,
    mimeType: "text/markdown",
    buffer: Buffer.from(content),
  });
  const card = page.getByRole("article").filter({ hasText: fileName });
  await card.waitFor({ timeout: 30_000 });
  await card.getByText("已就绪").waitFor({ timeout: 90_000 });
  record("上传并等待 READY");

  await page.getByRole("link", { name: "对话", exact: true }).click();
  const question = "什么时候允许使用这份资料进行问答？";
  await page.getByPlaceholder("例如：这个接口有哪些必填字段？").fill(question);
  await page.getByRole("button", { name: "提问", exact: true }).click();
  await page.getByText("原文依据").waitFor({ timeout: 60_000 });
  await page.getByRole("button").filter({ hasText: "索引状态只有 READY" }).first().click();
  const dialog = page.getByRole("dialog", { name: "原文依据" });
  await dialog.waitFor();
  const close = page.getByRole("button", { name: "关闭原文" });
  await page.waitForFunction(() => document.activeElement?.getAttribute("aria-label") === "关闭原文", undefined, { timeout: 10_000 });
  await page.waitForTimeout(450);
  const dialogShot = resolve(outDir, "04-source-dialog-1440.png");
  await page.screenshot({ path: dialogShot });
  manifest.screenshots.push({ name: "04-source-dialog-1440", path: dialogShot, width: 1440, height: 900 });
  await close.click();
  await page.waitForTimeout(300);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.locator("[data-sonner-toast]").waitFor({ state: "detached", timeout: 6_000 }).catch(() => undefined);
  const answerShot = resolve(outDir, "04b-chat-answer-1440.png");
  await page.screenshot({ path: answerShot });
  manifest.screenshots.push({ name: "04b-chat-answer-1440", path: answerShot, width: 1440, height: 900 });
  record("流式问答与引用弹层");

  const state = await context.storageState();
  const shots = [
    { name: "01-home-1440", path: "/", width: 1440, height: 1000, fullPage: true },
    { name: "02-bases-1440", path: "/knowledge-bases", width: 1440, height: 900, fullPage: true },
    { name: "03-base-detail-1440", path: `/knowledge-bases/${baseId}`, width: 1440, height: 900, fullPage: true },
    { name: "05-settings-1440", path: "/settings", width: 1440, height: 900, fullPage: false },
    { name: "06-home-390", path: "/", width: 390, height: 844, fullPage: true },
    { name: "07-bases-390", path: "/knowledge-bases", width: 390, height: 844, fullPage: true },
    { name: "08-base-detail-390", path: `/knowledge-bases/${baseId}`, width: 390, height: 844, fullPage: true },
    { name: "09-chat-768", path: "/conversations", width: 768, height: 900, fullPage: false },
  ];

  for (const shot of shots) {
    const shotContext = await browser.newContext({
      viewport: { width: shot.width, height: shot.height },
      storageState: state,
    });
    const shotPage = await shotContext.newPage();
    await shotPage.goto(`${baseURL}${shot.path}`, { waitUntil: "networkidle" });
    await shotPage.waitForTimeout(900);
    const file = resolve(outDir, `${shot.name}.png`);
    await shotPage.screenshot({ path: file, fullPage: shot.fullPage });
    manifest.screenshots.push({ name: shot.name, path: file, width: shot.width, height: shot.height });
    await shotContext.close();
  }
  record("多尺寸截图", "passed", `${shots.length} 张`);

  const cleanup = await page.evaluate(async ({ id, text }) => {
    const list = await (await fetch("/api/v1/questions?limit=100")).json();
    const item = list.items.find((row) => row.question === text);
    if (item) await fetch(`/api/v1/questions/${item.question_id}`, { method: "DELETE" });
    const base = await fetch(`/api/v1/knowledge-bases/${id}`, { method: "DELETE" });
    return { question_deleted: Boolean(item), base_status: base.status };
  }, { id: baseId, text: question });
  manifest.created.question = cleanup.question_deleted ? "deleted" : "not_found";
  record("清理验收数据", cleanup.base_status < 300 ? "passed" : "failed", JSON.stringify(cleanup));
} catch (error) {
  record("验收中断", "failed", String(error));
  if (page) {
    await page.screenshot({ path: resolve(outDir, "failure.png"), fullPage: false }).catch(() => undefined);
  }
  await save();
  await browser.close();
  process.exit(1);
}

await save();
await browser.close();
console.log(`Manifest: ${resolve(outDir, "manifest.json")}`);
