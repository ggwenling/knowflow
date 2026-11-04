# Sol 独立审阅：Box 盲测 20 题报告

- Reviewer: Sol High（独立审阅，本会话未参与被审文件实现）
- 审阅日期：2026-11-05（Asia/Shanghai）
- Brief：`/workspace/knowflow-briefs/2026-11-04-sol-box-blind-20-review.md`
- 分支 / 当前 HEAD：`grok` / `bf720e4393511e68f72304c276d7893ae729b23a`
- 审阅对象：工作树中尚未提交的 `docs/evaluation/2026-11-04-rag-box-blind-20.md` 和 `docs/evaluation/assets-box-blind-20261104-metrics.json`。
- Verdict: **APPROVED**

报告如实披露三项质量门失败；聚合数字、脱敏边界、运行指纹及账本摘要相互一致，出处与局限说明齐全。本结论仅批准本轮报告与 assets 的审阅范围，不表示模型质量门通过，也不表示负责人 Windows 盲测完成。

## Findings

### P0

未发现。

### P1

未发现。

### P2

未发现待修复项。

## 核对依据

1. **隐私与可提交边界。** 全文检查两个被审文件，未见题面、答案、span/quote 正文、完整预测或密钥。报告第 45–59 行只公开哈希前缀、失败状态和错误类别。assets 的 20 条 `question_results` 经字段白名单断言，每条恰含 `id_hash`、`outcome`、`category`；哈希均为唯一的 64 位十六进制值。这里按 brief 明确允许的脱敏字段边界审阅；未将 runbook 禁止提交的原始完整逐题评分视为可公开材料。

2. **门禁与分母。** 报告第 31–39 行与 assets 的 `metrics`、`quality_gate.checks` 一致：Recall@5 为 30/30，MRR@10 为 1；support 为 11/16，citation 为 19/25，不可答拒答为 4/5，后三项分别低于 0.90、0.95、0.90，整体 `failed`。可答误拒答为 0/15；本次 execution errors 为 0，可答回答率 15/15 与该表述相符。support/citation 覆盖分别为 16/16、25/25。内存脚本核对了全部八项门禁的 observed 与指标值、minimum 与状态；报告未把采集成功混同为质量门成功。

3. **样本量与审核性质。** 第 14、39 行明确 n=20、15 可答和 5 不可答，并说明不可答单题影响 20 个百分点，90% 门槛实际要求 5/5。第 33–34、41、64 行明确标注 script review proxy、自动启发式 reviewer 及非人工独立复核。assets 沿用的 `human_*` 指标键没有被报告解释成人工审核证据。

4. **失败摘要与类别。** 第 47–57 行共 11 条失败记录，涉及 5 个唯一哈希；每个前缀在 assets 中恰好匹配一条已回答记录，无前缀碰撞或重复的“哈希＋类别”记录。类别可重叠，计数为 citation 5、support 5、refusal 1，与第 59 行一致。16−11=5 个不支持答案、5−4=1 个不可答未拒答、25−19=6 条不支持引用，均与摘要相容；6 条引用分布于 5 题不存在算术冲突。30/30 检索证据命中与 retrieval 失败题数 0 相容。assets 的 `by_category` 是题目类别，全部为 `uncategorized`，其 20 题、16 回答、4 拒答及可答性分组均自洽；不应将它与报告的可重叠错误类别混为一谈。以上确认公开材料的可定位性与内部一致性，未独立重判逐题归因。

5. **出处、指纹与授权声明。** 第 13–19 行列出 pack/corpus、转换后 dataset、schema/config/prompt、quality config 与 runtime 脚本哈希，并写明 CodeBuddy 出题/校验、Codex runner。assets 的 dataset SHA 与报告一致；assets 中五个 `run` 字段逐项等于仓外 `collection-status-summary.json`，也均出现在报告中。第 23–24 行披露 draft peak、`verified_by=draft-not-owner-signed`、负责人授权本次使用草稿以及价格未签核。第 14、63–64 行明确同组织与同语料偏差、结果不等价于负责人 Windows 盲测。

6. **预算与采集状态。** 第 25 行与指定仓外摘要完全一致：limit 10,000,000、reserved 49,160、remaining 9,950,840 microyuan，paid/zero-price reservations 为 20/30。整数换算为 CNY 10.000000 / 0.049160 / 9.950840，余额等式成立，预留低于本次 1 CNY 停止线及项目 soft 8 / hard 10 CNY。摘要也确认第一次采集 rc=1、connection refused、预留 0，第二次 rc=0、20 题、预留 49,160；报告保留了失败尝试。摘要的价格/策略标签与报告的草稿声明相符。这里核验的是账本预留摘要，不是供应商实际结算。

7. **Git 卫生。** 实跑 `git ls-files | rg blind`，仅返回两份已跟踪的盲测协议/runbook；另以 `git ls-files -z` 检查 `.blindtest/` 与 `private-blind` 路径，0 命中，支持第 65 行的限定声明。这只证明当前索引未跟踪这些路径，不构成历史提交或所有潜在泄漏路径的全面审计。

## 方法、快照与未覆盖范围

- 只读对照 brief 指定的公开集范例、Windows runbook、holdout protocol 和仓外 `collection-status-summary.json`，并参考既有 Sol 审阅格式。使用 `python3` 在内存中执行字段、计数、比率、门禁、哈希关联及账本等式断言，23 项断言全部通过；`git diff --check` 通过。未运行采集、评分、服务或付费模型调用。
- 被审报告 SHA-256：`a045a54e5792b94dbc63e6bb98047788798f7ff759587ca890401772f8b197b2`。
- 被审 assets SHA-256：`3691e9af2e9d0e57bab6c11c4eb5cf91807f2ec9dac6a226cbbf5ac689b80a7c`。
- 未读取 `.blindtest/` 或 `/workspace/knowflow-private-blind/` 中任何内容，未读取原始题面、答案、quote、预测或审核全文。未重算私有 pack/corpus/配置文件哈希，未核验实际出题会话、负责人授权原始记录、启发式审核脚本实现、正式 runner 退出码/完成时间原始日志或远程 CI；对这些内容仅确认报告有相应声明，并在指定摘要可支持的范围内交叉核对。摘要未包含“首轮未生成预测文件”及“重启 AI”等过程细节，本次不独立证明这些细节。
- 本轮唯一仓库写入为本审阅文档；未修改两个被审文件或代码，未 commit 或 push。
