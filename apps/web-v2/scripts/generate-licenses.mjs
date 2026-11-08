import { execFileSync } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const npm = process.platform === "win32" ? "npm.cmd" : "npm";
const tree = JSON.parse(execFileSync(npm, ["ls", "--omit=dev", "--all", "--json"], {
  cwd: appRoot,
  encoding: "utf8",
}));

const found = new Map();
function walk(node) {
  for (const [name, entry] of Object.entries(node.dependencies ?? {})) {
    if (entry.version) found.set(`${name}@${entry.version}`, { name, version: entry.version });
    walk(entry);
  }
}
walk(tree);

const rows = [];
for (const pkg of found.values()) {
  let metadata = {};
  try {
    metadata = JSON.parse(await readFile(resolve(appRoot, "node_modules", pkg.name, "package.json"), "utf8"));
  } catch {
    /* optional platform package is not installed on this machine */
  }
  const repository = typeof metadata.repository === "string"
    ? metadata.repository
    : metadata.repository?.url ?? "";
  rows.push({
    name: pkg.name,
    version: pkg.version,
    license: metadata.license ?? "UNKNOWN",
    repository: repository.replace(/^git\+/, "").replace(/\.git$/, ""),
  });
}

rows.sort((a, b) => a.name.localeCompare(b.name));
const unknown = rows.filter((row) => row.license === "UNKNOWN").length;
const generated = new Date().toISOString();
const lines = [
  "# KnowFlow Web v2 第三方许可清单（生产依赖）",
  "",
  `- 生成时间：${generated}`,
  `- 作用域：\`npm ls --omit=dev --all\` 解析到的运行时依赖闭包（不含 devDependencies）`,
  `- 条目：${rows.length}；许可证未知：${unknown}`,
  "- 性质：发行证据清单，不构成法律意见。许可证原文仍需在发行前随镜像分发。",
  "- 说明：根 `THIRD-PARTY-LICENSES.md` 仍只覆盖 `apps/web`；合并前需扩展 `scripts/audit-dependencies.py` 的 Node 作用域。",
  "",
  "| 包 | 版本 | 许可证 | 仓库 |",
  "|---|---|---|---|",
  ...rows.map((row) => `| \`${row.name}\` | ${row.version} | ${row.license} | ${row.repository || "—"} |`),
  "",
];

await writeFile(resolve(appRoot, "THIRD-PARTY-LICENSES.md"), lines.join("\n"), "utf8");
console.log(`wrote apps/web-v2/THIRD-PARTY-LICENSES.md (${rows.length} packages, ${unknown} unknown)`);
