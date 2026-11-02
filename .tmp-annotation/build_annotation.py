"""Compose the independent annotation review file from reviewed judgments.

Offsets are never typed by hand: every evidence span is located by its exact
quote inside the pinned document text, so a mistyped or non-unique quote fails
loudly instead of producing a silently wrong annotation.
"""
import json
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "evaluation/data/seed-v2-candidate"
OUT = ROOT / "evaluation/data/reviews/2026-11-02-agent-annotation-review.json"

# id -> (answerable, reference_answer, [(document_id, exact_quote), ...])
ANNOTATIONS = {
    # --- fact-01: index job required fields ---
    "candidate-01": (True, "必填字段是 documentId（UUID）和 profileId（字符串）两项。", [
        ("api", "必填字段为 documentId（UUID）和 profileId（字符串）。")]),
    "candidate-16": (True, "两个必填字段：documentId，类型 UUID；profileId，类型字符串。", [
        ("api", "必填字段为 documentId（UUID）和 profileId（字符串）。")]),
    "candidate-41": (True, "两个必填字段的 camelCase 名称是 documentId 和 profileId。", [
        ("api", "必填字段为 documentId（UUID）和 profileId（字符串）。")]),
    # --- fact-02: success response ---
    "candidate-02": (True, "成功返回 HTTP 202，响应体包含 jobId。", [
        ("api", "成功响应为 HTTP 202，响应体包含 jobId。")]),
    "candidate-17": (True, "客户端会收到 HTTP 202，响应体里带 jobId。", [
        ("api", "成功响应为 HTTP 202，响应体包含 jobId。")]),
    # --- fact-03: endpoint ---
    "candidate-03": (True, "接口路径是 POST /v1/index-jobs。", [
        ("api", "创建索引任务使用 POST /v1/index-jobs。")]),
    "candidate-18": (True, "调用 POST /v1/index-jobs 这个 endpoint。", [
        ("api", "创建索引任务使用 POST /v1/index-jobs。")]),
    # --- fact-04: chunkSize ---
    "candidate-04": (True, "chunkSize 默认 360 个 Unicode 码点，允许范围是 180 到 720 的整数。", [
        ("chunk", "chunkSize 默认 360 个 Unicode 码点，允许 180–720 的整数。")]),
    "candidate-19": (True, "默认 360 个 Unicode 码点，下界 180、上界 720，且须为整数。", [
        ("chunk", "chunkSize 默认 360 个 Unicode 码点，允许 180–720 的整数。")]),
    # --- fact-05: overlap ---
    "candidate-05": (True, "默认重叠区为 40 个 Unicode 码点。", [
        ("chunk", "重叠区默认为 40 个 Unicode 码点。")]),
    "candidate-20": (True, "默认重叠 40 个 Unicode 码点。", [
        ("chunk", "重叠区默认为 40 个 Unicode 码点。")]),
    "candidate-42": (True, "overlap 默认为 40 个 Unicode 码点。", [
        ("chunk", "重叠区默认为 40 个 Unicode 码点。")]),
    # --- fact-06: batch size ---
    "candidate-06": (True, "每批索引最多包含 16 个分段。", [
        ("chunk", "每批索引最多包含 16 个分段。")]),
    "candidate-21": (True, "单次写入 batch 的 chunk 上限是 16。", [
        ("chunk", "每批索引最多包含 16 个分段。")]),
    # --- fact-07: text locator ---
    "candidate-07": (True, "单位是 Unicode 码点，从 0 开始计数，区间右端不含。", [
        ("locator", "TXT/MD 偏移以原始文本的 Unicode 码点计数，从 0 开始，区间右端不含。")]),
    "candidate-22": (True, "按原始文本的 Unicode 码点计数，起点 0，半开区间。", [
        ("locator", "TXT/MD 偏移以原始文本的 Unicode 码点计数，从 0 开始，区间右端不含。")]),
    "candidate-43": (True, "从 0 开始，右端不包含，是半开区间。", [
        ("locator", "TXT/MD 偏移以原始文本的 Unicode 码点计数，从 0 开始，区间右端不含。")]),
    # --- fact-08: PDF page numbers ---
    "candidate-08": (True, "PDF 页码从 1 开始计数。", [
        ("locator", "PDF 页码从 1 开始")]),
    "candidate-23": (True, "第一页的编号是 1。", [
        ("locator", "PDF 页码从 1 开始")]),
    "candidate-45": (True, "页码起点是 1。", [
        ("locator", "PDF 页码从 1 开始")]),
    # --- fact-09: code points ---
    "candidate-09": (True, "「中文🙂A」有 4 个 Unicode 码点；🙂 的区间是 [2,3)。", [
        ("locator", "示例串「中文🙂A」有 4 个 Unicode 码点；🙂 的区间是 [2,3)。")]),
    "candidate-24": (True, "🙂 占据半开区间 [2,3)，即第 3 个码点。", [
        ("locator", "示例串「中文🙂A」有 4 个 Unicode 码点；🙂 的区间是 [2,3)。")]),
    # --- fact-10: who publishes ---
    "candidate-10": (True, "只有 Java 服务可以发布活动索引版本，Python 只提交候选结果。", [
        ("publish", "只有 Java 服务可以发布活动索引版本；Python 只提交候选结果。")]),
    "candidate-25": (True, "Java 端有权切换 active index，Python 只提交候选结果。", [
        ("publish", "只有 Java 服务可以发布活动索引版本；Python 只提交候选结果。")]),
    "candidate-46": (True, "Python 提交候选结果（含候选 embedding），Java 负责切换 active_index。", [
        ("publish", "只有 Java 服务可以发布活动索引版本；Python 只提交候选结果。")]),
    # --- fact-11: pre-publish checks ---
    "candidate-11": (True, "需要核验有效租约、文档可见性、Chunk 清单和向量完整性。", [
        ("publish", "发布前必须核验有效租约、文档可见性、Chunk 清单和向量完整性。")]),
    "candidate-26": (True, "通过四项核验：有效租约、文档可见性、Chunk 清单、向量完整性。", [
        ("publish", "发布前必须核验有效租约、文档可见性、Chunk 清单和向量完整性。")]),
    # --- fact-12: transaction boundary ---
    "candidate-12": (True, "所有核验与活动版本切换应在同一数据库事务内完成。", [
        ("publish", "所有核验与活动版本切换应在同一数据库事务完成。")]),
    "candidate-27": (True, "把发布前核验和活动版本切换放在同一个数据库事务里提交，因此要么全成要么全不成。", [
        ("publish", "所有核验与活动版本切换应在同一数据库事务完成。")]),
    # --- fact-13: deadline and retries ---
    "candidate-13": (True, "总期限 18 秒，自动重试次数 0。", [
        ("timeout", "演示的模型请求总期限为 18 秒，自动重试次数为 0。")]),
    "candidate-28": (True, "时限 18 秒，自动 retry 次数为 0。", [
        ("timeout", "演示的模型请求总期限为 18 秒，自动重试次数为 0。")]),
    # --- fact-14: timeout status ---
    "candidate-14": (True, "返回 HTTP 504，错误码 PROCESSING_TIMEOUT。", [
        ("timeout", "超时对外返回 HTTP 504，错误码 PROCESSING_TIMEOUT。")]),
    "candidate-29": (True, "对外报告 HTTP 504 与错误码 PROCESSING_TIMEOUT。", [
        ("timeout", "超时对外返回 HTTP 504，错误码 PROCESSING_TIMEOUT。")]),
    "candidate-48": (True, "对应 HTTP 504。", [
        ("timeout", "超时对外返回 HTTP 504，错误码 PROCESSING_TIMEOUT。")]),
    # --- fact-15: retry wait ---
    "candidate-15": (True, "当前客户端重试等待默认 10 秒，上限 30 秒。", [
        ("adr", "当前客户端重试等待默认 10 秒，上限 30 秒。")]),
    "candidate-30": (True, "默认 10 秒、上限 30 秒。", [
        ("adr", "当前客户端重试等待默认 10 秒，上限 30 秒。")]),
    # --- multi_evidence ---
    "candidate-31": (True, "超时返回 HTTP 504、错误码 PROCESSING_TIMEOUT；Python 不能自行发布索引，只有 Java 服务可以发布活动索引版本。", [
        ("timeout", "超时对外返回 HTTP 504，错误码 PROCESSING_TIMEOUT。"),
        ("publish", "只有 Java 服务可以发布活动索引版本；Python 只提交候选结果。")]),
    "candidate-32": (True, "每批索引最多 16 个分段；活动索引版本只有 Java 服务可以发布。", [
        ("chunk", "每批索引最多包含 16 个分段。"),
        ("publish", "只有 Java 服务可以发布活动索引版本；Python 只提交候选结果。")]),
    "candidate-33": (True, "TXT/MD 偏移以 Unicode 码点计数、从 0 开始、右端不含；PDF 页码从 1 开始。", [
        ("locator", "TXT/MD 偏移以原始文本的 Unicode 码点计数，从 0 开始，区间右端不含。"),
        ("locator", "PDF 页码从 1 开始")]),
    "candidate-34": (True, "支持 UTF-8 TXT、Markdown 和含可提取文字的 PDF；检索片段是获准片段，LLM 请求发送当前问题与这些检索到的获准片段。", [
        ("files", "支持 UTF-8 TXT、Markdown 和含可提取文字的 PDF。"),
        ("outbound", "LLM 请求发送当前问题和检索到的获准片段。")]),
    "candidate-35": (True, "owner 只由服务端根据已验证身份生成，客户端传入 owner_id 应拒绝；不存在、属于他人或已删除的资源统一返回 HTTP 404。", [
        ("access", "owner 只由服务端根据已验证身份生成，客户端传入 owner_id 应拒绝。"),
        ("access", "不存在、其他用户或已经删除的资源，对外统一返回 HTTP 404。")]),
    "candidate-36": (True, "该草案状态为未批准、不生效，且 ADR-017 已替代它的重试等待参数；当前生效值是默认 10 秒、上限 30 秒。", [
        ("draft", "状态：草案，未批准，不生效。"),
        ("adr", "本 ADR 替代重试草案 v1.2 的重试等待参数。"),
        ("adr", "当前客户端重试等待默认 10 秒，上限 30 秒。")]),
    "candidate-37": (True, "发布前须核验有效租约、文档可见性、Chunk 清单和向量完整性；这些核验与活动版本切换应在同一数据库事务完成。", [
        ("publish", "发布前必须核验有效租约、文档可见性、Chunk 清单和向量完整性。"),
        ("publish", "所有核验与活动版本切换应在同一数据库事务完成。")]),
    "candidate-38": (True, "扫描 PDF 需要 OCR 能力；本演示版本未实现 OCR。", [
        ("files", "扫描 PDF 需要 OCR，本演示版本未实现 OCR。")]),
    "candidate-39": (True, "Embedding 请求发送获准的文档分段文本；LLM 请求发送当前问题和检索到的获准片段。供应商的价格、保留及训练政策须查询正式供应商记录，本材料不提供这些事实，不能当作供应商事实使用。", [
        ("outbound", "Embedding 请求发送获准的文档分段文本。"),
        ("outbound", "LLM 请求发送当前问题和检索到的获准片段。"),
        ("outbound", "供应商价格、保留及训练政策须查询正式供应商记录，本材料不提供这些事实。")]),
    "candidate-40": (True, "自动重试次数为 0，即失败不重试；超时与取消只释放计算资源，不能恢复已删除文档，也不能自行发布索引。", [
        ("timeout", "演示的模型请求总期限为 18 秒，自动重试次数为 0。"),
        ("timeout", "取消只释放计算资源，不能恢复已删除文档，也不能自行发布索引。")]),
    # --- chinese_keyword ---
    "candidate-44": (True, "应拒绝：owner 只能由服务端根据已验证身份生成，客户端传入 owner_id 应拒绝。", [
        ("access", "owner 只由服务端根据已验证身份生成，客户端传入 owner_id 应拒绝。")]),
    "candidate-47": (True, "不自动 OCR：扫描 PDF 需要 OCR，本演示版本未实现 OCR。", [
        ("files", "扫描 PDF 需要 OCR，本演示版本未实现 OCR。")]),
    "candidate-49": (True, "不能。该草案状态为未批准、不生效，且 ADR-017 已替代它的重试等待参数。", [
        ("draft", "状态：草案，未批准，不生效。"),
        ("adr", "本 ADR 替代重试草案 v1.2 的重试等待参数。")]),
    "candidate-50": (True, "6 MiB 是合成演示的单文件上限，不是 KnowFlow 产品限制。", [
        ("files", "合成演示的单文件上限为 6 MiB，不是 KnowFlow 产品限制。")]),
}

# Questions the reviewed corpus cannot answer: the material never states the fact.
UNANSWERABLE = {
    "candidate-51": "材料未规定生产环境使用哪一款 GPU，现有文档不含此事实。",
    "candidate-52": "材料不含供应商报价；价格须查询正式供应商记录，此处不提供该数字。",
    "candidate-53": "材料未给出供应商的保留天数；保留政策须查询正式供应商记录。",
    "candidate-54": "材料未说明正式服务的部署云区域。",
    "candidate-55": "材料未记录任何真实用户试用人数。",
    "candidate-56": "材料未给出真实问答服务的 p95 延迟承诺。",
    "candidate-57": "材料未提及任何商业客户认证。",
    "candidate-58": "材料未规定删除后备份的保留天数；超时文档只说明取消不能恢复已删除文档。",
    "candidate-59": "材料只列出 TXT、Markdown 与含可提取文字的 PDF 三种格式，从未说明支持 DOCX，因此不能回答为已支持。",
    "candidate-60": "材料未记录线上系统使用的 LLM 版本号。",
}


def main():
    manifest_bytes = (CANDIDATE / "manifest.json").read_bytes().replace(b"\r\n", b"\n")
    manifest = json.loads(manifest_bytes)
    candidates = json.loads((CANDIDATE / "questions.json").read_text(encoding="utf-8"))
    documents = {}
    for item in manifest["documents"]:
        text = (CANDIDATE / item["path"]).read_text(encoding="utf-8")
        documents[item["id"]] = (item, text)

    annotations = []
    for candidate in candidates:
        question_id = candidate["id"]
        if question_id in UNANSWERABLE:
            answerable, answer, spans = False, UNANSWERABLE[question_id], []
        else:
            answerable, answer, spans = ANNOTATIONS[question_id]
        evidence = []
        for document_id, quote in spans:
            item, text = documents[document_id]
            if text.count(quote) != 1:
                raise SystemExit(f"quote not unique in {document_id}: {quote!r} "
                                 f"count={text.count(quote)}")
            start = text.index(quote)
            end = start + len(quote)
            evidence.append({
                "document_id": document_id,
                "content_version_id": item["content_version_id"],
                "start": start,
                "end": end,
                "unit": "unicode_code_point",
                "quote": quote,
                "line_start": text.count("\n", 0, start) + 1,
                "line_end": text.count("\n", 0, end) + 1,
            })
        annotations.append({
            "id": question_id,
            "question": candidate["question"],
            "leakage_group": candidate["leakage_group"],
            "annotation_status": "reviewed",
            "category": candidate["category"],
            "answerable": answerable,
            "reference_answer": answer,
            "evidence": evidence,
        })

    canonical = json.dumps(candidates, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    review = {
        "status": "agent_reviewed",
        "review_version": 1,
        "dataset_id": manifest["dataset_id"],
        "source_manifest_sha256": sha256(manifest_bytes).hexdigest(),
        "candidate_questions_sha256": sha256(canonical).hexdigest(),
        "reviewer": {
            "id": "agent:little-code-sauce@independent-pass-2026-11-02",
            "reviewed_at": "2026-11-02T15:30:00+08:00",
        },
        "review_method": (
            "Independent agent annotation written from the pinned source documents "
            "only; the machine draft was not consulted. This is agent review, not "
            "human review, and must not be reported as human review."),
        "annotations": annotations,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    answerable = sum(1 for item in annotations if item["answerable"])
    print(json.dumps({"output": str(OUT), "questions": len(annotations),
                      "answerable": answerable,
                      "unanswerable": len(annotations) - answerable,
                      "evidence_spans": sum(len(a["evidence"]) for a in annotations)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
