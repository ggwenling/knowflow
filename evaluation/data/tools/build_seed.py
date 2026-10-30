"""Reproduce original synthetic seed documents and reference annotations, no external data."""
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'seed-v1'
DOCS = [
('api', '索引接口.md', '# 合成项目「青竹」接口规范 v1.4\n\n状态：已发布；2026-09-12 生效。\n创建索引任务使用 POST /v1/index-jobs。\n必填字段为 documentId（UUID）和 profileId（字符串）。\n成功响应为 HTTP 202，响应体包含 jobId。\n'),
('chunk', '分段策略.md', '# 合成项目「青竹」分段策略 v2\n\n状态：已批准。\nchunkSize 默认 360 个 Unicode 码点，允许 180–720 的整数。\n重叠区默认为 40 个 Unicode 码点。\n每批索引最多包含 16 个分段。\n'),
('draft', '重试草案.md', '# 合成项目「青竹」重试草案 v1.2\n\n状态：草案，未批准，不生效。\n编辑日期：2026-09-20。\n提议默认等待 20 秒，上限 60 秒。\n'),
('adr', 'ADR-017.md', '# 合成项目「青竹」ADR-017\n\n状态：已批准；2026-10-01 生效。\n本 ADR 替代重试草案 v1.2 的重试等待参数。\n当前客户端重试等待默认 10 秒，上限 30 秒。\n'),
('files', '文件边界.md', '# 合成项目「青竹」文件边界 v1\n\n支持 UTF-8 TXT、Markdown 和含可提取文字的 PDF。\n合成演示的单文件上限为 6 MiB，不是 KnowFlow 产品限制。\n扫描 PDF 需要 OCR，本演示版本未实现 OCR。\n'),
('access', '资源隔离.txt', '合成项目「青竹」资源访问规范 v1\n\nowner 只由服务端根据已验证身份生成，客户端传入 owner_id 应拒绝。\n不存在、其他用户或已经删除的资源，对外统一返回 HTTP 404。\n不能因为资源 ID 存在就直接返回原文。\n'),
('publish', '索引发布.md', '# 合成项目「青竹」发布协议 v3\n\n只有 Java 服务可以发布活动索引版本；Python 只提交候选结果。\n发布前必须核验有效租约、文档可见性、Chunk 清单和向量完整性。\n所有核验与活动版本切换应在同一数据库事务完成。\n'),
('locator', '来源定位.md', '# 合成项目「青竹」来源定位 v1\n\nTXT/MD 偏移以原始文本的 Unicode 码点计数，从 0 开始，区间右端不含。\nPDF 页码从 1 开始，未提取到的页面坐标不得编造。\n示例串「中文🙂A」有 4 个 Unicode 码点；🙂 的区间是 [2,3)。\n'),
('outbound', '数据出站.txt', '合成项目「青竹」数据出站说明 v1\n\nEmbedding 请求发送获准的文档分段文本。\nLLM 请求发送当前问题和检索到的获准片段。\n演示仅使用原创合成内容，不含用户文档、密钥和个人资料。\n供应商价格、保留及训练政策须查询正式供应商记录，本材料不提供这些事实。\n'),
('timeout', '超时取消.md', '# 合成项目「青竹」超时规则 v1\n\n演示的模型请求总期限为 18 秒，自动重试次数为 0。\n超时对外返回 HTTP 504，错误码 PROCESSING_TIMEOUT。\n取消只释放计算资源，不能恢复已删除文档，也不能自行发布索引。\n'),
]
# name, question, answerable, answer, (document id, exact source quote)*
QUESTIONS = [
('q01','创建索引任务必须传哪些字段？',True,'documentId（UUID）和 profileId（字符串）。',[('api','必填字段为 documentId（UUID）和 profileId（字符串）。')]),
('q02','索引任务创建成功的 HTTP 状态与查询标识是什么？',True,'HTTP 202，使用 jobId。',[('api','成功响应为 HTTP 202，响应体包含 jobId。')]),
('q03','分段默认长度、允许范围和重叠长度是多少？',True,'默认 360，允许 180–720，默认重叠 40，单位均为 Unicode 码点。',[('chunk','chunkSize 默认 360 个 Unicode 码点，允许 180–720 的整数。'),('chunk','重叠区默认为 40 个 Unicode 码点。')]),
('q04','重试等待用 20/60 秒还是 10/30 秒？为什么？',True,'默认 10 秒，上限 30 秒；ADR-017 已批准生效并明确替代未生效草案。',[('draft','状态：草案，未批准，不生效。'),('adr','状态：已批准；2026-10-01 生效。'),('adr','本 ADR 替代重试草案 v1.2 的重试等待参数。'),('adr','当前客户端重试等待默认 10 秒，上限 30 秒。')]),
('q05','演示支持哪些格式，扫描 PDF 可以直接索引吗？',True,'UTF-8 TXT、Markdown、文本型 PDF；扫描 PDF 需要尚未实现的 OCR。',[('files','支持 UTF-8 TXT、Markdown 和含可提取文字的 PDF。'),('files','扫描 PDF 需要 OCR，本演示版本未实现 OCR。')]),
('q06','访问其他用户资源应该返回什么，能相信客户端 owner_id 吗？',True,'统一 404，owner 来自服务端验证身份，拒绝客户端 owner_id。',[('access','owner 只由服务端根据已验证身份生成，客户端传入 owner_id 应拒绝。'),('access','不存在、其他用户或已经删除的资源，对外统一返回 HTTP 404。')]),
('q07','Python 能否自行发布活动索引，发布前要核验什么？',True,'只能由 Java 发布；核验有效租约、文档可见性、Chunk 清单和向量完整性，同事务切换。',[('publish','只有 Java 服务可以发布活动索引版本；Python 只提交候选结果。'),('publish','发布前必须核验有效租约、文档可见性、Chunk 清单和向量完整性。'),('publish','所有核验与活动版本切换应在同一数据库事务完成。')]),
('q08','Embedding 和 LLM 分别接收什么演示内容？',True,'Embedding 接收获准分段；LLM 接收问题和获准检索片段；仅原创合成资料。',[('outbound','Embedding 请求发送获准的文档分段文本。'),('outbound','LLM 请求发送当前问题和检索到的获准片段。'),('outbound','演示仅使用原创合成内容，不含用户文档、密钥和个人资料。')]),
('q09','TXT/MD 偏移单位及端点规则是什么，PDF 页码从几开始？',True,'原始文本 Unicode 码点，从 0 开始、右端不含；PDF 页码从 1 开始。',[('locator','TXT/MD 偏移以原始文本的 Unicode 码点计数，从 0 开始，区间右端不含。'),('locator','PDF 页码从 1 开始，未提取到的页面坐标不得编造。')]),
('q10','演示模型请求总期限和自动重试次数是多少，超时如何返回？',True,'18 秒，0 次自动重试；HTTP 504 / PROCESSING_TIMEOUT。',[('timeout','演示的模型请求总期限为 18 秒，自动重试次数为 0。'),('timeout','超时对外返回 HTTP 504，错误码 PROCESSING_TIMEOUT。')]),
('q11','取消执行可以恢复已删文档或发布活动索引吗？',True,'不可以，取消只释放计算资源。',[('timeout','取消只释放计算资源，不能恢复已删除文档，也不能自行发布索引。')]),
('q12','Embedding 实际每百万 tokens 账单价格是多少？',False,'资料不足，应拒答；本语料未提供实际账单价格。',[]),
('q13','该接口的 OAuth2 scope 具体名称是什么？',False,'资料不足，应拒答；本语料未定义 OAuth2 scope。',[]),
('q14','示例串中文🙂A 中表情的码点区间是什么？',True,'[2,3)，不是 UTF-8 字节区间。',[('locator','示例串「中文🙂A」有 4 个 Unicode 码点；🙂 的区间是 [2,3)。')]),
('q15','生产部署机器的 GPU 型号是什么？',False,'资料不足，应拒答；本语料未提供生产硬件。',[]),
]


def build():
    ROOT.mkdir(parents=True,exist_ok=True)
    docs=[]; lookup={}
    for did, filename, text in DOCS:
        raw=text.encode('utf-8'); digest=sha256(raw).hexdigest()
        version='content-'+did+'-'+digest[:12]
        path=ROOT/'documents'/filename;path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
        doc={'id':did,'path':'documents/'+filename,'content_version_id':version,'sha256':digest,
             'format':path.suffix[1:],'bytes':len(raw),'characters':len(text),
             'origin':'Original synthetic 青竹 corpus authored for KnowFlow evaluation; not product limits or observed users.',
             'license':'CC0-1.0','external_api_allowed':True}
        docs.append(doc);lookup[did]=(doc,text)
    questions=[]
    for qid,prompt,answerable,answer,cites in QUESTIONS:
        evidence=[]
        for did,quote in cites:
            doc,text=lookup[did];start=text.index(quote);end=start+len(quote)
            evidence.append({'document_id':did,'content_version_id':doc['content_version_id'],
                'start':start,'end':end,'unit':'unicode_code_point','quote':quote,
                'line_start':text.count('\n',0,start)+1,'line_end':text.count('\n',0,end)+1})
        group='locator' if qid in ('q09','q14') else ('hardware-absent' if qid=='q15' else ('api' if qid in ('q01','q02','q13') else ('timeout' if qid in ('q10','q11') else qid)))
        questions.append({'id':qid,'question':prompt,'answerable':answerable,'reference_answer':answer,
                          'evidence':evidence,'split':'holdout' if qid in ('q09','q14','q15') else 'development',
                          'leakage_group':group,'annotation':'Author reference annotation, not a model prediction or user result.'})
    manifest={'dataset_id':'qingzhu-seed-v1','synthetic':True,'license':'CC0-1.0',
              'description':'Original synthetic evaluation only; all numerical limits refer to fictional 青竹, not KnowFlow.',
              'documents':docs}
    (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'questions.json').write_text(json.dumps(questions,ensure_ascii=False,indent=2)+'\n')
    print('built',len(docs),'original synthetic documents and',len(questions),'reference questions')

if __name__=='__main__':build()
