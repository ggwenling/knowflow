"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, isMockMode } from "../../../lib/api-client";
import { mockApi } from "../../../lib/mock";
import { DocumentItem, TaskItem } from "../../../lib/types";
import { EmptyState, ErrorBox, Loading } from "../../../components/states";

export default function KnowledgeBaseDetailPage() {
  const params = useParams();
  const kbId = params.kbId as string;
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [tasks, setTasks] = useState<Record<string, TaskItem>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadNote, setUploadNote] = useState("");
  const mock = isMockMode();

  async function load() {
    setLoading(true);
    setError("");
    try {
      const list = mock ? await mockApi.listDocuments(kbId) : await api.listDocuments(kbId);
      setDocs(list);
      if (mock) {
        const next: Record<string, TaskItem> = {};
        for (const d of list) {
          if (d.task_id) next[d.task_id] = await mockApi.getTask(d.task_id);
        }
        setTasks(next);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setUploadNote("");
    try {
      if (mock) {
        const ext = file.name.split(".").pop()?.toLowerCase();
        const format = ext === "pdf" ? "pdf" : ext === "md" ? "md" : "txt";
        setDocs((prev) => [
          ...prev,
          {
            id: `doc-mock-${Date.now()}`,
            knowledge_base_id: kbId,
            name: file.name,
            format,
            status: "QUEUED",
            index_version_id: null,
            task_id: null,
          },
        ]);
        setUploadNote("Mock 上传已接受：任务 QUEUED；只有已发布索引才显示 READY，上传成功不等于 READY。");
      } else {
        const accepted = await api.uploadDocument(kbId, file);
        setUploadNote(`已接受，文档 ${accepted.document_id}，任务 ${accepted.task_id}（QUEUED）。`);
        await load();
      }
      setFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败。");
    } finally {
      setUploading(false);
    }
  }

  async function onDeleteDocument(docId: string) {
    if (!window.confirm("删除文档将提交逻辑失效并安排清理，确认删除吗？")) return;
    try {
      if (!mock) await api.deleteDocument(docId);
      setDocs((prev) => prev.filter((d) => d.id !== docId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败。");
    }
  }

  return (
    <div>
      <p>
        <Link href="/libraries">← 知识库列表</Link>
      </p>
      <h1>知识库详情</h1>
      <p className="muted">知识库 ID：{kbId}</p>
      {error ? <ErrorBox message={error} onRetry={load} /> : null}
      <div className="card">
        <h2>上传文档</h2>
        <form onSubmit={onUpload}>
          <label htmlFor="doc-file">文件（TXT / MD / 文本型 PDF）</label>
          <input
            id="doc-file"
            type="file"
            accept=".txt,.md,.pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            required
          />
          <p className="muted">
            开发上限：文件 8 MiB、PDF 200 页、TXT/MD 文本 200,000 码点；仅接受扩展名与文件签名匹配的
            txt/md/pdf。上传前请注意：Embedding 候选 BAAI/bge-m3（1024 维），生成候选 DeepSeek（deepseek-flash
            别名），数据去向以 KF2-003 运行记录为准；上传成功不等于 READY，仍需索引。
          </p>
          <div className="row" style={{ marginTop: 12 }}>
            <button type="submit" disabled={uploading || !file}>
              {uploading ? "上传中…" : "上传"}
            </button>
          </div>
        </form>
        {uploadNote ? <p className="muted">{uploadNote}</p> : null}
      </div>
      <h2>文档</h2>
      {loading ? (
        <Loading />
      ) : docs.length === 0 ? (
        <EmptyState text="该知识库还没有文档。" />
      ) : (
        docs.map((d) => (
          <div className="card" key={d.id}>
            <div className="row">
              <strong>{d.name}</strong>
              <span className="tag">{d.format}</span>
              <span className="tag">{d.status}</span>
              {d.index_version_id ? <span className="muted">索引 {d.index_version_id}</span> : null}
              {d.task_id && tasks[d.task_id] ? (
                <span className="muted">任务 {tasks[d.task_id].status}</span>
              ) : null}
              <button className="danger" onClick={() => void onDeleteDocument(d.id)}>
                删除文档
              </button>
            </div>
            <p className="muted">
              {d.status === "READY"
                ? "已发布索引，可检索。"
                : "处理中或未就绪；更新失败时旧活动版本继续可用。刷新后状态可恢复。"}
            </p>
          </div>
        ))
      )}
      <p className="muted">
        文档列表默认 limit=50；只包含当前用户、活动知识库下未删除文档。删除提交后，新请求不再检索或引用该文档。
      </p>
    </div>
  );
}
