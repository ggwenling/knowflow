# 独立审阅：NOTICE P2-4 后续处置（相对 d6bf89d 未提交 diff）

- Reviewer：CodeBuddy（独立会话，不是本轮实现者）
- Target：未提交工作树相对 `d6bf89dcbf3b57b14dafbb4c54b71f30c96fd21b`（分支 `grok`）
- 审阅范围：`NOTICE`、`docs/reviews/2026-11-04-codebuddy-de830a8.md` 的“后续处置”段
- Verdict：**APPROVED**

## 结论

P2-4 的处置与 `docs/reviews/2026-11-03-dependency-inventory.json` 一致：`@img/sharp-wasm32`、`@img/sharp-win32-*` 均为 0.35.5，`net.java.dev.jna:jna` 为 5.13.0 且为 `test` 作用域；SPDX 表达式与 LGPL／Apache 表述未被误写。原审阅 Verdict 未被改动，`git diff --check` 通过。审阅中仅修正两处措辞，未改变版本、许可证或审阅结论。

## 逐项核对

### 1. 版本与许可证（对照 inventory）

| 组件 | inventory 值 | NOTICE 写法 | 结果 |
|---|---|---|---|
| `@img/sharp-wasm32` | 0.35.5；`Apache-2.0 AND LGPL-3.0-or-later AND MIT` | 同行同值 | 一致 |
| `@img/sharp-win32-*`（arm64 / ia32 / x64） | 0.35.5；`Apache-2.0 AND LGPL-3.0-or-later` | 同行同值，三种架构均存在 | 一致 |
| `net.java.dev.jna:jna` | 5.13.0；`test`；`LGPL-2.1-or-later / Apache-2.0` | 5.13.0；注明仅测试作用域、双许可、按 `Apache-2.0` 使用 | 一致 |
| `@img/sharp-libvips-*` | 1.3.4；`LGPL-3.0-or-later` | 仍为 1.3.4，未与 sharp 本体变体混写 | 一致 |

- 新增两行与 `@img/sharp-libvips-*` 1.3.4 行分开记录，解决了原 P2-4 指出的“含各平台 binary 变体”易被误读为已覆盖 `win32` / `wasm32` 的问题。
- `jna` 的 `test` 作用域和“通常不随 Linux 运行时镜像分发”的限定与 inventory 相符；按 `Apache-2.0` 使用属于本仓库的双许可选择，未被写成唯一许可证。
- 未发现版本号、作用域或 SPDX 标识被误改。

### 2. 原审阅 Verdict

- `docs/reviews/2026-11-04-codebuddy-de830a8.md:6` 仍为 `- Verdict：**APPROVED**`。
- `git diff d6bf89d -- docs/reviews/2026-11-04-codebuddy-de830a8.md` 仅追加文末“后续处置”两行；原 Verdict、P2-4 发现和“未覆盖范围”均未被改写。
- 新增段落明确“本小节仅记录后续处置，不改变上文 Verdict 与原 P2-4 发现记录”，与保留历史审阅记录的写法一致。

### 3. `git diff --check`

- `git diff --check d6bf89d` 退出码 0。
- 新增的未跟踪审阅文件另行检查，无行尾空白、无制表符。

## 本会话修改

1. `NOTICE:16`：将“sharp 本体的平台变体见下两行”改为“sharp 本体中带 LGPL 条款的平台变体见下两行”。原因：inventory 中还有 `@img/sharp-darwin-*`、`linux-*`、`linuxmusl-*`、`freebsd-wasm32`、`webcontainers-wasm32` 等纯 Apache-2.0 变体，原句会被读成下两行已覆盖全部 sharp 平台变体。
2. `docs/reviews/2026-11-04-codebuddy-de830a8.md:138`：将“已在后续提交关闭”改为“已在后续修改中关闭”。原因：该 diff 仍未提交，写“后续提交”与当前工作树状态不符。

两处均只修正措辞，不改变版本、许可证、作用域或 Verdict。

## 未覆盖范围

- 仅核对 `NOTICE` 与本段文字同 inventory 的一致性，不重做许可证法律判断，不核验全量 SBOM。
- 未要求把纯 Apache-2.0 的 `@img/sharp-*` 变体逐条列入 `NOTICE`；该文件开头已限定为弱 copyleft／署名摘要，完整清单以 inventory 为准。
- 未 commit／push，未运行代码、未调用付费 API，未读取或修改盲测材料。

## 验证命令与结果

```sh
git diff --check d6bf89d
# exit 0

python3  # 只读比对 inventory 中的 sharp / jna 版本、作用域与许可证
# PASS @img/sharp-wasm32 0.35.5 / Apache-2.0 AND LGPL-3.0-or-later AND MIT
# PASS @img/sharp-win32-arm64 0.35.5 / Apache-2.0 AND LGPL-3.0-or-later
# PASS @img/sharp-win32-ia32 0.35.5 / Apache-2.0 AND LGPL-3.0-or-later
# PASS @img/sharp-win32-x64 0.35.5 / Apache-2.0 AND LGPL-3.0-or-later
# PASS net.java.dev.jna:jna 5.13.0 / test / LGPL-2.1-or-later / Apache-2.0

git diff d6bf89d -- docs/reviews/2026-11-04-codebuddy-de830a8.md
# 仅追加“后续处置”段；Verdict 行未变
```
