// Local-only metadata: an empty string means the original ask used the default;
// absence means a stored question's original model is unknown to this client.
export type LocalQuestionModel = { requestedModelId?: string };

export function questionRequestBody(question: string, modelId?: string) {
  return { question, ...(modelId ? { llm_model_id: modelId } : {}) };
}

export function retryQuestionArgs(
  answer: LocalQuestionModel & { question: string; knowledge_base_id: string },
  catalog: { enabled: boolean; models: { id: string }[] } | null,
  catalogError = false,
): [string, string, string?] {
  const modelId = answer.requestedModelId;
  if (modelId === undefined) {
    throw new Error("无法确认原问答使用的模型，请重新编辑问题并明确选择模型。");
  }
  if (modelId && (catalogError || !catalog?.enabled || !catalog.models.some((model) => model.id === modelId))) {
    throw new Error("原问答使用的模型已删除或不可用。请检查模型配置，或重新编辑问题并切换到默认模型。");
  }
  return [answer.question, answer.knowledge_base_id, modelId || undefined];
}
