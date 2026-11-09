import { chromium } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { spawn } from "node:child_process";

const baseURL = process.env.KNOWFLOW_ACCEPTANCE_BASE_URL ?? "http://127.0.0.1:3000";
const model = process.env.KNOWFLOW_ACCEPTANCE_MODEL;
if (!model) throw new Error("KNOWFLOW_ACCEPTANCE_MODEL must identify the actual executing agent");
const out = resolve(process.env.KNOWFLOW_ACCEPTANCE_OUT_DIR ?? `test-results/agent-acceptance-${Date.now()}`);
await mkdir(out, { recursive: true });
const email = `agent-${randomBytes(10).toString("hex")}@example.test`;
const password = randomBytes(24).toString("hex");
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  await page.goto(`${baseURL}/register`);
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await page.getByRole("heading", { name: "KnowFlow", exact: true }).waitFor();
  await page.screenshot({ path: resolve(out, "00-dedicated-account.png") });
} finally { await browser.close(); }
const env = { ...process.env, KNOWFLOW_ACCEPTANCE_MODEL: model, KNOWFLOW_ACCEPTANCE_BASE_URL: baseURL,
  KNOWFLOW_E2E_BASE_URL: baseURL, KNOWFLOW_ACCEPTANCE_OUT_DIR: out,
  KNOWFLOW_ACCEPTANCE_EMAIL: email, KNOWFLOW_ACCEPTANCE_PASSWORD: password };
async function run(args, logName) {
  let log = "";
  const child = spawn(process.execPath, args, { env, stdio: ["ignore", "pipe", "pipe"] });
  for (const stream of [child.stdout, child.stderr]) stream.on("data", data => { log += data; process.stdout.write(data); });
  const code = await new Promise((done, reject) => { child.once("error", reject); child.once("exit", done); });
  await writeFile(resolve(out, logName), log);
  if (code !== 0) throw new Error(`${logName} failed (${code}); evidence: ${out}`);
}
await run(["scripts/acceptance.mjs"], "smoke.log");
await run(["node_modules/@playwright/test/cli.js", "test", "agent-acceptance.spec.ts", "--output", resolve(out, "playwright")], "modules.log");
console.log(`Agent acceptance evidence: ${out}`);
