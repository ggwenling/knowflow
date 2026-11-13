import { randomBytes } from "node:crypto";
import { createServer } from "node:net";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = resolve(import.meta.dirname, "..");
const temp = await mkdtemp(resolve(tmpdir(), "knowflow-e2e-"));
const envFile = resolve(temp, ".env");
const streamCapture = resolve(temp, "answer-stream-events.json");
const project = `knowflow-e2e-${randomBytes(5).toString("hex")}`;
const candidate = process.argv.includes("--v2");
const rollbackState = resolve(temp, "rollback-session.json");
const webApp = candidate ? "apps/web-v2" : "apps/web";
const artifacts = process.env.KNOWFLOW_E2E_ARTIFACTS
  ? resolve(process.env.KNOWFLOW_E2E_ARTIFACTS) : null;
const override = candidate ? [] : ["-f", "infra/compose.legacy-web.yml"];
const compose = ["compose", "--project-name", project, "-f", "infra/compose.yml", ...override, "--env-file", envFile];

async function availablePort() {
  const server = createServer();
  await new Promise((resolveListen, reject) => server.once("error", reject).listen(0, "127.0.0.1", resolveListen));
  const { port } = server.address();
  await new Promise((resolveClose, reject) => server.close((error) => error ? reject(error) : resolveClose()));
  return port;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { cwd: root, stdio: "inherit", ...options });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} exited with status ${result.status}`);
}

async function waitForWeb(url) {
  const deadline = Date.now() + 60_000;
  let lastProbe = "no response";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${url}/api/mode`, { signal: AbortSignal.timeout(1_000) });
      if (response.ok) return;
      lastProbe = `HTTP ${response.status}`;
    } catch (error) {
      lastProbe = error.cause?.code ?? error.message;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Web service did not become reachable at ${url}; last probe: ${lastProbe}`);
}

function hex(bytes = 32) { return randomBytes(bytes).toString("hex"); }

async function saveDiagnostics(secrets) {
  if (!artifacts) return;
  for (const [file, args] of [
    ["compose-status.txt", ["ps", "--all"]],
    ["compose-logs.txt", ["logs", "--no-color", "--tail", "300"]],
  ]) {
    const result = spawnSync("docker", [...compose, ...args], {
      cwd: root, encoding: "utf8", timeout: 15_000, maxBuffer: 8 * 1024 * 1024,
    });
    let output = (result.stdout ?? "") + (result.stderr ?? "");
    for (const secret of secrets) output = output.replaceAll(secret, "[redacted]");
    output = output.replace(/(postgres(?:ql)?:\/\/)[^@\s]+@/gi, "$1[redacted]@")
      .replace(/(authorization:\s*(?:bearer\s+)?)[^\s,"]+/gi, "$1[redacted]");
    await writeFile(resolve(artifacts, file), output);
  }
}

let secrets = [];
try {
  if (artifacts) await mkdir(artifacts, { recursive: true });
  const port = await availablePort();
  const env = [
    `KNOWFLOW_DEV_POSTGRES_PASSWORD=${hex()}`,
    `KNOWFLOW_DEV_MIGRATOR_PASSWORD=${hex()}`,
    `KNOWFLOW_DEV_APP_PASSWORD=${hex()}`,
    `KNOWFLOW_DEV_AI_PASSWORD=${hex()}`,
    "KNOWFLOW_DEV_MINIO_ROOT_USER=knowflowe2e",
    `KNOWFLOW_DEV_MINIO_ROOT_PASSWORD=${hex()}`,
    `KNOWFLOW_INTERNAL_SHARED_SECRET=${hex()}`,
    `KNOWFLOW_E2E_DUMMY_EMBEDDING_KEY=${hex()}`,
    `KNOWFLOW_E2E_DUMMY_LLM_KEY=${hex()}`,
    "KNOWFLOW_WEB_HOST_BIND=127.0.0.1",
    `KNOWFLOW_WEB_PORT=${port}`,
  ].join("\n");
  secrets = env.split("\n").map((line) => line.split("=")[1]).filter((value) => /^[0-9a-f]{64}$/.test(value));
  await writeFile(envFile, env, { mode: 0o600 });
  run("docker", [...compose, "up", "--build", "--quiet-build", "--wait", "--wait-timeout", "240"]);
  const baseUrl = `http://127.0.0.1:${port}`;
  await waitForWeb(baseUrl);
  const cli = resolve(root, webApp, "node_modules/@playwright/test/cli.js");
  const testOptions = {
    cwd: resolve(root, webApp),
    env: { ...process.env, KNOWFLOW_E2E_BASE_URL: baseUrl,
      KNOWFLOW_E2E_STREAM_CAPTURE: streamCapture, KNOWFLOW_ACCEPTANCE_PROJECT: project,
      ...(candidate ? { KNOWFLOW_E2E_ROLLBACK_STATE: rollbackState } : {}) },
  };
  function playwright(args, report) {
    run(process.execPath, [cli, "test", ...args, ...(artifacts ? ["--reporter=list,json"] : [])], {
      ...testOptions,
      env: { ...testOptions.env, ...(artifacts ? { PLAYWRIGHT_JSON_OUTPUT_FILE: resolve(artifacts, report) } : {}) },
    });
  }
  playwright(candidate ? ["--grep-invert", "旧版回退"] : [], "playwright.json");
  run("uv", ["run", "--project", "services/ai", "--frozen", "python",
    "contracts/validate_sse_capture.py", streamCapture]);
  if (candidate) {
    const fallback = ["compose", "--project-name", project, "-f", "infra/compose.yml",
      "-f", "infra/compose.legacy-web.yml", "--env-file", envFile];
    run("docker", [...fallback, "up", "--no-deps", "--build", "--quiet-build", "--wait", "web"]);
    await waitForWeb(baseUrl);
    // Keep the main suite's artifacts for CI, but give the rollback run its own
    // output directory so Playwright does not try to clear thousands of files
    // from the previous run (and so both runs stay independently inspectable).
    playwright(["rollback.spec.ts", "--output", resolve(artifacts ?? temp, "playwright-rollback")], "rollback.json");
  }
} finally {
  try { await saveDiagnostics(secrets); }
  catch (error) { console.warn("Could not save Compose diagnostics:", error.message); }
  try { run("docker", [...compose, "down", "--volumes", "--remove-orphans"]); }
  finally { await rm(temp, { recursive: true, force: true }); }
}
