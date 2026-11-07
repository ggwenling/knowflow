# 价格与预算签核包

**用途**：供负责人快速确认评测所用价目表、预算上限，并决定签字后是否允许继续消耗。
**新基线**：评测提交 `9907aca25968ed8ad3677c1119088cfbc8166293`；其后提交 `d2b3ff1` 为采集器 sidecar，不改变本次评测产物的 `code_sha`。
**生成日期**：2026-11-07
**结论先行**：价格文件与策略文件仍为 agent 自动核价，`verified_by` 仍为 human confirmation pending；账本累计计费预留为 **CNY 3.30752**（323 笔付费、431 笔零价），已超过此前记录的“项目软目标 < CNY 2.00” **CNY 1.30752**，但未触及 soft 8 / hard 10；供应商实际账单无证据。

---

## 1. 一页签核摘要

| 项目 | 当前值 | 证据 |
|---|---|---|
| 价格文件 | `d:\konwflow\.blindtest\config\PRICE_FILE.json` | 文件存在，内容已读取 |
| 价格文件 SHA-256 | `0d6ffaf0b817e9c5dafdfb0014a22fdbbfbea0fd4ec6756787276363777a023c` | 本次重算，与上一版一致 |
| 策略文件 | `d:\konwflow\.blindtest\config\POLICY_FILE.json` | 文件存在，内容已读取 |
| 策略文件 SHA-256 | `8680a9365ce386d7d69fd803a4c2ea84dd99e1cbed0b00c11a3b1a8d439e60b8` | 本次重算，与上一版一致 |
| `verified_by`（两文件相同） | `agent:TRAE (auto-verified from official pricing page, human confirmation pending)` | 本轮未变化 |
| `verified_at`（两文件相同） | `2026-11-04T18:13:11+08:00` | 本轮未变化 |
| `valid_until`（两文件相同） | `2026-12-31T23:59:59+08:00` | 本轮未变化 |
| 运行模型 | `deepseek-flash+BAAI/bge-m3` | 两卷 `run-metadata.json` |
| 运行 `code_sha` | `9907aca25968ed8ad3677c1119088cfbc8166293` | 两卷 `run-metadata.json` |
| 运行 `config_sha256` | `20af54a4df3a20ca737801f695f4d9e11d108056b344c81a8f2b485980b1006a` | 两卷 `run-metadata.json`，与上一版一致 |
| 账本文件 | `eval-out/seed-v2-dev-9907aca/budget-ledger.sqlite3` 与 `eval-out/seed-v2-holdout-9907aca/budget-ledger.sqlite3` | 两份文件字节一致 |
| 账本 SHA-256 | `325d4b646acd85d8f592c99ea89708a299ceb73c88e7d33723ae7bc36e8470eb` | 两份文件一致 |
| 账本 hard limit | `10,000,000 microyuan` = **CNY 10.00** | 账本 `budget.limit_microyuan` |
| 账本累计计费预留 | 323 笔 × CNY 0.01024 = **CNY 3.30752** | 账本 `reservations` |
| 零价预留 | 431 笔（Embedding） | 账本 `zero_price_reservations` |
| 预算停止记录 | 0 笔 | 账本 `budget_stops` |
| 项目软目标 | `< CNY 2.00`（2026-11-05 记录） | `docs/evaluation/2026-11-05-blind-rounds-summary.md` |
| 与项目软目标差额 | **超出 CNY 1.30752** | 本节计算 |
| 供应商实际账单 | **无证据 / 待核实** | 仓库内未见账单、发票、对账记录 |

> **关键口径**：账本里的金额是“按价目表预留（reservation）”的额度，**不等于供应商实际账单**。账本没有记录每次调用的实际 token 数，也没有供应商后台账单可对账。

---

## 2. 核价依据

### 2.1 官方价目页与抓取日期

| 模型 | 供应商 | 官方价目页 | 文件记录抓取日期 | 复核日期 |
|---|---|---|---|---|
| `deepseek-flash` | deepseek | https://api-docs.deepseek.com/zh-cn/quick_start/pricing | `2026-11-04T18:13:11+08:00` | 2026-11-07 |
| `BAAI/bge-m3` | siliconflow | https://siliconflow.cn/pricing | `2026-11-04T18:13:11+08:00` | 2026-11-07 |

> 本轮未发现新的价格证据，PRICE / POLICY 哈希与 `verified_by` 保持原值；上表复核日期沿用 2026-11-07 已完成的官方页复核。

### 2.2 各模型单价

| 模型 | 输入单价 | 输出单价 | 本次计算采用 | 说明 |
|---|---|---|---|---|
| `deepseek-flash` | CNY 1 / 百万 tokens（缓存未命中）；缓存命中 CNY 0.02 / 百万 tokens | CNY 2 / 百万 tokens | 输入按缓存未命中 CNY 1 / M；输出按 CNY 2 / M | 取较高价，属保守预留；未采用缓存命中价 |
| `BAAI/bge-m3` | CNY 0（官方页显示“免费”） | CNY 0 | CNY 0 | 431 笔零价预留与之一致 |

> 官方页当前展示的模型名为 `deepseek-v4-flash`（输入缓存未命中 CNY 1 / M、缓存命中 CNY 0.02 / M、输出 CNY 2 / M）。`PRICE_FILE.json` 使用别名 `deepseek-flash`，单价数值一致；**别名与官方模型名的映射关系待核实**。

### 2.3 策略文件中的计费上限

| 模型 | `input_tokens_upper` | `output_tokens_upper` | `max_payload_bytes` | `bound_kind` | 说明 |
|---|---|---|---|---|---|
| `deepseek-flash` | 8192 | 1024 | 65536 | `provider_context_limit` | 该值远低于官方页展示的 1M 上下文 / 384K 最大输出，实际是保守的内部预留上限；`bound_kind` 标签与官方上下文限制不一致，**待核实** |
| `BAAI/bge-m3` | 32768 | 0 | 131072 | `provider_context_limit` | 零价模型，预留金额恒为 0 |

来源：`POLICY_FILE.json`；官方上下文/输出上限来自 2026-11-07 复核的 DeepSeek 价目页。

---

## 3. 计算过程与账本对齐

### 3.1 单次 DeepSeek 预留

```text
输入：8192 tokens × CNY 1 / 1,000,000 = CNY 0.008192
输出：1024 tokens × CNY 2 / 1,000,000 = CNY 0.002048
单次合计：CNY 0.01024
```

### 3.2 账本累计

```text
DeepSeek 计费预留：323 笔 × CNY 0.01024 = CNY 3.30752
Embedding 零价预留：431 笔 × CNY 0 = CNY 0
账本累计：CNY 3.30752
```

### 3.3 与账本数据库逐项对齐

| 账本字段 | 实测值 | 按价目表推算 | 是否一致 |
|---|---|---|---|
| `budget.limit_microyuan` | 10,000,000 | CNY 10.00 | 一致（hard 上限） |
| `reservations` 笔数 | 323 | — | — |
| `reservations.microyuan` 单笔 | 10,240 | CNY 0.01024 | 一致 |
| `reservations.microyuan` 合计 | 3,307,520 | CNY 3.30752 | 一致 |
| `reservations.input_tokens_upper` | 8192 | POLICY 上限 | 一致 |
| `reservations.output_tokens_upper` | 1024 | POLICY 上限 | 一致 |
| `zero_price_reservations` 笔数 | 431 | — | — |
| `zero_price_reservations` 单价 | 0 | BAAI/bge-m3 免费 | 一致 |
| `budget_stops` | 0 笔 | 未触发 soft/hard 停止 | 一致 |

> 账本中的 `price_quote` 与当前 `PRICE_FILE.json` 的 `provider`、`model`、`input_cny_per_million`、`output_cny_per_million`、`source_url`、`valid_until`、`verified_at`、`verified_by` 字段一致。

---

## 4. 账本累计与今天各轮明细

### 4.1 口径说明

- 账本 `reservations` / `zero_price_reservations` **没有时间戳字段**，无法直接按行归属到某一轮。
- 下表按“各轮目录账本快照的请求 ID 集合增量 + 目录修改时间”归属：
  - 请求 ID 在后续快照中只增不减；
  - `seed-v2-dev-9907aca` 与 `seed-v2-holdout-9907aca` 的账本文件字节一致（SHA-256 `325d4b64…`），说明两者是同一累计账本的同一最终快照。
- 每个“增量”等于该轮新增的计费预留笔数；每笔按 CNY 0.01024 计。

### 4.2 各轮明细

| 轮次 | 目录 | 目录时间 | 累计快照（计费预留笔数） | 本轮增量（笔） | 本轮增量金额（CNY） | 累计金额（CNY） |
|---|---|---|---:|---:|---:|---:|
| 基线（非今天） | `seed-v2-dev` | 2026-11-06 23:07:06 | 40 | 40 | 0.40960 | 0.40960 |
| 今天第 1 轮 | `seed-v2-dev-rerun-53f8b9ea` | 2026-11-07 13:17:16 | 81 | 41 | 0.41984 | 0.82944 |
| 今天第 2 轮 | `seed-v2-dev-run3-40f4b838` | 2026-11-07 13:29:27 | 121 | 40 | 0.40960 | 1.23904 |
| 今天第 3 轮 | `seed-v2-holdout-40f4b838` | 2026-11-07 13:36:32 | 141 | 20 | 0.20480 | 1.44384 |
| 今天第 4 轮 | `seed-v2-dev-0.2.0` + `seed-v2-holdout-0.2.0` | 2026-11-07 14:58:55 | 201 | 60 | 0.61440 | 2.05824 |
| 今天第 5 轮（作废批次） | `seed-v2-dev-42d3b3d` + `seed-v2-holdout-42d3b3d` | 2026-11-07 18:58:06 | 262 | 61 | 0.62464 | 2.68288 |
| 今天第 6 轮（正式补跑） | `seed-v2-dev-9907aca` + `seed-v2-holdout-9907aca` | 2026-11-07 19:17:12 | 323 | 61 | 0.62464 | **3.30752** |
| **今天合计（第 1–6 轮）** | — | — | — | **283** | **2.89792** | — |
| **账本累计（含 11-06 基线）** | — | — | **323** | — | — | **3.30752** |

补充：

- 今天第 4 轮的 60 笔 = development 40 题 + holdout 20 题；与两卷 `metrics.json` 的 `sample_count=40` / `20` 一致。
- 今天第 5 轮为 **provider 故障窗口的作废批次**：`seed-v2-dev-42d3b3d` 有 13 题、`seed-v2-holdout-42d3b3d` 有 20 题记录为 `COLLECTION_INCOMPLETE`，两卷 `predictions.status.json` 的 `complete=false`，且没有 `metrics.json`；该批次 **未计入结论**。
- 今天第 6 轮为覆盖引用粒度修复的正式补跑：两卷 `metrics.json` 均 `passed`，`execution_error_count=0`。
- 今天第 1 轮 41 笔、第 5/6 轮各 61 笔，分别比对应题数多 1 笔；账本本身不能说明多出的是重试还是额外调用，**待核实**。
- 零价预留 431 笔（Embedding）不计入金额；其快照增量与计费预留同步增长。

### 4.3 为什么超出项目软目标 2.00

| 组成 | 金额（CNY） | 说明 |
|---|---:|---|
| 到 `0.2.0` 为止的累计 | 2.05824 | 已超 2.00 共 0.05824 |
| 引用粒度修复正式补跑（`9907aca`） | +0.62464 | 为覆盖句级 locator 修复补跑一轮完整评测 |
| provider 故障窗口作废批次（`42d3b3d`） | +0.62464 | 未计入结论，但仍计入账本预留 |
| **累计** | **3.30752** | **超出 2.00 共 1.30752** |

### 4.4 与预算阈值的关系

| 阈值 | 金额（CNY） | 当前累计（CNY） | 占用比例 | 剩余（CNY） |
|---|---:|---:|---:|---:|
| 项目软目标（2026-11-05 记录） | 2.00 | 3.30752 | 165.4% | **-1.30752（已超）** |
| soft stop | 8.00 | 3.30752 | 41.3% | 4.69248 |
| hard limit（账本） | 10.00 | 3.30752 | 33.1% | 6.69248 |

- 账本 `budget_stops=0`，说明本次没有被代码层 soft/hard 门禁拦下。
- 2026-11-05 曾记录另一个账本累计 `2.684136 CNY` 的闲置进程事件（`docs/evaluation/2026-11-05-blind-rounds-summary.md`）；该金额**不在本账本 323 笔内**，是否存在其他未纳入账本的消耗**待核实**。

---

## 5. 需要负责人决定的事项

### 5.1 价格确认

- 是否认可 `deepseek-flash` 按官方 `deepseek-v4-flash` 缓存未命中价 CNY 1 / M、输出 CNY 2 / M 计费。
- 是否认可 `BAAI/bge-m3` 按免费计费。
- 是否认可“取缓存未命中高价、按 POLICY 上限 8192/1024 预留”的保守口径。
- 本轮 PRICE / POLICY 的 SHA-256 与 `verified_by` 均未变化；若负责人认可，需在签字后将 `verified_by` 更新为具名负责人（本文件不修改配置文件）。

### 5.2 预算上限确认

当前存在两套口径，需要明确以哪一套为准：

| 口径 | 金额 | 状态 | 签字选择 |
|---|---:|---|---|
| 项目软目标 | CNY 2.00 | 已超出 CNY 1.30752 | □ 维持，需补充授权后才可继续 |
| soft stop | CNY 8.00 | 未触及，剩余 CNY 4.69248 | □ 作为继续消耗的提醒线 |
| hard limit | CNY 10.00 | 未触及，剩余 CNY 6.69248 | □ 作为继续消耗的硬上限 |

### 5.3 签字后是否允许继续消耗

| 选项 | 说明 | 勾选 |
|---|---|---|
| 允许继续 | 以 hard CNY 10.00 为上限，当前剩余 CNY 6.69248 | □ |
| 允许继续但附条件 | 例如先追加授权覆盖项目软目标超出部分 CNY 1.30752，或设定新的单轮上限：______ | □ |
| 暂停 | 签字后不再发起任何真实模型调用，直至另行批准 | □ |

> 无论选择哪一项，都建议同时确认：供应商后台是否有独立于本地账本的硬支出上限；本账本只是本地预留，不是供应商侧限额。作废批次 `42d3b3d` 的 CNY 0.62464 是否应从未来预算口径中剔除，也需要负责人明确。

---

## 6. 签字栏

| 字段 | 填写 |
|---|---|
| 负责人（姓名 / 角色） | |
| 日期 | |
| 价格结论 | □ 认可价目表与单价　□ 不认可　□ 有条件认可（见备注） |
| 预算上限结论 | □ 以 hard CNY 10.00 为准　□ 以项目软目标 CNY 2.00 为准　□ 其他：______ |
| 签字后是否允许继续消耗 | □ 允许　□ 允许但附条件　□ 暂停 |
| 允许的上限 / 追加授权金额 | CNY ______ |
| 作废批次 CNY 0.62464 是否剔除 | □ 是　□ 否 |
| 是否要求供应商账单对账后再签字 | □ 是　□ 否 |
| 异议 / 备注 | |
| 签字 | |

---

## 7. 待核实清单

以下事项现有事实不足，未做推测：

1. 供应商实际账单 / 发票 / 后台用量：仓库内无证据，账本金额不能等同于实际账单。
2. `deepseek-flash` 与官方 `deepseek-v4-flash` 的别名映射：官方页未直接展示 `deepseek-flash` 名称。
3. `POLICY_FILE.json` 的 `bound_kind=provider_context_limit` 与官方 1M 上下文 / 384K 输出不一致；8192/1024 更像是内部保守上限。
4. `run-metadata.json` 的 `config_sha256=20af54a4…` 与两个配置文件的单文件 SHA-256 不等价；其组合口径和是否确由这两个文件生成，仓库内未见生成脚本。
5. 账本无时间戳，今天各轮的金额归属是按请求 ID 增量与目录时间推断，不是账本原生字段。
6. 今天第 1 轮 41 笔、第 5/6 轮各 61 笔的具体原因（比对应题数各多 1 笔）。
7. 2026-11-05 另一账本的 CNY 2.684136 事件是否还有未纳入本账本的消耗。
8. “项目软目标 < CNY 2.00”的授权范围（仅 Phase 1+2，还是覆盖本账本全部轮次）需要负责人确认。
9. `42d3b3d` 作废批次被归因为 provider 故障窗口；产物侧证据是 `complete=false` 与 `COLLECTION_INCOMPLETE`，具体 provider 故障记录待核实。
10. 作废批次 CNY 0.62464 是否应从预算考核中剔除，尚未有书面口径。

---

## 8. 证据路径

| 内容 | 路径 |
|---|---|
| 价格文件 | `.blindtest/config/PRICE_FILE.json` |
| 策略文件 | `.blindtest/config/POLICY_FILE.json` |
| development 账本 | `eval-out/seed-v2-dev-9907aca/budget-ledger.sqlite3` |
| holdout 账本 | `eval-out/seed-v2-holdout-9907aca/budget-ledger.sqlite3` |
| development 运行元数据 | `eval-out/seed-v2-dev-9907aca/run-metadata.json` |
| holdout 运行元数据 | `eval-out/seed-v2-holdout-9907aca/run-metadata.json` |
| development 指标 | `eval-out/seed-v2-dev-9907aca/metrics.json` |
| holdout 指标 | `eval-out/seed-v2-holdout-9907aca/metrics.json` |
| 作废批次（不使用） | `eval-out/seed-v2-dev-42d3b3d/`、`eval-out/seed-v2-holdout-42d3b3d/` |
| 项目软目标与 11-05 账本事件 | `docs/evaluation/2026-11-05-blind-rounds-summary.md` |
| 交付清单中的价格/预算缺口 | `docs/planning/2026-11-07-deliverable-checklist.md`（第 3 节） |

> 本文件只做记录，不修改代码、不修改评测产物、不修改配置文件。
