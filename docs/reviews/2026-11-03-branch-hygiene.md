# 分支卫生只读盘点（#11）

- 盘点时间：2026-11-03 17:15（Asia/Hong_Kong）
- 仓库：`D:\konwflow`（GitHub `ggwenling/knowflow` 本地克隆）
- 基线：`local@84681d4b6ec184bc067112627f4fd09660177401`；`origin/local` 同 SHA；`main`/`origin/main@b7e83c8`
- 报告性质：**只读**。未创建、删除、重命名、推送任何分支，未合并，未改动 GitHub Issue / PR。唯一写入是本文件（以及同批次的 #14 报告与清单 JSON）。
- 方法：`git fetch --all --prune`（仅更新远端引用）→ `for-each-ref` / `rev-list --left-right --count` / `merge-base --is-ancestor` / `reflog` / `worktree list` / `fsck --dangling` / `status --porcelain -uall`

## 1. 结论摘要

| 判断 | 结果 |
|---|---|
| 主线是否健康 | **是**。`local` 线性快进自 `main`，49 提交、0 merge commit，与 `origin/local` 完全同步 |
| 是否存在历史改写（强推） | **未发现**。`1d0fd5e` 仍是 `local` 祖先；`origin/local` reflog 全部为 `update by push`，无 forced 记录 |
| 是否存在孤儿/重复分支 | **是**，3 个本地分支 + 2 个远端分支内容已全部并入 `local`，属于纯冗余 |
| 是否存在未合并分叉 | **是**，`origin/next` 有 6 个提交不在 `local`/`main` 中（2026-10-29 起分叉） |
| 工作树是否干净 | **否**，3 个已跟踪文件有用户改动 + 1058 个未跟踪文件（约 10.4 MB），全部是评审/交接产物 |
| 版本锚点 | **缺失**，仓库 0 个 tag |

一句话：主线可以放心推进，但 `origin/next` 必须显式处置（合并或归档），否则它会在 PR #3 合并后变成第二个"事实主线"。

## 2. 引用清单

### 2.1 本地分支

| 分支 | SHA | 最后提交（HKT） | 相对 `local` | 是否已并入 `local` | upstream |
|---|---|---|---|---|---|
| `local` | `84681d4` | 2026-11-03 16:55 | — | — | `origin/local`（同步） |
| `main` | `b7e83c8` | 2026-11-02 15:09 | ahead 49 / behind 0 | 是 | `origin/main`（同步） |
| `java` | `a70ce15` | 2026-10-31 11:55 | ahead 99 / behind 0 | **是** | 无 |
| `python` | `c6bfb1a` | 2026-10-31 14:32 | ahead 85 / behind 0 | **是** | 无 |
| `codex/integration-20261031` | `493112d` | 2026-10-31 14:35 | ahead 68 / behind 0 | **是** | 无 |

### 2.2 远端分支

| 远端分支 | SHA | 最后提交 | 相对 `local` | 是否已并入 `local` | 说明 |
|---|---|---|---|---|---|
| `origin/local` | `84681d4` | 2026-11-03 16:55 | 0 / 0 | — | PR #3 head |
| `origin/main` | `b7e83c8` | 2026-11-02 15:09 | ahead 49 / behind 0 | 是 | 默认分支，未合并 PR #3 |
| `origin/java` | `26e1aca` | 2026-10-30 09:47 | ahead 128 / behind 0 | **是** | 已被 `local` 完全吸收 |
| `origin/python` | `b463940` | 2026-10-30 09:23 | ahead 122 / behind 0 | **是** | 已被 `local` 完全吸收 |
| `origin/next` | `61f5edc` | 2026-10-31 14:53 | ahead 163 / **behind 6** | **否** | 唯一分叉分支，见 F1 |

注：`origin/java`、`origin/python` 的 SHA 与本地同名分支不同（本地各多 29 / 37 个提交），但两条链都完整包含在 `local` 中，不构成独立工作线。

### 2.3 其他引用

- Tag：**0 个**
- Worktree：1 个（`D:/konwflow`，检出 `local`）
- `origin/HEAD` → `origin/main`

## 3. 历史完整性核查

| 检查 | 命令 | 结果 |
|---|---|---|
| 验收报告 §1 的"无强推"结论是否仍成立 | `git merge-base --is-ancestor 1d0fd5e local` | **成立**（exit 0） |
| `origin/local` 是否被强推过 | `git reflog show origin/local` | 最近 6 条均为 `update by push`，无 `push (forced)` |
| `main` 是否被移动 | `git rev-parse main origin/main` | 同为 `b7e83c8`，未变 |
| 历史形状 | `git log main..local --merges` | 0 个 merge commit，纯线性 |
| 作者分布 | `git log main..local --format='%an'` | 49/49 全部 `ggwenling`（单作者，见 F6） |
| 悬空对象 | `git fsck --dangling` | 存在若干 dangling blob/tree（rebase/amend 残留，正常，不影响引用） |

`local` 相对 `main` 的 49 个提交全部落在 2026-11-02 至 2026-11-03，其中 45 个触及 `services/`、`apps/`、`contracts/`、`evaluation/`、`infra/`。

## 4. 发现

### F1 — `origin/next` 是唯一未合并分叉（严重度：中高）

- 证据：`git log --oneline main..origin/next` 得 6 个提交；`merge-base local origin/next` = `7d5095b`（2026-10-29）；`git diff --stat local...origin/next` 触及 39 个文件、+2701 行。
- 内容：`docs/tasks/KF2-002/005/008/009`、`apps/web` 早期 Mock 骨架（`src/lib/mock.ts`、`mock-banner.tsx`，draft.5 候选）、`infra/docker-compose.yml`（旧路径，现为 `infra/compose.yml`）、`.editorconfig`、`AGENTS.md`。
- 影响：`next` 的 Web 骨架与当前 `apps/web` 是两套实现，且 `infra/docker-compose.yml` 与现行 `infra/compose.yml` 路径冲突；PR #3 合并后若有人从 `next` 拉分支，会产生大规模伪冲突。文档层（`docs/product/pilot-protocol.md`、`scenario.md`）在 `local` 已有后续版本，直接合并会回退内容。
- 建议：**不合并**。二选一——(a) 打 `archive/next-20261031` tag 后删除远端分支；(b) 在 Issue 里记录"已废弃，仅供追溯"并保留只读。两种都要在 PR #3 合并说明里点一句，避免后续误判为待合并分支。

### F2 — 5 个冗余分支引用（严重度：低）

- 证据：`java`、`python`、`codex/integration-20261031` 三个本地分支均 `--is-ancestor` 于 `local`，且**无 upstream**；`origin/java`、`origin/python` 同样已是 `local` 祖先。
- 影响：`git branch` 列表误导（看起来像并行工作线），实际全部死引用；每次 `git push --all` 会重复推送。
- 建议：确认后删除本地 3 个 + 远端 2 个。远端删除需仓库管理员权限，属不可逆操作，**本轮未执行**。

### F3 — 未跟踪产物 1058 个文件 / 约 10.4 MB（严重度：中）

- 证据：`git status --porcelain -uall` 计 1058 条；目录 `.review-20261101`、`.review-check-pytest`、`.review-codex-1103`、`.review-current-run`、`.review-pytest-all`、`.review-pytest-current`、`.review-pytest-tmp`、`.review-run-pytest`、`.review-session-1101`、`.review-session-1101b`、`.review-session-1101c`（合计约 10.4 MB，单目录最大 2.97 MB）与 `grok bot/`（2 文件）。
- 影响：`git status` 噪声掩盖真实改动；`git add -A` 会一次性带入 1000+ 文件，其中包括测试报告与可能含本地路径的输出。
- 建议：`.gitignore` 增加 `.review-*/`、`.tmp-*/`；`grok bot/` 若属交接文档则移入 `docs/handoff/` 并纳入版本控制，否则同样忽略。**不要**为了消警告递归删除用户产物。

### F4 — 工作树有 3 个已跟踪文件的未提交改动（严重度：低）

- `.context/ai-handoff.md`（交接记录，按 handoff 技能保留未提交）
- `apps/web/next-env.d.ts`（Next 生成物，随 `next dev` 变动）
- `services/ai/.env.example`（用户改动，含变量名不含值）

`next-env.d.ts` 属于生成文件，建议加入 `.gitignore` 并从索引移除，否则每次本地起 dev server 都会污染工作树。

### F5 — 无 tag，无版本锚点（严重度：中）

- 证据：`git tag -l` 为空。当前候选只靠 40 位 SHA 传播，验收报告里已出现"计划写 `a30394a`、远端 HEAD 是 `2833417`"的错绑风险（见验收报告 §8）。
- 建议：合并前打一个带语义的 tag，例如 `draft10-rc1@84681d4`，让签收、恢复证据、性能证据都能指向同一个不可变名字。

### F6 — 49 个提交单作者（严重度：信息项）

- 全部提交作者为 `ggwenling <3118027323@qq.com>`。这不影响分支卫生，但对应验收报告 §4.2 的"作者自签风险"：代码审阅、证据文档、验收结论出自同一条提交链。分支层面无解，属流程问题。

### F7 — 构建产物与依赖缓存已在忽略列表（正面确认）

`target/`、`node_modules/`、`.venv/`、`.next/`、`__pycache__/` 均在 `.gitignore` 内；485 个跟踪文件中最大者为 `apps/web/package-lock.json`（288 KB），无二进制大文件、无模型权重、无 `.env`。这部分卫生状况良好。

## 5. 处置建议（本轮均未执行）

| 对象 | 动作 | 风险 | 需谁批准 |
|---|---|---|---|
| `origin/next` | 打 `archive/next-20261031` 后删除远端分支 | 低（内容已归档于 tag） | 仓库管理员 |
| `java` / `python` / `codex/integration-20261031` | 删除本地分支 | 极低 | 项目负责人 |
| `origin/java` / `origin/python` | 删除远端分支 | 低 | 仓库管理员 |
| `.review-*` / `grok bot/` | 写入 `.gitignore` 或迁出仓库 | 无 | 项目负责人 |
| `apps/web/next-env.d.ts` | 加入 `.gitignore` + `git rm --cached` | 低 | 前端负责人 |
| `local@84681d4` | 打 RC tag | 无 | 项目负责人 |
| PR #3 | 保持 open，等正式 Q/M 签收 | — | 项目负责人 |

## 6. 未验证项

1. **GitHub 侧状态未复核**：本机无 `gh` CLI、本轮未使用任何 GitHub 凭据，PR #3 的 open/mergeable、分支保护规则、Actions 权限设置均引自 `grok bot/knowflow-acceptance-2833417.md`，未独立确认。
2. **远端是否有未 fetch 的新提交**：`fetch --prune` 成功，但只反映执行时刻。
3. **Git LFS 未使用**：无 `.gitattributes` LFS 规则，当前无大文件需求，不构成问题。

## 7. 复现命令

```powershell
git fetch --all --prune
git for-each-ref --sort=-committerdate --format='%(refname:short)|%(objectname:short)|%(committerdate:iso8601)|%(subject)' refs/heads refs/remotes
git rev-list --left-right --count local...origin/next
git merge-base --is-ancestor 1d0fd5e local
git reflog show origin/local --date=iso
git worktree list --porcelain
git status --porcelain -uall | Measure-Object
git diff --stat local...origin/next
```
