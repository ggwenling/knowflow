# 答案支持度与引用真人审阅（2026-11-08）

状态：**工作表已生成；真人逐条审阅与签字待负责人完成**。现有 `review.json` 的 `reviewed_by` 仍为 agent，不能当作人工签收。

## 1. 审阅对象

| 分卷 | 答案数 | answered | refused | 引用数 | 工作表行数 |
|---|---:|---:|---:|---:|---:|
| development（`9907aca`） | 40 | 31 | 9 | 47 | 56 |
| holdout（`9907aca`） | 20 | 18 | 2 | 28 | 30 |

来源：

- `eval-out/seed-v2-dev-9907aca/review.json`
- `eval-out/seed-v2-holdout-9907aca/review.json`

这些是公开合成集结果，不是私有盲测。不要用本工作表替代私有盲测。

## 2. 生成工作表

```powershell
python scripts/prepare-citation-review.py
```

输出（不纳入版本库）：

- `eval-out/citation-review-20261108/development.csv`
- `eval-out/citation-review-20261108/holdout.csv`
- `eval-out/citation-review-20261108/summary.json`

## 3. CSV 字段与填写规则

| 字段 | 说明 |
|---|---|
| `answer` / `answer_sha256` | 待审答案与其哈希；审阅期间不得改动 |
| `agent_support` | 机器判断，仅供对照，不作为人工结论 |
| `claim` / `source_text` | 引用声明与对应原文片段 |
| `human_support` | `supported` / `not_supported` / `uncertain`；refused 行填 `refusal_correct` / `refusal_incorrect` |
| `human_citation` | `correct` / `incorrect` / `uncertain`；refused 行留空 |
| `human_notes` | 判定理由；不可只写“ok” |
| `reviewer` | 真实审阅者标识（不得使用 agent 前缀） |
| `reviewed_at` | 带时区的 ISO 时间，例如 `2026-11-08T15:00:00+08:00` |

规则：

- 每条 answered 引用都要独立判断 claim 是否被 `source_text` 支持；不能只看答案整体。
- refused 行判断“拒答是否合理”，引用列留空。
- 不确定时填 `uncertain` 并在 notes 写明缺什么证据。
- 不得修改 `review.json`、`predictions.json` 或原始材料。

## 4. 校验

```powershell
python scripts/validate-citation-review.py
```

校验内容：

- 每一行都有 reviewer、reviewed_at、human_support；
- answered 行都有 human_citation 与 notes；
- refused 行的引用列必须为空；
- 取值在允许集合内；
- 输出覆盖率与计数；不完整时退出码非零。

校验通过后，负责人再决定是否生成独立的人工 review JSON 并重跑指标。生成新文件时不得覆盖原 `review.json`。

## 5. 签字

| 分卷 | 审阅者 | 日期 | 覆盖 | 结论 | 证据路径 |
|---|---|---|---|---|---|
| development |  |  | 31 answered / 47 citations / 9 refused |  |  |
| holdout |  |  | 18 answered / 28 citations / 2 refused |  |  |

签字栏为空，直到真实审阅完成。

## 6. 不能由本文件替代的事项

- 私有盲测（独立题集、独立评分、失败后换集）；
- PRICE/POLICY 与预算签核；
- M 线浏览器人工验收；
- 三端完整消费签收与总体验收。
