"""Build machine-authored, source-grounded drafts for human review."""
import argparse
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "evaluation" / "data" / "seed-v2-candidate"
OUTPUT = DATASET / "machine-draft-annotations.json"

FACTS = {
    "fact-01": ("必填字段为 documentId（UUID）和 profileId（字符串）。",
                [("api", "必填字段为 documentId（UUID）和 profileId（字符串）。")]),
    "fact-02": ("创建成功返回 HTTP 202，响应体包含 jobId。",
                [("api", "成功响应为 HTTP 202，响应体包含 jobId。")]),
    "fact-03": ("使用 POST /v1/index-jobs 创建索引任务。",
                [("api", "创建索引任务使用 POST /v1/index-jobs。")]),
    "fact-04": ("chunkSize 默认 360 个 Unicode 码点，允许 180–720 的整数。",
                [("chunk", "chunkSize 默认 360 个 Unicode 码点，允许 180–720 的整数。")]),
    "fact-05": ("默认重叠区为 40 个 Unicode 码点。",
                [("chunk", "重叠区默认为 40 个 Unicode 码点。")]),
    "fact-06": ("每批索引最多包含 16 个分段。",
                [("chunk", "每批索引最多包含 16 个分段。")]),
    "fact-07": ("TXT/MD 偏移按原始文本的 Unicode 码点计数，从 0 开始，右端不包含。",
                [("locator", "TXT/MD 偏移以原始文本的 Unicode 码点计数，从 0 开始，区间右端不含。")]),
    "fact-08": ("PDF 页码从 1 开始；未提取到的页面坐标不得编造。",
                [("locator", "PDF 页码从 1 开始，未提取到的页面坐标不得编造。")]),
    "fact-09": ("字符串共有 4 个 Unicode 码点，🙂 的半开区间是 [2,3)。",
                [("locator", "示例串「中文🙂A」有 4 个 Unicode 码点；🙂 的区间是 [2,3)。")]),
    "fact-10": ("只有 Java 服务可以发布活动索引版本；Python 只提交候选结果。",
                [("publish", "只有 Java 服务可以发布活动索引版本；Python 只提交候选结果。")]),
    "fact-11": ("发布前核验有效租约、文档可见性、Chunk 清单和向量完整性。",
                [("publish", "发布前必须核验有效租约、文档可见性、Chunk 清单和向量完整性。")]),
    "fact-12": ("发布核验与活动版本切换在同一数据库事务中完成。",
                [("publish", "所有核验与活动版本切换应在同一数据库事务完成。")]),
    "fact-13": ("演示模型请求总期限为 18 秒，自动重试次数为 0。",
                [("timeout", "演示的模型请求总期限为 18 秒，自动重试次数为 0。")]),
    "fact-14": ("超时返回 HTTP 504，错误码为 PROCESSING_TIMEOUT。",
                [("timeout", "超时对外返回 HTTP 504，错误码 PROCESSING_TIMEOUT。")]),
    "fact-15": ("当前客户端重试等待默认 10 秒，上限 30 秒。",
                [("adr", "当前客户端重试等待默认 10 秒，上限 30 秒。")]),
}

SPECIAL = {
    "candidate-31": (
        "超时返回 HTTP 504 / PROCESSING_TIMEOUT；Python 不能自行发布活动索引，只提交候选结果。",
        [("timeout", "超时对外返回 HTTP 504，错误码 PROCESSING_TIMEOUT。"),
         ("publish", "只有 Java 服务可以发布活动索引版本；Python 只提交候选结果。")]),
    "candidate-32": (
        "每批最多 16 个分段；只有 Java 服务发布活动索引，Python 只提交候选结果。",
        [("chunk", "每批索引最多包含 16 个分段。"),
         ("publish", "只有 Java 服务可以发布活动索引版本；Python 只提交候选结果。")]),
    "candidate-33": (
        "PDF 页码从 1 开始；TXT/MD 偏移按 Unicode 码点计数、从 0 开始且右端不包含。",
        [("locator", "TXT/MD 偏移以原始文本的 Unicode 码点计数，从 0 开始，区间右端不含。"),
         ("locator", "PDF 页码从 1 开始，未提取到的页面坐标不得编造。")]),
    "candidate-34": (
        "演示支持 UTF-8 TXT、Markdown 和含可提取文字的 PDF。Embedding 接收获准的文档分段文本，LLM 接收当前问题和检索到的获准片段。",
        [("files", "支持 UTF-8 TXT、Markdown 和含可提取文字的 PDF。"),
         ("outbound", "Embedding 请求发送获准的文档分段文本。"),
         ("outbound", "LLM 请求发送当前问题和检索到的获准片段。")]),
    "candidate-35": (
        "owner 由服务端根据已验证身份生成；不存在、他人所有或已删除的资源统一返回 HTTP 404。",
        [("access", "owner 只由服务端根据已验证身份生成，客户端传入 owner_id 应拒绝。"),
         ("access", "不存在、其他用户或已经删除的资源，对外统一返回 HTTP 404。")]),
    "candidate-36": (
        "20 秒默认等待和 60 秒上限仅是未批准草案，不生效；已批准 ADR 规定当前默认 10 秒、上限 30 秒。",
        [("draft", "状态：草案，未批准，不生效。"),
         ("draft", "提议默认等待 20 秒，上限 60 秒。"),
         ("adr", "当前客户端重试等待默认 10 秒，上限 30 秒。")]),
    "candidate-37": (
        "发布前核验有效租约、文档可见性、Chunk 清单和向量完整性；所有核验与活动版本切换在同一数据库事务完成。",
        [("publish", "发布前必须核验有效租约、文档可见性、Chunk 清单和向量完整性。"),
         ("publish", "所有核验与活动版本切换应在同一数据库事务完成。")]),
    "candidate-38": (
        "扫描 PDF 需要 OCR，而该演示版本未实现 OCR。",
        [("files", "扫描 PDF 需要 OCR，本演示版本未实现 OCR。")]),
    "candidate-39": (
        "Embedding 接收获准的文档分段文本，LLM 接收当前问题和检索到的获准片段。供应商价格、保留及训练政策不能从本材料推断，须查正式供应商记录。",
        [("outbound", "Embedding 请求发送获准的文档分段文本。"),
         ("outbound", "LLM 请求发送当前问题和检索到的获准片段。"),
         ("outbound", "供应商价格、保留及训练政策须查询正式供应商记录，本材料不提供这些事实。")]),
    "candidate-40": (
        "该演示的自动重试次数为 0；取消只释放计算资源，不能恢复已删除文档，也不会自行发布索引。",
        [("timeout", "演示的模型请求总期限为 18 秒，自动重试次数为 0。"),
         ("timeout", "取消只释放计算资源，不能恢复已删除文档，也不能自行发布索引。")]),
    "candidate-44": (
        "owner 由服务端根据已验证身份生成，客户端传入 owner_id 应拒绝。",
        [("access", "owner 只由服务端根据已验证身份生成，客户端传入 owner_id 应拒绝。")]),
    "candidate-47": (
        "扫描 PDF 需要 OCR，而该演示版本未实现 OCR。",
        [("files", "扫描 PDF 需要 OCR，本演示版本未实现 OCR。")]),
    "candidate-49": (
        "未批准的 20 秒默认等待和 60 秒上限草案不生效；当前已批准参数是默认 10 秒、上限 30 秒。",
        [("draft", "状态：草案，未批准，不生效。"),
         ("draft", "提议默认等待 20 秒，上限 60 秒。"),
         ("adr", "当前客户端重试等待默认 10 秒，上限 30 秒。")]),
    "candidate-50": (
        "6 MiB 是合成演示的单文件上限，不是 KnowFlow 产品限制。",
        [("files", "合成演示的单文件上限为 6 MiB，不是 KnowFlow 产品限制。")]),
}

NO_ANSWER = {
    "candidate-51": "现有合成资料未说明生产环境规定使用哪一款 GPU。",
    "candidate-52": "现有合成资料未提供 Embedding 供应商的正式报价。",
    "candidate-53": "现有合成资料未提供供应商对用户资料的保留天数；应查询正式供应商记录。",
    "candidate-54": "现有合成资料未说明正式服务部署的云区域。",
    "candidate-55": "现有合成资料未提供真实用户试用人数。",
    "candidate-56": "现有合成资料未定义真实问答服务的 p95 延迟承诺。",
    "candidate-57": "现有合成资料未说明已获得何种商业客户认证。",
    "candidate-58": "现有合成资料未提供文档删除后的备份保留天数。",
    "candidate-59": "现有合成资料没有说明 DOCX 上传与解析能力，不能据此确定是否支持。",
    "candidate-60": "现有合成资料未提供线上系统使用的不可变 LLM 模型版本号。",
}


def _canonical_questions_sha256(questions):
    canonical = json.dumps(questions, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return sha256(canonical).hexdigest()


def draft_annotations(dataset_root=DATASET):
    root = Path(dataset_root).resolve()
    manifest_bytes = (root / "manifest.json").read_bytes().replace(b"\r\n", b"\n")
    manifest = json.loads(manifest_bytes)
    questions = json.loads((root / "questions.json").read_text(encoding="utf-8"))
    documents = {item["id"]: item for item in manifest["documents"]}
    sources = {item["id"]: (root / item["path"]).read_text(encoding="utf-8")
               for item in manifest["documents"]}
    annotations = []
    for question in questions:
        row = {key: question[key] for key in
               ("id", "question", "leakage_group", "category")}
        row["annotation_status"] = "machine_draft"
        if question["id"] in NO_ANSWER:
            row.update(answerable=False, reference_answer=NO_ANSWER[question["id"]],
                       evidence=[])
        else:
            if question["id"] in SPECIAL:
                answer, references = SPECIAL[question["id"]]
            else:
                answer, references = FACTS[question["leakage_group"]]
            evidence = []
            for document_id, quote in references:
                source = sources[document_id]
                start = source.find(quote)
                if start < 0 or source.find(quote, start + 1) >= 0:
                    raise ValueError("DRAFT_EVIDENCE_QUOTE_NOT_UNIQUE")
                end = start + len(quote)
                evidence.append({
                    "document_id": document_id,
                    "content_version_id": documents[document_id]["content_version_id"],
                    "start": start,
                    "end": end,
                    "unit": "unicode_code_point",
                    "quote": quote,
                    "line_start": source.count("\n", 0, start) + 1,
                    "line_end": source.count("\n", 0, end) + 1,
                })
            row.update(answerable=True, reference_answer=answer, evidence=evidence)
        annotations.append(row)
    return {
        "draft_version": 1,
        "status": "machine_authored_pending_human_review",
        "dataset_id": manifest["dataset_id"],
        "source_manifest_sha256": sha256(manifest_bytes).hexdigest(),
        "candidate_questions_sha256": _canonical_questions_sha256(questions),
        "question_count": len(annotations),
        "questions_marked_reviewed_count": 0,
        "human_reviewed": False,
        "annotations": annotations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = draft_annotations(args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"question_count": result["question_count"],
                      "human_reviewed": result["human_reviewed"],
                      "status": result["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
