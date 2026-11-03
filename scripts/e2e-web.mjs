import { randomBytes } from "node:crypto";
import { createServer } from "node:net";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = resolve(import.meta.dirname, "..");
const temp = await mkdtemp(resolve(tmpdir(), "knowflow-e2e-"));
const envFile = resolve(temp, ".env");
const streamCapture = resolve(temp, "answer-stream-events.json");
const project = `knowflow-e2e-${randomBytes(5).toString("hex")}`;
const compose = ["compose", "--project-name", project, "-f", "infra/compose.yml", "--env-file", envFile];

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
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${url}/api/mode`, { signal: AbortSignal.timeout(1_000) });
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Web service did not become reachable at ${url}`);
}

function hex(bytes = 32) { return randomBytes(bytes).toString("hex"); }

try {
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
  await writeFile(envFile, env, { mode: 0o600 });
  run("docker", [...compose, "up", "--build", "--quiet-build", "--wait", "--wait-timeout", "240"]);
  const baseUrl = `http://127.0.0.1:${port}`;
  await waitForWeb(baseUrl);
  run(process.execPath, [resolve(root, "apps/web/node_modules/@playwright/test/cli.js"), "test"], {
    cwd: resolve(root, "apps/web"),
    env: { ...process.env, KNOWFLOW_E2E_BASE_URL: baseUrl,
      KNOWFLOW_E2E_STREAM_CAPTURE: streamCapture },
  });
  run("uv", ["run", "--project", "services/ai", "--frozen", "python",
    "contracts/validate_sse_capture.py", streamCapture]);
} finally {
  try { run("docker", [...compose, "down", "--volumes", "--remove-orphans"]); }
  finally { await rm(temp, { recursive: true, force: true }); }
}
