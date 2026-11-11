# 公开评测答案与引用独立人审

正式验收采用独立人工签核。此流程适用于冻结候选的公开 `development` 和 `holdout`，由独立审阅人完成两卷，再由负责人依据评分和审计材料签核。真实采集须先满足 T03 前置条件。 [交付首日记录](../planning/2026-11-09-delivery-day-1.md)

## 1. 准备工作表

在冻结候选的检出目录运行。将示例运行 ID 改为本次 ID，并将公开采集产物放在对应目录。每卷需有 v2 原始 review 和生成该 review 的 predictions。

```powershell
$candidate = git rev-parse --verify HEAD
$runId = "candidate-public-01"
$public = "eval-out/$runId/public"
$out = "eval-out/$runId/citation-review"
$prepared = python scripts/prepare-citation-review.py --manual --out $out --run-id $runId --candidate-sha $candidate `
  --development "$public/development.review.json" --development-predictions "$public/development.predictions.json" `
  --holdout "$public/holdout.review.json" --holdout-predictions "$public/holdout.predictions.json"
if ($LASTEXITCODE -ne 0) { throw "人审工作表准备失败" }
$manifestSha = ($prepared | ConvertFrom-Json).manifest_sha256
$prepared
```

每卷的预测必须声明相同的冻结候选 SHA，review 中的预测哈希必须与对应预测文件一致。输出包含 `development.csv`、`holdout.csv` 和 `manifest.json`，行数按本次产物计算。准备人将候选 SHA、运行 ID 和命令输出的 `manifest_sha256` 单独交给负责人留存。后续校验使用这份记录。

## 2. 填写工作表

只编辑 UTF-8 CSV 的这五列，保留其余列、表头和行序。

| 字段 | 填写规则 |
|---|---|
| `review_support` | 回答填 `supported` 或 `not_supported`。拒答填 `refusal_correct` 或 `refusal_incorrect`。 |
| `review_citation` | 逐条判断该行的 `claim` 是否由 `source_text` 支持，填 `correct` 或 `incorrect`。拒答留空。 |
| `review_notes` | 每行记录判定依据，去除首尾空白后至少 10 个字符。 |
| `reviewer` | 真实独立审阅者标识，禁止使用 `agent:` 前缀。 |
| `reviewed_at` | 带时区的 ISO 时间，例如 `2026-11-09T15:00:00+08:00`，不得晚于校验时间。 |

同一问题的所有引用行使用同一答案支持度、审阅者和时间。证据暂不充分时，在备注记录缺项并留待复核。取得最终判断后再导出。保留所有原始预测、review 和语料。

## 3. 校验、导出和评分

在新会话中，从独立留存的准备记录恢复 `$candidate` 和 `$manifestSha`，按上面的定义设置 `$public` 和 `$out`。校验命令读取原件并复核哈希、冻结候选和只读列。首次校验可省略 `--export`。

```powershell
python scripts/validate-citation-review.py --manual --dir $out --candidate-sha $candidate --manifest-sha256 $manifestSha --export
if ($LASTEXITCODE -ne 0) { throw "人审工作表未成功导出" }
```

`COMPLETE` 表示工作表完整。导出写入 `development.review.manual.json`、`holdout.review.manual.json` 和 `review-audit.json`，保留既有文件。审计文件记录清单、填好的 CSV 和导出文件的哈希。拒答意见和判定理由保留在 CSV，评分器按题集计算拒答指标。

用本次公开评测的语料和已批准的门限配置离线重算。下列示例使用与公开预测同目录的 `*.gate.json`。T06 要求公开引用准确率至少 96%，其余指标按交付清单复核。 [交付验收清单](../planning/2026-11-09-delivery-execution-plan.md)

```powershell
$failed = @()
foreach ($split in "development", "holdout") {
  python evaluation/runner/runner.py --formal --split $split --dataset evaluation/data/seed-v2-reviewed `
    --predictions "$public/$split.predictions.json" --quality-config "$public/$split.gate.json" `
    --review "$out/$split.review.manual.json" --output "$out/$split.score.json"
  if ($LASTEXITCODE -ne 0) { $failed += $split }
}
if ($failed.Count -gt 0) { throw "正式评分未通过 $($failed -join ', ')" }
```

独立审阅人签核时记录候选 SHA、运行 ID、两卷覆盖率和结论、日期及证据路径。负责人留存准备记录、完整工作表、审计文件及两份评分报告。公开人审是公开质量证据的一部分，私有盲测、预算与三端消费签收继续按各自流程办理。

## 4. 离线复现

```powershell
python -m unittest scripts.tests.test_manual_citation_review -v
```

临时目录中的合成夹具覆盖两卷生成、人工字段填写、拒绝缺项和篡改、导出及正式评分器读取。夹具故意给 holdout 留一条错误引用，以验证完整人审仍可产生评分失败。

2026-11-08 记录属于历史候选 `9907aca`。当时 development 有 40 个答案、47 条引用、56 行工作表，holdout 有 20 个答案、28 条引用、30 行工作表。历史原件及本次人工签核分别留存。
