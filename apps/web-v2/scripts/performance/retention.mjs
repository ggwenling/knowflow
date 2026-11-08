import { chromium } from '@playwright/test';
import { createWriteStream } from 'node:fs';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { once } from 'node:events';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { relative, resolve } from 'node:path';
import { cpus, hostname, platform, release } from 'node:os';

// Mock-only diagnostic. Snapshots contain the full synthetic page heap; never use a real account.
const baseUrl = new URL(process.env.KNOWFLOW_E2E_BASE_URL ?? 'http://127.0.0.1:3300');
if (!['127.0.0.1', 'localhost', '[::1]'].includes(baseUrl.hostname)) throw new Error('Retention diagnostics require a localhost instance');
const mode = process.env.PERF_RETENTION_MODE ?? 'snapshots';
if (!['snapshots', 'metrics', 'minimal'].includes(mode)) throw new Error('Invalid PERF_RETENTION_MODE');
const rounds = Number(process.env.PERF_RETENTION_ROUNDS ?? 180);
if (!Number.isInteger(rounds) || rounds < 60 || rounds > 1000 || rounds % 20 !== 0) throw new Error('Rounds must be a multiple of 20 in [60, 1000]');
const label = process.env.PERF_RETENTION_LABEL ?? new Date().toISOString().replaceAll(/[:.]/g, '-');
if (!/^[a-zA-Z0-9_-]+$/.test(label)) throw new Error('Invalid output label');
const output = resolve(import.meta.dirname, '../../performance-results/retention', label);
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const samples = [];
const errors = [];
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block' });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  let requests = 0;
  await page.route('**/api/**', async route => {
    requests++;
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/mode') return route.fulfill({ json: { mode: 'synthetic' } });
    if (path === '/api/v1/me') return route.fulfill({ json: { user_id: 'retention', email: 'retention@example.test' } });
    if (path === '/api/v1/knowledge-bases') return route.fulfill({ json: { items: [{ id: 'base', name: '资源释放验收', status: 'ACTIVE' }], has_more: false } });
    return route.fulfill({ json: { items: [], has_more: false } });
  });
  const cdp = await context.newCDPSession(page);
  if (mode !== 'minimal') await cdp.send('Performance.enable');
  await cdp.send('HeapProfiler.enable');
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 });
  await page.goto(new URL('/workflow', baseUrl).href);
  const cycle = async () => {
    const navigation = page.getByRole('navigation', { name: '主导航' });
    await navigation.getByRole('link', { name: '首页', exact: true }).click();
    await page.locator('canvas').waitFor({ state: 'visible' });
    await navigation.getByRole('link', { name: '工作流', exact: true }).click();
    await page.locator('canvas').waitFor({ state: 'detached' });
  };
  const snapshot = async cycles => {
    const path = resolve(output, `${cycles}.heapsnapshot`);
    const stream = createWriteStream(path);
    let failed;
    stream.on('error', error => { failed = error; });
    const listener = ({ chunk }) => stream.write(chunk);
    cdp.on('HeapProfiler.addHeapSnapshotChunk', listener);
    try {
      await cdp.send('HeapProfiler.takeHeapSnapshot', { reportProgress: false, captureNumericValue: true, exposeInternals: false });
    } finally {
      cdp.off('HeapProfiler.addHeapSnapshotChunk', listener);
      stream.end();
      await once(stream, 'close');
    }
    if (failed) throw failed;
    return `${cycles}.heapsnapshot`;
  };
  const sample = async cycles => {
    await cdp.send('HeapProfiler.collectGarbage');
    const heap = await cdp.send('Runtime.getHeapUsage');
    const metrics = mode === 'minimal' ? {} : Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(item => [item.name, item.value]));
    const counters = await cdp.send('Memory.getDOMCounters');
    // Only return primitives. Do not retain browser objects via console or CDP object handles.
    const timing = await page.evaluate(() => ({
      navigationEntries: performance.getEntriesByType('navigation').length,
      resourceEntries: performance.getEntriesByType('resource').length,
      measureEntries: performance.getEntriesByType('measure').length,
      markEntries: performance.getEntriesByType('mark').length,
    }));
    const result = { cycles, heapBytes: metrics.JSHeapUsedSize ?? heap.usedSize, runtimeHeapBytes: heap.usedSize, embedderHeapBytes: heap.embedderHeapUsedSize, backingStorageBytes: heap.backingStorageSize, ...counters, ...timing, apiRequests: requests };
    const middle = Math.min(60, Math.floor(rounds / 40) * 20);
    if (mode === 'snapshots' && [0, middle, rounds].includes(cycles)) result.snapshot = await snapshot(cycles);
    samples.push(result);
    await writeFile(resolve(output, 'samples.json'), JSON.stringify(samples, null, 2) + '\n');
    console.log(JSON.stringify(result));
  };
  await cycle();
  await cycle();
  await sample(0);
  for (let i = 20; i <= rounds; i += 20) {
    for (let j = 0; j < 20; j++) await cycle();
    await sample(i);
  }
  await context.close();
  const git = args => execFileSync('git', args, { cwd: resolve(import.meta.dirname, '../../../..'), encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }).trim();
  const appRoot = resolve(import.meta.dirname, '../..');
  const sourceFiles = [];
  const collect = async directory => {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const path = resolve(directory, entry.name);
      if (entry.isDirectory()) await collect(path);
      else if (entry.isFile()) sourceFiles.push(path);
    }
  };
  await collect(resolve(appRoot, 'src'));
  for (const name of ['package.json', 'package-lock.json', 'next.config.ts']) sourceFiles.push(resolve(appRoot, name));
  const manifest = [];
  for (const path of sourceFiles.sort()) manifest.push({ path: relative(appRoot, path).replaceAll('\\', '/'), sha256: createHash('sha256').update(await readFile(path)).digest('hex') });
  const report = {
    generatedAt: new Date().toISOString(), browser: browser.version(), node: process.version,
    machine: { hostname: hostname(), platform: platform(), release: release(), cpu: cpus()[0]?.model },
    source: { branch: git(['branch', '--show-current']), commit: git(['rev-parse', 'HEAD']), buildId: (await readFile(resolve(appRoot, '.next/BUILD_ID'), 'utf8')).trim(), applicationSha256: createHash('sha256').update(JSON.stringify(manifest)).digest('hex'), manifest, trackedDiffSha256: createHash('sha256').update(git(['diff', '--binary', '--', 'apps/web-v2', '.github/workflows/web-e2e.yml', 'scripts/e2e-web.mjs'])).digest('hex') },
    conditions: { mode, baseUrl: baseUrl.origin, fixture: 'same synthetic retention user, one base, empty lists', warmup: 2, rounds, sampleEvery: 20, viewport: '1440x1000', cpuRate: 1, network: 'local, unthrottled', cache: 'fresh context, same-page SPA; Playwright routing disables HTTP cache', waits: 'home canvas visible; workflow canvas detached; explicit GC before metrics and optional snapshot', observation: 'no React devtools hook or custom metric accumulation; Performance CDP enabled except minimal control; HeapProfiler enabled in all groups', limitations: 'JS heap, not GPU/native memory; snapshots may perturb GC/JIT; minimal group still uses CDP and Playwright' }, samples, errors,
  };
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(`Report: ${resolve(output, 'report.json')}`);
} finally {
  await browser.close();
}
