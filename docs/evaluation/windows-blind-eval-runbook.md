# Windows 本地盲测评测 Runbook（负责人执行）

本 runbook 只在负责人 Windows 机器上使用。盲测包必须放在**仓库根目录**下的 `.blindtest/`（已 gitignore），例如 `D:\konwflow\knowflow\.blindtest\`。**不要**使用仓库旁的兄弟目录 `D:\konwflow\.blindtest\`——当前转换器与采集器都按 `<repo>\.blindtest` 校验路径。

不得把题面、答案、预测全文或密钥复制进 git，也不得粘贴到聊天。

## 前置条件

- 已安装：JDK 21、Python 3.12（仓库 `services\ai\.venv`）、PostgreSQL+pgvector、MinIO；Java API 可在本机 `:8080` 健康检查通过。
- 仓库检出约定 SHA（如 `grok`），工作树干净。
- 目录布局（固定）：

```text
<repo>\                          # 例：D:\konwflow\knowflow
  .blindtest\                    # 私有包根（gitignore）
    COMMITMENT.txt
    questions.json
    corpus.json
    config\                      # 可选：签核版 PRICE/POLICY、gate.json
      PRICE_FILE.json
      POLICY_FILE.json
      gate.json
    out\                         # 运行产物（gitignore）
      runner\                    # private_pack_to_runner 输出
      budget-ledger.sqlite3
      predictions.json
      predictions.diagnostics.json  # 每题剪枝原因码（无题面/答案）
      run-metadata.json
      review-template.json
      review.json
      metrics.json
  evaluation\...
```

- PowerShell 环境变量（**不要**把值写入仓库或截图）：

```powershell
cd D:\konwflow\knowflow   # 换成真实仓库根
$env:DEEPSEEK_API_KEY = "<from vault>"
$env:EMBEDING_KEY = "<from vault>"
$env:KNOWFLOW_BUDGET_LEDGER_PATH = "$PWD\.blindtest\out\budget-ledger.sqlite3"
$env:KNOWFLOW_BUDGET_PRICE_FILE = "$PWD\.blindtest\config\PRICE_FILE.json"    # 负责人签核版
$env:KNOWFLOW_BUDGET_POLICY_FILE = "$PWD\.blindtest\config\POLICY_FILE.json"
$env:KNOWFLOW_INTERNAL_SHARED_SECRET = "<local>"
$env:KNOWFLOW_EVALUATION_CONTROL_SECRET = "<local >=32 chars>"
# 另配 KNOWFLOW_AI_DATABASE_URL、Java/DB/MinIO 角色密码等，同本地开发
```

- BudgetLedger soft **CNY 8** / hard **CNY 10**：累计预留到 8 必须停。
- 补问默认关闭。若在 holdout 核对 `unanswerable` 拒答表现后选择显式启用（`KNOWFLOW_ANSWER_REPAIR=on`），每题最多 **2 次 DeepSeek 尝试**：1 次生成 + 至多 1 次引用补问。补问只发生在「模型自称有答案、但引用校验把答案剪空」的题上，仍按 policy 上界预约。若评测选择开启，按 CNY 估算整个包时按每题 2 次生成预留留量，不要用单次价乘题数。

## 1. 适配私有包 → runner 输入

转换器**没有** `--input` / `--output`。它固定读取 `<repo>\.blindtest`，并写入 `<repo>\.blindtest\out\runner`。可选 `--source-root` 仅用于解析 `corpus.json` 里的语料相对路径（默认即仓库根）。

```powershell
cd D:\konwflow\knowflow
# 确保 .blindtest\out\runner 尚不存在（转换器拒绝覆盖）
.\services\ai\.venv\Scripts\python.exe evaluation\adapters\private_pack_to_runner.py
# 若语料不在仓库根而在其它已授权根目录：
# .\services\ai\.venv\Scripts\python.exe evaluation\adapters\private_pack_to_runner.py --source-root D:\path\to\corpus-root
```

成功时 stdout 仅为 JSON counts / `dataset_sha256`，不打印题面。

## 2. 启动本机 Java + 真实评测 AI

```powershell
# 先起 PG / MinIO / Java（习惯端口 55432 / 59000 / 8080），确认：
# Invoke-WebRequest http://127.0.0.1:8080/actuator/health
.\services\ai\.venv\Scripts\python.exe evaluation\collector\real_service.py
# 监听 127.0.0.1:8000；缺 env 会 fail-closed，错误只含变量名
```

## 3. 采集（协议规定的 split，私有包转换后为 holdout）

`run-metadata.json` 必填：`code_sha`、`schema_sha256`、`config_sha256`、`prompt_sha256`、`model`（均为真实指纹，勿编造）。

```powershell
$code = (git rev-parse HEAD).Trim()
$schema = (Get-FileHash contracts\schemas\protocol.schema.json -Algorithm SHA256).Hash.ToLower()
# config/prompt：对实际使用的签核 PRICE+POLICY 字节与产品 prompt 字节分别做 SHA-256
$model = "deepseek-flash+BAAI/bge-m3"
# 将上述字段写入 .blindtest\out\run-metadata.json

$env:KNOWFLOW_EVALUATION_ACCESS_TOKEN = "<owner bearer>"
$env:KNOWFLOW_EVALUATION_DATABASE_URL = "postgresql://knowflow_app:<pwd>@127.0.0.1:55432/knowflow"

.\services\ai\.venv\Scripts\python.exe evaluation\collector\run.py `
  --dataset "$PWD\.blindtest\out\runner" `
  --split holdout `
  --output "$PWD\.blindtest\out\predictions.json" `
  --run-metadata "$PWD\.blindtest\out\run-metadata.json"
```

`privacy=local_only` 时，`--output` 必须落在 `<repo>\.blindtest\out\` 下，否则采集以 `PRIVATE_OUTPUT_OUTSIDE_IGNORED_DIRECTORY` 拒绝。

## 4. 人工审核与门禁

生成审核模板（未传 `--review` 时写模板；参数名是 `--output`，**不是** `--prepare`）：

```powershell
.\services\ai\.venv\Scripts\python.exe evaluation\runner\review_predictions.py `
  --predictions "$PWD\.blindtest\out\predictions.json" `
  --dataset "$PWD\.blindtest\out\runner" `
  --split holdout `
  --output "$PWD\.blindtest\out\review-template.json"
```

在仓库外完成 support / citation 判断后，保存为 `.blindtest\out\review.json`，再跑正式门禁（**必须**提供 `--output`；原始评分含逐题结果，留在私有目录）：

```powershell
.\services\ai\.venv\Scripts\python.exe evaluation\runner\runner.py `
  --predictions "$PWD\.blindtest\out\predictions.json" `
  --dataset "$PWD\.blindtest\out\runner" `
  --split holdout `
  --quality-config "$PWD\.blindtest\config\gate.json" `
  --review "$PWD\.blindtest\out\review.json" `
  --output "$PWD\.blindtest\out\metrics.json" `
  --formal
```

## 5. 只提交聚合

允许提交到 git：

- 指标表、门禁通过/失败、账本 `summary`（microyuan/CNY）、模型 id、code/config/schema/prompt SHA、PRICE/POLICY **文件哈希与 verified_by**（不要提交密钥或题面）。
- 报告路径建议：`docs/evaluation/YYYY-MM-DD-rag-real-blind.md`。

禁止：`predictions.json`、审核原文、`.blindtest/**` 下任何文件、密钥、完整预测/逐题 `question_results`。

## 6. 失败时

- 若 soft stop：立刻停，报告累计预留与最后一步。
- 诊断仅基于聚合错误码与指标（retrieval vs refusal），不要为调试把盲题贴进聊天。
