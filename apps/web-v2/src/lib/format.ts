import type { ApiError, QuestionHistory } from "@/services/api";

const questionStatus: Record<string, string> = {
  QUEUED: "等待处理",
  RUNNING: "正在生成",
  PROCESSING: "正在生成",
  SUCCEEDED: "已完成",
  FAILED: "处理失败",
  CANCELLED: "已取消",
};

const documentStatus: Record<string, string> = {
  QUEUED: "等待处理",
  RUNNING: "正在建立索引",
  PROCESSING: "正在处理",
  SUCCEEDED: "已就绪",
  READY: "已就绪",
  FAILED: "处理失败",
  CANCELLED: "已取消",
};

export function questionStatusLabel(value: string) {
  return questionStatus[value.toUpperCase()] ?? value;
}

export function documentStatusLabel(value: string) {
  return documentStatus[value.toUpperCase()] ?? value;
}

export function formatLabel(value: string) {
  const format = (value || "").toUpperCase();
  return format === "PDF" || format === "MD" ? format : "TXT";
}

export function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 KB";
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

const relativeFormat = new Intl.RelativeTimeFormat("zh-CN", { numeric: "auto" });
const dateFormat = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });

export function relativeTime(iso?: string | null) {
  if (!iso) return "";
  const timestamp = Date.parse(iso);
  if (!Number.isFinite(timestamp)) return "";
  const minutes = Math.round((timestamp - Date.now()) / 60_000);
  if (Math.abs(minutes) < 1) return "刚刚";
  if (Math.abs(minutes) < 60) return relativeFormat.format(minutes, "minute");
  if (Math.abs(minutes) < 1440) return relativeFormat.format(Math.round(minutes / 60), "hour");
  if (Math.abs(minutes) < 10_080) return relativeFormat.format(Math.round(minutes / 1440), "day");
  return dateFormat.format(timestamp);
}

export function messageOf(error: unknown) {
  if (error instanceof Error) {
    const status = (error as ApiError).status;
    const code = (error as ApiError).code;
    if (status === 401) return "登录状态已失效，请重新登录。";
    if (status === 403) return "你没有执行这个操作的权限。";
    if (status === 404 || code === "NOT_FOUND") return "内容不存在或你无权访问。";
    if (status === 409) return "当前状态不允许这个操作，请刷新后再试。";
    if (status === 413) return "文件超过大小限制。";
    if (status === 502) return "服务暂时不可用，请稍后重试。";
    if (status && status >= 500) return "服务暂时不可用，请稍后重试。";
    if (error.name === "AbortError") return "请求已停止。";
    return error.message;
  }
  return "操作未能完成，请稍后重试。";
}

export type QuestionGroup = { label: string; items: QuestionHistory[] };

export function groupQuestions(items: QuestionHistory[]): QuestionGroup[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterday = today - 86_400_000;
  const groups: QuestionGroup[] = [
    { label: "今天", items: [] },
    { label: "昨天", items: [] },
    { label: "更早", items: [] },
  ];

  for (const item of items) {
    const time = item.finished_at ? Date.parse(item.finished_at) : Number.NaN;
    if (!Number.isFinite(time) || time >= today) groups[0].items.push(item);
    else if (time >= yesterday) groups[1].items.push(item);
    else groups[2].items.push(item);
  }

  return groups.filter((group) => group.items.length > 0);
}
