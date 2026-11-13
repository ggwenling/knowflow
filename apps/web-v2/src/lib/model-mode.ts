export type ModelMode = "synthetic" | "external" | "unknown";

export function configuredModelMode(): ModelMode {
  const mode = process.env.KNOWFLOW_WEB_MODEL_MODE;
  return mode === "synthetic" || mode === "external" ? mode : "unknown";
}
