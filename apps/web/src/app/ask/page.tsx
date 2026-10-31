"use client";

import { useEffect, useState } from "react";
import { api, isMockMode } from "../../lib/api-client";
import { mockApi } from "../../lib/mock";
import { KnowledgeBase, QuestionAnswer, SourceRef } from "../../lib/types";
import { EmptyState, ErrorBox, Loading } from "../../components/states";

function formatLocator(s: SourceRef): string {
  if (s.locator.kind === "page") return `PDF 第 ${s.locator.page} 页`;
  return `字符区间 ${s.locator.start}–${s.locator.end}（从 0 起，右端不含）`;
}

export default function AskPage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [kbId, setKbId] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<QuestionAnswer | null>(null);
  const [selected, setSelected] = useState<SourceRef | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const mock = isMockMode();

  useEffect(() => {
    (async () => {
      try {
        const list = mock ? await mockApi.listKnowledgeBases() : await api.listKnowledgeBases();
        setKbs(list);
        if (list.length > 0) setKbId(list[0].id);
      } catch {
        // 未登录或加载失败时，页面仍可展示输入框与说明，错误在提交时提示。
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onAsk(e: React.FormEvent) {
    e.preventDefault();
    if (!kbId || !question.trim()) return;
    setLoading(true);
    setError("");
    setAnswer(null);
    setSelected(null);
    try {
      const result = mock
        ? await mockApi.askQuestion(kbId, question.trim())
        : await api.askQuestion(kbId, question.trim());
      setAnswer(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提问失败。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h1>问答与来源核验</h1>
      <p className="muted">
        单轮问答：每次提问独立检索，历史不作为多轮上下文。公开请求只包含问题，不得提交 owner、快照或索引范围。
        有答案必须有至少一个来源；无证据时明确返回无答案，不编造页码或引用。
      </p>
      {error ? <ErrorBox message={error} /> : null}
      <form onSubmit={onAsk}>
        <label htmlFor="ask-kb">知识库</label>
        <select id="ask-kb" value={kbId} onChange={(e) => setKbId(e.target.value)} required>
          <option value="">请选择知识库</option>
          {kbs.map((kb) => (
            <option key={kb.id} value={kb.id}>
              {kb.name}
            </option>
          ))}
        </select>
        <label htmlFor="ask-q">问题</label>
        <textarea
          id="ask-q"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="例如：删除文档后，相关引用还能打开原文吗？"
          required
        />
        <div className="row" style={{ marginTop: 12 }}>
          <button type="submit" disabled={loading || !kbId}>
            {loading ? "检索中…" : "提问"}
          </button>
        </div>
      </form>
      {loading ? <Loading label="正在检索与生成…" /> : null}
      {answer && !answer.has_answer ? (
        <EmptyState text="无证据：当前知识库中没有支持该问题的来源，未返回答案。" />
      ) : null}
      {answer && answer.has_answer ? (
        <div>
          <div className="card">
            <h2>回答</h2>
            <p style={{ whiteSpace: "pre-wrap" }}>{answer.answer}</p>
            {answer.index_version_id ? (
              <p className="muted">索引版本：{answer.index_version_id}</p>
            ) : null}
          </div>
          <h2>来源（点击查看定位与片段）</h2>
          {answer.sources.slice(0, 5).map((s) => (
            <div className="card" key={s.source_id}>
              <button className="secondary" onClick={() => setSelected(s)}>
                [{s.source_id}] {formatLocator(s)}
              </button>
              <p className="muted">文档 {s.document_id}</p>
            </div>
          ))}
          {selected ? (
            <div className="card">
              <h2>原文定位</h2>
              <p>
                来源 {selected.source_id} · {formatLocator(selected)}
              </p>
              <div className="snippet">{selected.snippet}</div>
              <p className="muted">
                完整原文代理读取（鉴权后的文件接口）与 PDF 页码预览属后续任务；此处只展示定位与片段，
                不编造页码或坐标。
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
