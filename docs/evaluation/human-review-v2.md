# 60 题人工审核操作

这批题的资料是原创合成数据，不是真实用户材料。`evaluation/data/seed-v2-candidate/annotation-template.json` 是不含机器答案的审核模板；先复制到仓库外的私有目录并填写。原文在同目录 `documents/`，`source_catalog` 记录文档 ID 和版本。

每题独立填写 `answerable`、`reference_answer` 和 `evidence`，确认后设 `annotation_status` 为 `reviewed`。不可回答题的 evidence 为 `[]`；可回答题逐条记录文档 ID、内容版本、原文摘录、Unicode 码点起止位置（左闭右开）和从 1 开始的行号，格式参考 `evaluation/data/tools/split_candidates.py` 的校验规则。不要在独立判断前查看 `machine-draft-annotations.json`。

完成后由审核者记录身份、带时区审核时间，并把填写后的私有文件交给执行者用于格式转换和校验。现有 finalizer 还要求外层 `status: human_reviewed`、`review_version: 1`、`candidate_questions_sha256`（取同目录 `split-manifest.json` 的 `input_sha256`）以及 `reviewer: {id, reviewed_at}`；原模板的摘要与 annotations 应保持对应。校验失败先修正标注，不修改原始候选资料。

现有公开 40/20 分配仅供开发和验证。另建 20 道题的盲测资料和答案由用户在仓库及开发聊天之外保管；冻结代码和配置前不向实现方展示。
