# 合并验收

## GitHub 检查

把 `Full Compose E2E`、`Java and Testcontainers`、`Offline RAG quality`
和 `Reviewed real RAG quality` 设为 main 的必过检查，启用合并前与 main
同步。真实评测按 PR 运行，当前流程使用常规 PR 合并。
外部 fork 涉及真实评测时，由维护者审核并在仓库内分支重新发起 PR。

无密钥质量检查运行已审阅的 20 道留出题。其字符二元组向量用于检索回归，
合成答复只摘录确实检索到的标注证据。语义支持和真实供应商延迟由下面的流程评估。
本地运行 `uv run --project services/ai --frozen python scripts/e2e-evaluation.py --offline-quality --output /tmp/rag/report.json`。

## 真实评测

在仓库的 `rag-quality` Environment 配置必需审核者并禁止自我审批，
仅在受信任的同仓库 PR 上审批候选代码。设置专用 `KNOWFLOW_LLM_API_KEY`
和 `KNOWFLOW_EMBEDDING_API_KEY`，以及有效的 `RAG_PRICE_JSON`、
`RAG_POLICY_JSON` 和 `RAG_RUN_LIMIT_MICROYUAN`。
价格与预算政策使用生产预算文件的结构。不要复用生产凭证。

从受审核的 `local` 提交运行 `RAG quality review` 的手动校准，
下载 `rag-latency-baseline.json` 并将其提交到
`evaluation/data/rag-latency-baseline.json`。三次相同条件的串行留出集
p95 中位数乘以 1.25 作为延迟上限。

候选收集完成后，另一名具有维护权限的审核者下载 `rag-live`，
对 `report.review.json` 中每个回答及其引用依次给出判断，然后在同一 PR
提交 Approve review。正文使用下列格式，包含所有已回答题的判断，
并从 review 文件复制实际哈希。

```knowflow-rag-review
{
  "predictions_sha256": "<report.review.json 中的值>",
  "judgements": {
    "<问题 ID>": ["supported", "supported", "unsupported"]
  }
}
```

每个数组首项评判答案，余项按引用顺序。等待审批的步骤可在 GitHub 查看，
质量审核步骤等待 30 分钟，未完成时保持不通过。重新收集后使用新的预测哈希。
参考题或阈值改动需单独说明并重新校准。

## OCR 和重建

生产 AI 镜像内置 Poppler 及 Tesseract 简体、繁体和英语语言包。
OCR 在受限解析子进程内处理扫描页。资源限制、OCR 或索引提交失败会保留上一版已发布索引。
发布前先排空旧 pipeline 的任务，再部署 Java 和 Python。旧索引可继续查询，
新的索引使用 `knowflow-index-v2-ocr`，通过重建按需切换。

`POST /api/v1/documents/{documentId}/rebuilds` 可传 UUID `Idempotency-Key`。
同账号同键重复请求同一文档返回同一个任务。键已绑定另一文档时返回 409。
旧客户端省略该请求头时沿用运行中重建去重规则。
