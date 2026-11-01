"""Build a versioned 60-question candidate set from the synthetic Qingzhu corpus."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT / "evaluation" / "data" / "seed-v1"
OUTPUT = ROOT / "evaluation" / "data" / "seed-v2-candidate"

PAIRED = [
    ("api", "创建索引任务请求需要提供哪些必填字段？", "索引任务请求必须提供哪两个字段及其类型？"),
    ("api", "任务成功后返回什么 HTTP 状态码，响应体包含什么字段？", "创建索引任务成功时客户端会看到怎样的响应？"),
    ("api", "创建索引任务的接口路径是什么？", "建立新的 index job 应调用哪一个 endpoint？"),
    ("chunk", "chunkSize 的默认值和允许范围分别是多少？", "分段长度采用什么默认值，合法下界和上界是多少？"),
    ("chunk", "默认重叠区长度是多少个 Unicode 码点？", "相邻文本 chunk 会默认重叠多少码点？"),
    ("chunk", "单批索引最多包含多少个分段？", "一次索引写入 batch 的 chunk 上限是多少？"),
    ("locator", "TXT/MD 偏移用什么单位，从几开始计数？", "文本来源 locator 的坐标如何计量？"),
    ("locator", "PDF 页码从几开始计数？", "引用 PDF 内容时第一页的编号是什么？"),
    ("locator", "字符串“中文🙂A”有多少个 Unicode 码点，🙂 的区间是什么？", "示例中的 emoji 在按码点计算时占据哪个半开区间？"),
    ("publish", "谁可以发布活动索引版本？", "Java 与 Python 中哪一端有权切换 active index？"),
    ("publish", "活动索引发布前要核验哪些内容？", "候选版本进入可检索状态之前需要通过哪些检查？"),
    ("publish", "活动版本切换与发布核验应处于什么事务边界？", "发布前验证和索引切换怎样保证一起提交？"),
    ("timeout", "演示模型请求总期限和自动重试次数分别是多少？", "合成项目的模型请求时限与自动 retry 配置是多少？"),
    ("timeout", "请求超时时返回什么 HTTP 状态和错误码？", "模型请求到期后对外报告什么 HTTP 与错误标识？"),
    ("adr", "当前客户端重试等待的默认值和上限是多少？", "当前生效的 retry wait 区间是多少？"),
]

OTHER = [
    ("multi_evidence", "publish-timeout", "任务超时时会返回什么错误？此时 Python 能否自行发布索引？"),
    ("multi_evidence", "chunk-publish", "索引批次大小上限是什么？活动索引由哪一服务发布？"),
    ("multi_evidence", "locator-format", "PDF 页码和 TXT/MD 偏移分别采用什么起点和单位？"),
    ("multi_evidence", "privacy-files", "演示支持哪些文件？上传文本与发送给 LLM 的检索片段有何关系？"),
    ("multi_evidence", "identity-notfound", "owner_id 从哪里确定？他人资源 ID 会返回什么状态？"),
    ("multi_evidence", "rollback-timeout", "重试草案中的等待值为什么不生效？当前有效的时间范围是什么？"),
    ("multi_evidence", "release-checks", "发布前要完成哪些核验，活动版本的切换如何提交？"),
    ("multi_evidence", "parse-boundary", "扫描 PDF 需要什么额外能力？演示有提供它吗？"),
    ("multi_evidence", "data-policy", "Embedding 与 LLM 各自接收什么文本？哪些字段不能当作供应商事实？"),
    ("multi_evidence", "retry-expiration", "失败重试上限是什么？任务超时是否会改变已删除文档状态？"),
    ("chinese_keyword", "fact-01", "查询“索引任务”的必填 camelCase 字段叫什么？"),
    ("chinese_keyword", "fact-05", "分段配置中的 overlap 默认是多少？"),
    ("chinese_keyword", "fact-07", "text_range 的 Unicode code point 偏移从几开始、右端是否包含？"),
    ("chinese_keyword", "identity-notfound", "客户端传入 owner_id 应如何处理？"),
    ("chinese_keyword", "fact-08", "PDF locator 的页码起点是多少？"),
    ("chinese_keyword", "fact-10", "候选 embedding 由谁提交，active_index 由谁切换？"),
    ("chinese_keyword", "parse-boundary", "扫描版 PDF 是否自动 OCR？"),
    ("chinese_keyword", "fact-14", "PROCESSING_TIMEOUT 对应哪个 HTTP 状态？"),
    ("chinese_keyword", "rollback-timeout", "未批准的 retry draft 能否代表当前生效配置？"),
    ("chinese_keyword", "miB-boundary", "6 MiB 是产品上传上限还是合成演示数据中的限制？"),
    ("no_answer", "production-gpu", "KnowFlow 在生产环境规定使用哪一款 GPU？"),
    ("no_answer", "vendor-price", "Embedding 供应商每千 token 的正式报价是多少？"),
    ("no_answer", "vendor-retention", "模型供应商会将用户资料保留多少天？"),
    ("no_answer", "production-region", "正式服务部署在哪一个云区域？"),
    ("no_answer", "customer-count", "目前有多少位真实用户完成了试用？"),
    ("no_answer", "latency-slo", "真实问答服务承诺的 p95 延迟是多少？"),
    ("no_answer", "commercial-license", "项目已经获得了哪种商业客户认证？"),
    ("no_answer", "deleted-backup", "文档删除后的备份会保留多少天？"),
    ("no_answer", "docx-support", "合成项目是否已经支持 DOCX 上传与解析？"),
    ("no_answer", "prod-model", "线上系统当前使用的不可变 LLM 模型版本号是多少？"),
]


def _questions():
    rows = []
    for index, (_document, question, paraphrase) in enumerate(PAIRED, 1):
        group = f"fact-{index:02}"
        rows.append({"id": f"candidate-{index:02}", "question": question,
                     "leakage_group": group, "annotation_status": "candidate",
                     "category": "factual"})
        rows.append({"id": f"candidate-{index + 15:02}",
                     "question": paraphrase,
                     "leakage_group": group, "annotation_status": "candidate",
                     "category": "rewrite"})
    for index, (category, group, question) in enumerate(OTHER, 31):
        rows.append({"id": f"candidate-{index:02}", "question": question,
                     "leakage_group": group, "annotation_status": "candidate",
                     "category": category})
    return rows


def build(output: Path = OUTPUT):
    if (output / "questions.json").exists():
        raise FileExistsError("OUTPUT_DIRECTORY_NOT_EMPTY")
    output.mkdir(parents=True, exist_ok=True)
    seed_manifest = json.loads((SEED / "manifest.json").read_text(encoding="utf-8"))
    documents = []
    for item in seed_manifest["documents"]:
        source = SEED / item["path"]
        target = output / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha256(target.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("DATASET_COPY_HASH_MISMATCH")
        documents.append(item)
    manifest = {"dataset_id": "qingzhu-seed-v2-candidate", "synthetic": True,
                "license": "CC0-1.0",
                "description": "60 pending candidate questions over the original synthetic Qingzhu corpus; not human-verified labels.",
                "documents": documents}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False,
                                                       indent=2) + "\n", encoding="utf-8")
    questions = _questions()
    category_counts = {category: sum(row["category"] == category for row in questions)
                       for category in {"factual", "rewrite", "multi_evidence",
                                        "chinese_keyword", "no_answer"}}
    if len(questions) != 60 or category_counts != {
            "factual": 15, "rewrite": 15, "multi_evidence": 10,
            "chinese_keyword": 10, "no_answer": 10}:
        raise ValueError("CANDIDATE_SET_SHAPE_INVALID")
    (output / "questions.json").write_text(json.dumps(questions, ensure_ascii=False,
                                                        indent=2) + "\n", encoding="utf-8")
    return len(documents), len(questions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    documents, questions = build(args.output)
    print(json.dumps({"documents": documents, "candidate_questions": questions,
                      "annotation_status": "candidate"}))


if __name__ == "__main__":
    main()
