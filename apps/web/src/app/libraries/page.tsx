"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, isMockMode } from "../../lib/api-client";
import { mockApi } from "../../lib/mock";
import { KnowledgeBase } from "../../lib/types";
import { EmptyState, ErrorBox, Loading } from "../../components/states";

function isAuthed(): boolean {
  if (typeof window === "undefined") return false;
  return !!window.localStorage.getItem("knowflow_token");
}

export default function LibrariesPage() {
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const mock = isMockMode();
  const authed = isAuthed();

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = mock ? await mockApi.listKnowledgeBases() : await api.listKnowledgeBases();
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (authed) void load();
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    try {
      if (mock) {
        setItems((prev) => [
          ...prev,
          { id: `kb-mock-${Date.now()}`, name: name.trim(), status: "ACTIVE", document_count: 0 },
        ]);
      } else {
        const created = await api.createKnowledgeBase({ name: name.trim() });
        setItems((prev) => [...prev, created]);
      }
      setName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败。");
    } finally {
      setCreating(false);
    }
  }

  async function onDelete(kbId: string) {
    if (!window.confirm("删除知识库将同步撤销其文档可见性，确认删除吗？")) return;
    try {
      if (!mock) await api.deleteKnowledgeBase(kbId);
      setItems((prev) => prev.filter((kb) => kb.id !== kbId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败。");
    }
  }

  if (!authed) {
    return (
      <div>
        <h1>知识库</h1>
        <p className="muted">
          未登录。请先 <Link href="/login">登录</Link>；未登录状态不展示他人或任何知识库内容。
        </p>
      </div>
    );
  }

  return (
    <div>
      <h1>知识库</h1>
      <p className="muted">列表只包含当前所有者且 ACTIVE 的知识库；不存在、他人或已删统一返回 404，不作区分。</p>
      {error ? <ErrorBox message={error} onRetry={load} /> : null}
      {loading ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState text="还没有知识库，先创建一个吧。" />
      ) : (
        items.map((kb) => (
          <div className="card" key={kb.id}>
            <div className="row">
              <Link href={`/libraries/${kb.id}`}>{kb.name}</Link>
              <span className="tag">{kb.status}</span>
              {typeof kb.document_count === "number" ? (
                <span className="muted">{kb.document_count} 篇文档</span>
              ) : null}
              <button className="danger" onClick={() => void onDelete(kb.id)}>
                删除
              </button>
            </div>
          </div>
        ))
      )}
      <div className="card">
        <h2>新建知识库</h2>
        <form onSubmit={onCreate}>
          <label htmlFor="kb-name">名称</label>
          <input
            id="kb-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例如：项目规范"
            required
          />
          <div className="row" style={{ marginTop: 12 }}>
            <button type="submit" disabled={creating}>
              {creating ? "创建中…" : "创建"}
            </button>
          </div>
          <p className="muted">创建请求不接受 owner 字段；所有者只来自服务器验证后的凭证。</p>
        </form>
      </div>
    </div>
  );
}
