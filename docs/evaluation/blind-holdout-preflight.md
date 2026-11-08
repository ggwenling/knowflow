# 私有盲测 Preflight（2026-11-08）

状态：**脚本已准备；未执行、未读取私有题集**。

## 1. 原则

- 私有盲测题集、答案和资料由负责人在仓库外受控保管；AI/本仓库不得读取或提交题面。
- 公开 60 题、开发/验证集和已看过的样本不能充作盲测。
- 失败后不得在同一题集反复调参；必须换新独立题集。
- 预算必须经 PRICE/POLICY 批准；本地账本不是供应商硬 cap。

## 2. 前置条件

| 条件 | 证据 |
|---|---|
| 新独立题集（未参与调参） | 题集 SHA-256、封存记录、创建日期 |
| 与公开集无重叠 | preflight 的 overlap 检查 |
| PRICE/POLICY 已签核 | 文件路径、哈希、签字 |
| 评分者独立 | 评分者身份与隔离声明 |
| 运行环境隔离 | 独立 DB/对象存储、无历史数据 |
| 预算与停止条件 | 上限、超额拒绝、告警 |

## 3. Preflight 命令（由题集保管人执行）

```powershell
python scripts/blind-preflight.py `
  --dataset "<仓库外路径>/blind-questions.json" `
  --expected-sha256 "<题集 SHA-256>" `
  --public-dataset "evaluation/data/qingzhu-seed-v2-reviewed.json" `
  --price "<仓库外路径>/PRICE_FILE.json" `
  --policy "<仓库外路径>/POLICY_FILE.json" `
  --out "eval-out/blind-preflight-20261108.json"
```

脚本只做：

- 文件存在与 SHA-256 匹配；
- JSON 结构可解析；
- 与公开集题面哈希是否重叠；
- PRICE/POLICY 是否存在、`verified_by` 是否仍为 pending；
- 仓库内不得存在 `.blindtest/`；
- 输出 pass/fail 与原因。

脚本**不**打印题面、答案或资料内容；输出只含计数、哈希前缀与布尔结果。

## 4. 通过标准

- 所有检查 pass；
- 题集与公开集零重叠；
- PRICE/POLICY 已由负责人签核；
- 预算硬上限或批准的软政策已记录；
- 独立评分者与运行环境已确认。

任何一项失败：停止运行，不要用同一题集调参。

## 5. 运行后证据

- 运行配置哈希、代码 SHA、模型 profile；
- 题集 SHA-256、评分者、时间；
- 指标与门槛结果；
- 失败样本与误拒答清单（不含题面全文，除非仓库外受控）；
- 预算账本与停止事件。

## 6. 未完成

- 新独立题集：无。
- 独立评分者：未指定。
- 盲测执行与质量门：未通过（v5 answerable 0.800）。
