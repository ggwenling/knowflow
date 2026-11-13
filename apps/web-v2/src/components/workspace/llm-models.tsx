"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "@/services/api";

export const protocols = {
  chat_completions: "OpenAI Chat Completions",
  responses: "OpenAI Responses",
  anthropic_messages: "Anthropic Messages",
};

export const defaultModelName = "DeepSeek V4.1 Flash";

export type LlmModel = {
  id: string;
  model_id: string;
  base_url: string;
  protocol: keyof typeof protocols;
  supports_tools: boolean;
  last_probe_at?: string | null;
  last_probe_status?: "success" | null;
};

export type LlmInput = Pick<LlmModel, "model_id" | "base_url" | "protocol"> & { api_key: string };
type Catalog = { enabled: boolean; models: LlmModel[] };

function useCatalog() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [selected, select] = useState("");
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const abort = new AbortController();
    void api<Catalog>("llm-models", { signal: abort.signal }).then((result) => {
      if (!abort.signal.aborted) {
        setCatalog(result);
        setError(false);
      }
    }).catch(() => { if (!abort.signal.aborted) setError(true); });
    return () => abort.abort();
  }, [reload]);

  const retry = useCallback(() => { setError(false); setReload((value) => value + 1); }, []);
  const save = useCallback(async (input: LlmInput, id?: string) => {
    const model = await api<LlmModel>(id ? `llm-models/${id}` : "llm-models", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(input),
    });
    setCatalog((previous) => previous && ({ ...previous,
      models: [...previous.models.filter((item) => item.id !== model.id), model],
    }));
  }, []);
  const remove = useCallback(async (id: string) => {
    await api(`llm-models/${id}`, { method: "DELETE" });
    setCatalog((previous) => previous && ({ ...previous, models: previous.models.filter((model) => model.id !== id) }));
  }, []);

  return useMemo(() => ({ catalog, error, selected, select, retry, save, remove }),
    [catalog, error, selected, retry, save, remove]);
}

const ModelContext = createContext<ReturnType<typeof useCatalog> | null>(null);

export function LlmModelsProvider({ children }: { children: ReactNode }) {
  return <ModelContext.Provider value={useCatalog()}>{children}</ModelContext.Provider>;
}

export function useLlmModels() {
  const context = useContext(ModelContext);
  if (!context) throw new Error("Model context is unavailable.");
  return context;
}

export function ModelSelect({ className, disabled }: { className?: string; disabled?: boolean }) {
  const { catalog, selected, select } = useLlmModels();
  const models = catalog?.models ?? [];
  return (
    <select className={className} aria-label="选择回答模型" value={selected} disabled={disabled}
      onChange={(event) => select(event.target.value)}>
      <option value="">{defaultModelName}</option>
      {selected && !models.some((model) => model.id === selected) && <option value={selected}>所选模型不可用</option>}
      {models.map((model) => (
        <option key={model.id} value={model.id}>{model.model_id} · {new URL(model.base_url).hostname}</option>
      ))}
    </select>
  );
}
