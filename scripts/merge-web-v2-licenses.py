"""Merge the generated web-v2 production license table into the root notice.

The root inventory predates apps/web-v2 and is not deduplicated across the two
web apps (they can coexist for rollback). This script appends a clearly marked
section so the release evidence contains every web-v2 runtime package without
rewriting the historical apps/web counts.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "web-v2" / "THIRD-PARTY-LICENSES.md"
ROOT_NOTICE = ROOT / "THIRD-PARTY-LICENSES.md"
START = "<!-- WEB_V2_LICENSES_START -->"
END = "<!-- WEB_V2_LICENSES_END -->"


def main() -> int:
    app_text = APP.read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([^`]+)` \| ([^|]+?) \| ([^|]+?) \|", app_text, re.MULTILINE)
    if len(rows) < 100:
        raise SystemExit(f"unexpected web-v2 license row count: {len(rows)}")

    lines = [
        START,
        "",
        f"### Node / Web v2（{len(rows)} 条，运行时）",
        "",
        "> `apps/web-v2` 是 Compose 默认工作台，与旧版 `apps/web` 可并存回退。以下依赖来自 "
        "`npm ls --omit=dev --all`，**未与旧版 Node 清单去重**；完整仓库字段见 "
        "`apps/web-v2/THIRD-PARTY-LICENSES.md`。发行 SBOM 应统一重算总量。",
        "",
        "| 包 | 版本 | 作用域 | 许可证 | 来源 |",
        "|---|---|---|---|---|",
    ]
    for name, version, license_text in rows:
        lines.append(f"| `{name.strip()}` | {version.strip()} | 运行时 | {license_text.strip()} | npm |")
    lines += ["", END]

    root_text = ROOT_NOTICE.read_text(encoding="utf-8")
    root_text = re.sub(
        rf"{re.escape(START)}.*?{re.escape(END)}\n?",
        "",
        root_text,
        flags=re.DOTALL,
    )
    marker = "## 5. 未覆盖范围与待核实"
    if marker not in root_text:
        raise SystemExit("root license section marker not found")
    root_text = root_text.replace(marker, "\n".join(lines) + "\n\n" + marker, 1)
    ROOT_NOTICE.write_text(root_text, encoding="utf-8")
    print(f"merged {len(rows)} web-v2 production packages into {ROOT_NOTICE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
