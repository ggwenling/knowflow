# PR / 分支合规记录（2026-11-08）

状态：**待补充远端证据与负责人例外审批**。本文件不声称合规已完成。

## 1. 当前事实

- 仓库：`https://github.com/ggwenling/knowflow.git`
- 分支：`local`，HEAD `6da4675c323dcd7a7d495b8ca7226d6682e77ed1`（以实际 `git rev-parse HEAD` 为准）。
- 远端 `main` 曾发生绕过 PR 规则的推送；`docs/planning/2026-11-07-deliverable-checklist.md` §1 与 §7 已记录。
- 本机没有安装 `gh` CLI，因此本次无法读取分支保护规则或创建 PR；只能用 `git push` + GitHub compare URL。

## 2. 需要补齐的证据

| # | 证据 | 现状 | 负责人动作 |
|---|---|---|---|
| 1 | 当前 `local` → `main` PR 链接 | 未创建 | 推送后创建 PR，记录 URL |
| 2 | PR 审批人/审批时间 | 未记录 | 至少一名独立审批 |
| 3 | `main` 分支保护规则截图/API | 未取得 | `gh api repos/{owner}/{repo}/branches/main/protection` 或 GitHub 设置截图 |
| 4 | 历史绕过 PR 的例外授权 | 未记录 | 书面例外/事后审批 |
| 5 | CI 结果 | 未核对当前 SHA | 记录 push/PR run URL 与结论 |
| 6 | 工作树收口 | 未提交 | 提交/PR 后记录 `git status` 为空 |

## 3. 例外申请模板

```text
申请事项：main 分支推送绕过 PR 规则的例外
关联提交/PR：<SHA / URL>
原因：<为什么无法在规则内完成>
风险与补偿措施：<review、回滚、审计>
申请人 / 日期：
批准人 / 日期：
```

## 4. 验证步骤（有 GitHub 权限时）

```powershell
git push origin local
# 打开 https://github.com/ggwenling/knowflow/compare/main...local 创建 PR
gh api repos/ggwenling/knowflow/branches/main/protection
gh run list --branch local --limit 5
```

## 5. 签字

| 项 | 负责人 | 日期 | 证据 |
|---|---|---|---|
| PR 链接 |  |  |  |
| 审批记录 |  |  |  |
| 分支保护 |  |  |  |
| 例外授权（如有） |  |  |  |

签字栏为空，直到真实证据到位。
