"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { defaultModelName, protocols, useLlmModels, type LlmInput, type LlmModel } from "@/components/workspace/llm-models";
import { modelErrorMessage } from "@/lib/model-errors";
import styles from "./settings.module.css";

const empty: LlmInput = { model_id: "", base_url: "", protocol: "chat_completions", api_key: "" };


export function ModelSettings() {
  const models = useLlmModels();
  const [editing, setEditing] = useState<string | null>(null);
  const [input, setInput] = useState(empty);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState("");

  function edit(model?: LlmModel) {
    setEditing(model?.id ?? "");
    setInput(model ? { model_id: model.model_id, base_url: model.base_url, protocol: model.protocol, api_key: "" } : empty);
    setConfirmDelete("");
    setError("");
    setNotice("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError("");
    setNotice("");
    try {
      await models.save(input, editing || undefined);
      setEditing(null);
      setInput(empty);
      setNotice("连接测试通过，模型已保存。");
    } catch (failure) {
      setError(modelErrorMessage((failure as { code?: unknown } | null)?.code));
    } finally {
      setPending(false);
    }
  }

  async function remove(id: string) {
    setPending(true);
    setError("");
    setNotice("");
    try {
      await models.remove(id);
      if (editing === id) { setEditing(null); setInput(empty); }
      setConfirmDelete("");
      setNotice("模型已删除。");
    } catch {
      setError("暂时无法删除模型，请刷新后重试。");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className={styles.modelSettings}>
      <div className={styles.modelRow}><strong>{defaultModelName}</strong><span>内置默认模型</span></div>
      {models.error && <div role="alert" className={styles.modelRow}><span>模型列表加载失败。</span><Button variant="secondary" size="sm" onClick={models.retry}>重试</Button></div>}
      {!models.catalog && !models.error && <p role="status">正在加载模型…</p>}
      {models.catalog?.enabled === false && <p>当前部署未启用自定义模型。</p>}
      {models.catalog?.enabled && <>
        {models.catalog.models.map((model) => (
          <div className={styles.modelRow} key={model.id}>
            <div><strong>{model.model_id}</strong><p>{new URL(model.base_url).hostname} · {protocols[model.protocol]} · {model.supports_tools ? "支持补充检索" : "基础问答"}</p><p>{model.last_probe_status === "success" && model.last_probe_at && Number.isFinite(Date.parse(model.last_probe_at)) ? <>最近通过检测：<time dateTime={model.last_probe_at}>{new Date(model.last_probe_at).toLocaleString("zh-CN")}</time></> : "尚无检测记录"}</p></div>
            <div className={styles.actions}>
              {confirmDelete === model.id ? <>
                <Button variant="danger" size="sm" disabled={pending} onClick={() => void remove(model.id)}>确认删除</Button>
                <Button variant="secondary" size="sm" disabled={pending} onClick={() => setConfirmDelete("")}>取消</Button>
              </> : <>
                <Button variant="secondary" size="sm" disabled={pending} onClick={() => edit(model)}>编辑</Button>
                <Button variant="secondary" size="sm" disabled={pending} onClick={() => setConfirmDelete(model.id)}>删除</Button>
              </>}
            </div>
          </div>
        ))}
        {editing === null ? <Button variant="secondary" size="sm" onClick={() => edit()}>添加自定义模型</Button> : (
          <form className={styles.modelForm} onSubmit={(event) => void submit(event)}>
            <label>Base URL<input type="url" maxLength={1024} required value={input.base_url} placeholder="https://api.example.com/v1" onChange={(event) => setInput({ ...input, base_url: event.target.value })} /></label>
            <label>API 密钥<input type="password" autoComplete="new-password" maxLength={2048} required={!editing} value={input.api_key} placeholder={editing ? "留空沿用现有密钥" : undefined} onChange={(event) => setInput({ ...input, api_key: event.target.value })} /></label>
            <label>接口协议<select value={input.protocol} onChange={(event) => setInput({ ...input, protocol: event.target.value as LlmInput["protocol"] })}>
              {Object.entries(protocols).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select></label>
            <label>模型 ID<input maxLength={160} autoComplete="off" required value={input.model_id} onChange={(event) => setInput({ ...input, model_id: event.target.value })} /></label>
            <p className={styles.note}>连接测试会使用你的密钥向此服务发送固定测试文本，可能产生少量费用。</p>
            <div className={styles.actions}>
              <Button type="submit" size="sm" disabled={pending}>{pending ? "正在测试连接…" : "测试并保存"}</Button>
              <Button type="button" variant="secondary" size="sm" disabled={pending} onClick={() => { setEditing(null); setInput(empty); setError(""); }}>取消</Button>
            </div>
          </form>
        )}
      </>}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
