# Windows 本地盲测评测 Runbook（负责人执行）

本 runbook 只在负责人 Windows 机器上使用。盲测包必须放在**包含该包的 Git 仓库根目录**下的 `.blindtest/`（已 gitignore）。用户给定的 `D:\konwflow\.blindtest\` 只有在 `D:\konwflow` 本身是 Git 根目录时才有效；若代码运行在隔离 worktree，可通过 `--pack-root` 指向该包。转换结果、预测、审核和指标仍须写入同一 `.blindtest\out\`。

不得把题面、答案、预测全文或密钥复制进 git，也不得粘贴到聊天。

## 前置条件

- 已安装：JDK 21、Python 3.12（仓库 `services\ai\.venv`）、PostgreSQL+pgvector、MinIO；Java API 可在本机 `:8080` 健康检查通过。
- 仓库检出约定 SHA（如 `grok`），工作树干净。
- 目录布局（固定）：

```text
<repo>\                          # 例：D:\konwflow
  .blindtest\                    # 私有包根（gitignore）
    COMMITMENT.txt
    questions.json
    corpus.json
    config\                      # 正式评测必需：负责人签核版 PRICE/POLICY、数据集绑定 gate.json
      PRICE_FILE.json
      POLICY_FILE.json
      gate.json
    out\                         # 运行产物（gitignore）
      runner\                    # private_pack_to_runner 输出
      budget-ledger.sqlite3
      predictions.json
      run-metadata.json
      review-template.json
      review.json
      metrics.json
  evaluation\...
```

- PowerShell 环境变量（**不要**把值写入仓库或截图）：

```powershell
# 先进入包含已审查 SHA 的工作树（可为隔离 worktree），然后：
$repo = (git rev-parse --show-toplevel).Trim()
$pack = "D:\konwflow\.blindtest"               # 用户指定的盲测包
Set-Location $repo
New-Item -ItemType Directory -Force -Path "$pack\config", "$pack\out" | Out-Null
$env:DEEPSEEK_API_KEY = "<from vault>"
$env:EMBEDING_KEY = "<from vault>"
$env:KNOWFLOW_EMBEDDING_KEY_ENV = "EMBEDING_KEY"
$env:KNOWFLOW_EMBEDDING_BASE_URL = "https://api.siliconflow.cn/v1"
$env:KNOWFLOW_EMBEDDING_MODEL = "BAAI/bge-m3"
$env:KNOWFLOW_EMBEDDING_DIMENSIONS = "1024"
$env:KNOWFLOW_LLM_KEY_ENV = "DEEPSEEK_API_KEY"
$env:KNOWFLOW_LLM_BASE_URL = "https://api.deepseek.com"
$env:KNOWFLOW_LLM_MODEL = "deepseek-flash"
$env:KNOWFLOW_BUDGET_LEDGER_PATH = "$pack\out\budget-ledger.sqlite3"
$env:KNOWFLOW_BUDGET_PRICE_FILE = "$pack\config\PRICE_FILE.json"    # 负责人签核版
$env:KNOWFLOW_BUDGET_POLICY_FILE = "$pack\config\POLICY_FILE.json"
$env:KNOWFLOW_INTERNAL_SHARED_SECRET = "<local>"
$env:KNOWFLOW_EVALUATION_CONTROL_SECRET = "<local >=32 chars>"
# 另配 KNOWFLOW_AI_DATABASE_URL、Java/DB/MinIO 角色密码等，同本地开发
```

- BudgetLedger soft **CNY 8** / hard **CNY 10**：累计预留到 8 必须停。
- 负责人签核的 PRICE/POLICY 文件必须已放在 `$pack\config`；当前缺文件或文件标记为 draft/unsigned 时，真实服务会 fail-closed。不得把草稿改名为正式文件。

## 1. 适配私有包 → runner 输入

转换器默认读取脚本仓库的 `.blindtest`，也可用 `--pack-root` 指向用户授权的另一个 Git 根目录下 `.blindtest`。它写入该包自己的 `out\runner`；`--source-root` 指语料相对路径的根目录（默认是私有包所在仓库）。

```powershell
$repo = (git rev-parse --show-toplevel).Trim()   # 当前代码仓库或隔离 worktree
$pack = "D:\konwflow\.blindtest"               # 用户指定的盲测包
Set-Location $repo
# 确保 .blindtest\out\runner 尚不存在（转换器拒绝覆盖）
.\services\ai\.venv\Scripts\python.exe evaluation\adapters\private_pack_to_runner.py `
  --pack-root $pack `
  --source-root (Split-Path $pack -Parent)
```

成功时 stdout 仅为 JSON counts / `dataset_sha256`，不打印题面。

## 2. 启动本机 Java + 真实评测 AI

```powershell
# PG / MinIO / Java 应已启动（常用端口 55432 / 59000 / 8080）。
# 本窗口设置 $repo、$pack，重新注入第 0 节全部变量、KNOWFLOW_AI_DATABASE_URL 和 Java/DB 连接变量；
# PowerShell 环境变量不会自动从其他终端继承。
.\services\ai\.venv\Scripts\python.exe evaluation\collector\real_service.py
# 监听 127.0.0.1:8000；缺 env 会 fail-closed，错误只含变量名
```

## 3. 采集（协议规定的 split，私有包转换后为 holdout）

另开采集窗口，设置 `$repo`、`$pack` 并重新注入 `KNOWFLOW_EVALUATION_ACCESS_TOKEN`、`KNOWFLOW_EVALUATION_DATABASE_URL`、`KNOWFLOW_INTERNAL_SHARED_SECRET`、`KNOWFLOW_EVALUATION_CONTROL_SECRET`，以及第 0 节的 PRICE/POLICY 路径。`run-metadata.json` 必填：`code_sha`、`schema_sha256`、`config_sha256`、`prompt_sha256`、`model`（均为真实指纹，勿编造）。

```powershell
$repo = (git rev-parse --show-toplevel).Trim()
$pack = "D:\konwflow\.blindtest"
Set-Location $repo
$code = (git -C $repo rev-parse HEAD).Trim()
$schema = (Get-FileHash contracts\schemas\protocol.schema.json -Algorithm SHA256).Hash.ToLower()
# config/prompt：对实际使用的签核 PRICE+POLICY 字节与产品 prompt 字节分别做 SHA-256
$model = "deepseek-flash+BAAI/bge-m3"
# 将上述字段写入 $pack\out\run-metadata.json

$env:KNOWFLOW_EVALUATION_ACCESS_TOKEN = "<owner bearer>"
$env:KNOWFLOW_EVALUATION_DATABASE_URL = "postgresql://knowflow_app:<pwd>@127.0.0.1:55432/knowflow"

.\services\ai\.venv\Scripts\python.exe evaluation\collector\run.py `
  --dataset "$pack\out\runner" `
  --split holdout `
  --output "$pack\out\predictions.json" `
  --run-metadata "$pack\out\run-metadata.json"
```

`privacy=local_only` 时，采集器会检查数据集和输出都位于同一个 Git 仓库中被忽略的 `.blindtest\out\`；否则以 `PRIVATE_OUTPUT_OUTSIDE_IGNORED_DIRECTORY` 拒绝。

## 4. 人工审核与门禁

生成审核模板（未传 `--review` 时写模板；参数名是 `--output`，**不是** `--prepare`）：

```powershell
$repo = (git rev-parse --show-toplevel).Trim()
$pack = "D:\konwflow\.blindtest"
Set-Location $repo
.\services\ai\.venv\Scripts\python.exe evaluation\runner\review_predictions.py `
  --predictions "$pack\out\predictions.json" `
  --dataset "$pack\out\runner" `
  --split holdout `
  --output "$pack\out\review-template.json"
```

在仓库外完成 support / citation 判断后，保存为 `D:\konwflow\.blindtest\out\review.json`。正式门禁使用 v2 gate：它必须绑定转换后数据集的 ID/SHA，并包含 `runner_v2.MINIMUMS` 的全部八项阈值。下面命令只打印数据集 SHA，不打印题面：

```powershell
@'
import json
from pathlib import Path
from evaluation.runner.runner import _load_dataset
from evaluation.runner.runner_v2 import MINIMUMS

dataset = Path(r"D:\konwflow\.blindtest\out\runner")
manifest, _, _, _, dataset_sha = _load_dataset(dataset)
gate = {"gate_version": 2, "dataset_id": manifest["dataset_id"],
        "dataset_sha256": dataset_sha, "minimums": MINIMUMS}
Path(r"D:\konwflow\.blindtest\config\gate.json").write_text(
    json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"gate_version": 2, "dataset_sha256": dataset_sha}))
'@ | & (Join-Path $repo 'services\ai\.venv\Scripts\python.exe') -
```

再跑正式门禁（**必须**提供 `--output`；原始评分含逐题结果，留在私有目录）：

```powershell
.\services\ai\.venv\Scripts\python.exe evaluation\runner\runner.py `
  --predictions "$pack\out\predictions.json" `
  --dataset "$pack\out\runner" `
  --split holdout `
  --quality-config "$pack\config\gate.json" `
  --review "$pack\out\review.json" `
  --output "$pack\out\metrics.json" `
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
