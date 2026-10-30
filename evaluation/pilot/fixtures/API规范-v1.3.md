# API规范 v1.3

状态：已发布
生效日期：2026-09-15
资料说明：KnowFlow 试用演练专用的完全虚构 API 规范。

## 2.1 创建索引任务

请求：POST /v1/index-jobs，JSON。
必填字段：
- documentId：UUID。
- profileId：字符串。
chunkSize：可选整数，默认 400，允许范围 200–800。
waitMs：可选整数，允许范围 100–10000 毫秒。
成功响应：HTTP 202，返回 jobId 供后续查询。
