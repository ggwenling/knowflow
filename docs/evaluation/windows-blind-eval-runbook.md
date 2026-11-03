# Windows 本地盲测评测 Runbook（负责人执行）

本 runbook 只在负责人 Windows 机器上使用。盲测资料位于 `D:/konwflow/.blindtest/`（或当前仓库旁的 `.blindtest/`），**不得**复制题面/答案进 git，也不得粘贴到聊天。

## 前置条件

- 已安装：JDK 21、Python 3.12、PostgreSQL+pgvector、MinIO（或沿用本机 compose）。
- 仓库检出 `grok`（或验收约定的 SHA），工作树干净。
- 环境变量（PowerShell，**不要**把值写入仓库或截图）：

```powershell
$env:DEEPSEEK_API_KEY = "<from vault>"
$env:EMBEDING_KEY = "<from vault>"
$env:KNOWFLOW_BUDGET_LEDGER_PATH = "D:\konwflow\.blindtest\out\budget-ledger.sqlite3"
$env:KNOWFLOW_BUDGET_PRICE_FILE = "D:\konwflow\.blindtest\config\PRICE_FILE.json"   # 负责人签核版
$env:KNOWFLOW_BUDGET_POLICY_FILE = "D:\konwflow\.blindtest\config\POLICY_FILE.json"
$env:KNOWFLOW_INTERNAL_SHARED_SECRET = "<local>"
$env:KNOWFLOW_EVALUATION_CONTROL_SECRET = "<local >=32 chars>"
# 以及 Java/DB/MinIO/AI 角色密码与 KNOWFLOW_AI_DATABASE_URL 等，同本地开发
```

- BudgetLedger soft **CNY 8** / hard **CNY 10**：累计预留到 8 必须停。

## 1. 适配私有包 → runner 输入

在仓库根：

```powershell
cd D:\konwflow\knowflow   # 按实际路径
.\services\ai\.venv\Scripts\python.exe evaluation\adapters\private_pack_to_runner.py `
  --input D:\konwflow\.blindtest\pack `
  --output D:\konwflow\.blindtest\out\runner
```

成功时只打印 counts / dataset hash。输出必须落在忽略目录 `.blindtest/out/`。

## 2. 启动本机 Java + 真实评测 AI

```powershell
# 先起 PG/MinIO/Java（端口习惯：55432 / 59000 / 8080）
.\services\ai\.venv\Scripts\python.exe evaluation\collector\real_service.py
# 监听 127.0.0.1:8000；缺 env 会 fail-closed，错误只含变量名
```

## 3. 采集（development 或协议规定的 split）

准备 `run-metadata.json`（真实 SHA，勿编造）：

```powershell
# run-metadata.json 必填字段（值须为真实指纹，勿编造）：
#   code_sha, schema_sha256, config_sha256, prompt_sha256, model
# 示例（PowerShell）：
$code = (git rev-parse HEAD).Trim()
$schema = (Get-FileHash contracts\schemas\protocol.schema.json -Algorithm SHA256).Hash.ToLower()
# config/prompt：对实际使用的价格+策略字节与产品 prompt 字节做 SHA-256
$model = "deepseek-flash+BAAI/bge-m3"
```

```powershell
$env:KNOWFLOW_EVALUATION_ACCESS_TOKEN = "<owner bearer>"
$env:KNOWFLOW_EVALUATION_DATABASE_URL = "postgresql://knowflow_app:<pwd>@127.0.0.1:55432/knowflow"
.\services\ai\.venv\Scripts\python.exe evaluation\collector\run.py `
  --dataset D:\konwflow\.blindtest\out\runner `
  --split holdout `
  --output D:\konwflow\.blindtest\out\predictions.json `
  --run-metadata D:\konwflow\.blindtest\out\run-metadata.json
```

## 4. 人工审核与门禁

```powershell
.\services\ai\.venv\Scripts\python.exe evaluation\runner\review_predictions.py `
  --predictions D:\konwflow\.blindtest\out\predictions.json `
  --dataset D:\konwflow\.blindtest\out\runner `
  --split holdout `
  --prepare D:\konwflow\.blindtest\out\review-template.json
# 在仓库外填写 support/citation judgements 后：
.\services\ai\.venv\Scripts\python.exe evaluation\runner\runner.py `
  --predictions D:\konwflow\.blindtest\out\predictions.json `
  --dataset D:\konwflow\.blindtest\out\runner `
  --split holdout `
  --quality-config D:\konwflow\.blindtest\config\gate.json `
  --review D:\konwflow\.blindtest\out\review.json `
  --formal
```

## 5. 只提交聚合

允许提交到 git 的内容：

- 指标表、门禁通过/失败、账本 `summary`（microyuan/CNY）、模型 id、code/config/schema/prompt SHA、PRICE/POLICY **文件哈希与 verified_by**（不要提交密钥或题面）。
- 报告路径建议：`docs/evaluation/YYYY-MM-DD-rag-real-blind.md`。

禁止：预测 JSON、审核原文、`.blindtest/**` 下任何文件、密钥、完整 PRICE 若含不应公开的账号信息。

## 6. 失败时

- 若 soft stop：立刻停，报告累计预留与最后一步。
- 诊断仅基于聚合错误码与指标（retrieval vs refusal），不要为调试把盲题贴进聊天。
