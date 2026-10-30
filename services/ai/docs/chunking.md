# KF2-017：可复现分段与来源定位

状态：分段器已接入本机 `local` 的 `0.2.0-draft.6` `IndexWorker` 并通过本地回归；独立 Q 审阅和 M 消费确认仍待完成。此模块本身是纯 Python 处理代码，不是 HTTP 入口或数据库写入者；lease-scoped 调度由 worker 执行，Chunk/向量写入经 Java gateway 完成。

## 配置与不变量

- 默认配置 `max_codepoints=800`、`overlap_codepoints=100`，配置会生成稳定的 `chunking_profile_id`；改变任一值会改变 profile 与 chunk identity。
- 分段在标题、段落边界优先；超长段落尽量在句末或空白处分开，找不到可用边界时按码点上限硬切。原文不 strip、不换行归一化、不改写 Markdown。
- 每个块的正文始终是一个 `TextBlock` 正文的连续原文切片。文本 `Locator` 使用原文 Unicode 码点 `[start,end)`；PDF 使用物理页码，块只在同一页内切分，绝不跨页合并。
- `chunk_id` 由来源身份/版本、文件哈希、解析配置、分段配置、页内位置和正文哈希确定；相同输入和配置可重复生成相同 ID。内容版本或配置变化产生新身份。
- 重叠上限为配置码点数；为了避免从段落或句子中间开始，必要时向后对齐到边界，因此实际重叠可以更短。PDF 的公开来源定位只有页码，ID 另包含页内块位置，以区别同页重复内容。

## 复现

```sh
uv run --project services/ai --frozen pytest services/ai/tests/test_chunking.py -q
```

回归覆盖确定性、内容版本隔离、中文/emoji/CRLF 原文切片、段落与标题边界、默认配置、PDF 空白物理页和不跨页，以及现有 15 题中所有有答案来源仍能在切块内按原始区间复核。测试不调用模型或数据库。

此开发基线没有证明真实文件上传、生产吞吐、token 预算或完整引用授权；这些仍需 A 的来源接口及后续索引/问答链路验证。
