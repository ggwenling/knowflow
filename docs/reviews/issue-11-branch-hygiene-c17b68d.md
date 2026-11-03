# Issue #11 分支卫生报告（T08：归档/同步陈旧 java/python/next）

- 报告日期：2026-11-03（Asia/Hong_Kong）
- 报告基线：`local@c17b68d37bddcf5bcbbde1f127f4c9a4c7674365`（与 `origin/local` 同步）
- 报告性质：**只读**。未删除、重命名、创建或推送任何分支；未开启分支保护；未改业务文件。唯一写入是本文件。
- 前序盘点：`agent/audit-20261103` 上的 `docs/reviews/2026-11-03-branch-hygiene.md`（基线 `84681d4`）。本报告按其口径复核，并将全部计数更新至 `c17b68d`，作为 Issue #11 的正式交付。

## 1. 验收标准对照

| Issue #11 验收标准 | 结果 | 证据 |
|---|---|---|
| 文档写明推荐工作分支 = `local`（合并后可为 `main`） | **满足** | §2 |
| 陈旧分支已标注或删除（删除需项目经理批准） | **满足（标注）** | §3；删除未执行，见 §5 |
| 测试要求：无代码测试；确认 compare 状态更新 | **满足** | §5 |
| 修改范围：分支元数据/保护规则；不改业务文件 | **遵守** | 仅新增本报告 |

## 2. 分支策略（推荐工作分支）

- **推荐工作分支 = `local`**。新工作、派工、提交一律从 `local` 拉出。
- **PR #3 合并后，推荐工作分支改为 `main`**，`local` 退役归档。
- `java`、`python`、`next`、`codex/integration-20261031`、`agent/*` 一律标注 **只读**：不得从其拉新分支、不得向其推送、不得作为合并目标，避免 Agent 误判为并行工作线。
- 分支保护为**可选项，需单独批准**（见 §6），本报告未开启。

## 3. 分支清单与标注

标注含义：
- **活跃**：推荐工作分支。
- **只读·已并入**：全部提交已是 `local` 祖先（`git merge-base --is-ancestor` 通过），纯冗余引用，经批准后可安全删除。
- **只读·分叉**：存在未并入 `local` 的提交，处置（吸收/归档/放弃）前不得删除。

计数格式：`local 独有 / 对方独有`，来自 `git rev-list --left-right --count local...<ref>`，左侧为只存在于 `local` 的提交数。

### 3.1 远端分支（GitHub `ggwenling/knowflow`，共 5 个，均 `protected: false`）

| 远端分支 | tip | 提交时间 (+0800) | 相对 `local` | 已并入 `local` | 标注 |
|---|---|---|---|---|---|
| `origin/local` | `c17b68d` | 2026-11-03 18:19 | 0 / 0 | — | **活跃**（PR #3 head） |
| `origin/main` | `b7e83c8` | 2026-11-02 15:09 | 53 / 0 | 是 | 只读·已并入（默认分支；PR #3 合并后升为主分支） |
| `origin/java` | `26e1aca` | 2026-10-30 17:47 | 132 / 0 | **是** | 只读·已并入 |
| `origin/python` | `b463940` | 2026-10-30 17:23 | 126 / 0 | **是** | 只读·已并入 |
| `origin/next` | `61f5edc` | 2026-10-31 14:53 | 167 / **6** | **否** | **只读·分叉（唯一未合并分叉）**，见 §4 |

### 3.2 本地分支（单一工作树 `D:/konwflow`，检出 `local`）

| 本地分支 | tip | 提交时间 (+0800) | 相对 `local` | 已并入 `local` | upstream | 标注 |
|---|---|---|---|---|---|---|
| `local` | `c17b68d` | 2026-11-03 18:19 | — | — | `origin/local`（同步） | **活跃** |
| `main` | `b7e83c8` | 2026-11-02 15:09 | 53 / 0 | 是 | `origin/main`（同步） | 只读·已并入 |
| `java` | `a70ce15` | 2026-10-31 11:55 | 103 / 0 | **是** | 无 | 只读·已并入（tip 比 `origin/java` 多 29 个提交，同样已并入） |
| `python` | `c6bfb1a` | 2026-10-31 14:32 | 89 / 0 | **是** | 无 | 只读·已并入（tip 比 `origin/python` 多 37 个提交，同样已并入） |
| `codex/integration-20261031` | `493112d` | 2026-10-31 14:35 | 72 / 0 | **是** | 无 | 只读·已并入 |
| `agent/audit-20261103` | `1c6b37d` | 2026-11-03 17:14 | 4 / **1** | 否 | 无 | 只读·分叉（1 个文档提交待定去留） |
| `agent/deploy-prep` | `21a6069` | 2026-11-03 17:19 | 4 / **1** | 否 | 无 | 只读·分叉（1 个部署草案待定去留） |

补充：
- `next` **无本地分支**，仅存在于远端。
- Tag：**0 个**（无版本锚点）。
- `main` 之上 53 个提交全部线性、无 merge commit，`local` 可快进合并。

## 4. `origin/next` 分叉详情（唯一需要决策的分支）

- 分叉点：`7d5095b`（2026-10-29 15:56），`next` 相对该点新增 6 个提交、39 个文件、+2701 行。
- 6 个独有提交：
  1. `f8b8cc9` docs(product): KF2-002 锁定首轮用户任务与验证脚本
  2. `54eebb3` chore(repo): KF2-005 建立仓库组织与协作基础
  3. `ed73444` docs(tasks): KF2-002/KF2-005 执行任务卡
  4. `a9a0b71` feat(web): KF2-008 前端骨架与契约 Mock 预研（draft5 候选，非冻结）
  5. `61efd37` chore(infra): KF2-009 Compose 草案（未验收，CI 工作流因 App 权限暂缓）
  6. `61f5edc` docs(tasks): KF2-008/KF2-009 任务卡（预研/草案，待验收）
- **仅存在于 `next`、`local` 上缺失的内容**（删除前必须权衡）：
  - `docs/tasks/KF2-002.md`、`KF2-005.md`、`KF2-008.md`、`KF2-009.md`（`local` 的 `docs/tasks/` 只有 7 个早期文件，无 KF2 任务卡）
  - `apps/web/src/lib/mock.ts`、`apps/web/src/components/mock-banner.tsx` 等早期 Mock 骨架
  - `infra/docker-compose.yml`（旧路径；`local` 已改为 `infra/compose.yml`，两者路径冲突）
  - `AGENTS.md`、`.editorconfig`、`.gitattributes`（`local` 均无）
- **不建议合并**：`next` 的 Web 骨架与当前 `apps/web` 是两套实现；`docs/product/pilot-protocol.md`、`scenario.md` 在 `local` 已有后续版本，直接合并会回退内容；`infra/docker-compose.yml` 与现行 `infra/compose.yml` 冲突。PR #3 合并后若有人从 `next` 拉分支，会产生大规模伪冲突。

## 5. compare 状态确认（含 GitHub 侧复核）

| 检查项 | 命令/接口 | 结果 |
|---|---|---|
| `main...local` 提交差 | `git rev-list --left-right --count main...local` / GitHub `compare/main...local` | `local` 领先 **53**、落后 **0**（API：`status=ahead`、`ahead_by=53`、`behind_by=0`） |
| 历史是否被改写 | `local` 为 `main` 的线性后继；`c724c79`、`84681d4` 仍为祖先 | 无强推、无 merge commit |
| PR #3 | `GET /repos/ggwenling/knowflow/pulls/3` | `state=open`、`merged=false`、`head=local@c17b68d`、`base=main@b7e83c8`、`mergeable_state=clean` |
| 远端分支数量与保护 | `GET /repos/ggwenling/knowflow/branches` | 5 个（`java`/`local`/`main`/`next`/`python`），`protected` 全部为 `false` |
| Tag | `git tag -l` | 0 个 |

相对 Issue 创建时的证据更新：`java` 落后数由 ~79 → **103**，`python` 由 ~73 → **89**，`next` 由 behind ~114 → **behind 167 / ahead 6**（`local` 在此期间新增提交）。

## 6. 处置建议（均待项目经理批准，本轮一律未执行）

| 对象 | 建议动作 | 风险 | 需批准方 |
|---|---|---|---|
| 本地 `java`、`python`、`codex/integration-20261031` | 删除（内容已 100% 并入 `local`，无信息损失） | 极低 | 项目经理 |
| 远端 `origin/java`、`origin/python` | 删除 | 低（内容已并入 `local`） | 项目经理 + 仓库管理员 |
| `origin/next` | 二选一：①打 `archive/next-20261031` tag 后删除远端分支；②保留只读并在 PR #3 说明中标注"已废弃、仅供追溯"（推荐 ①，保留 KF2 任务卡的追溯能力） | 中（`next` 独有 KF2 任务卡与 Mock 骨架，删除前须打 tag） | 项目经理 |
| `agent/audit-20261103` / `agent/deploy-prep` | 先确认其 1 个独有文档提交是否吸收进 `local`，再删除分支 | 低 | 项目经理 |
| `main`（可选） | 开启分支保护：禁止 force push、要求 PR | 低 | 单独批准（Issue 标注"可选"） |
| 版本锚点（建议） | 合并前打 RC tag，如 `draft10-rc1@<SHA>` | 无 | 项目经理 |

## 7. 复现命令

```bash
git fetch origin --prune
git rev-list --left-right --count local...main        # 53 0
git rev-list --left-right --count local...java        # 103 0
git rev-list --left-right --count local...python      # 89 0
git rev-list --left-right --count local...origin/next # 167 6
git merge-base --is-ancestor java local && echo merged
git merge-base --is-ancestor origin/next local || echo divergent
git log --oneline local..origin/next
git diff --stat local...origin/next
git tag -l | wc -l
# GitHub 侧（需凭据）
curl -s https://api.github.com/repos/ggwenling/knowflow/compare/main...local
curl -s https://api.github.com/repos/ggwenling/knowflow/branches
```

## 8. 边界与未验证项

- 本报告只覆盖分支引用与 compare 状态，不包含代码质量、CI 结果与合并可行性评估。
- 工作树未跟踪产物（`.review-*/` 约 10 MB、`docs/reviews/` 下并行会话草稿）与 `grok bot/` 误入历史文件不属于分支卫生范围，见验收报告 §4/§5，需另行授权处置。
- 远端是否有未 fetch 的新提交：数据反映执行时刻（2026-11-03 18:2x）。
- 分支删除、tag 创建、分支保护开启均需批准后另行执行，本报告不构成执行记录。
