import type { Page, Route } from "@playwright/test";

export const base = { id: "base-1", name: "优化验收资料库", status: "ACTIVE" };
export const document = { id: "doc-1", original_name: "资料.txt", status: "READY", active_index_version_id: "index-1", format: "txt", byte_size: 128 };
export const question = (index: number) => ({ question_id: `q-${index}`, knowledge_base_id: base.id, question: `历史问题 ${index}`, status: "SUCCEEDED", finished_at: "2026-11-07T12:00:00Z" });

export async function mockWorkspace(page: Page, override?: (route: Route, url: URL) => Promise<boolean>) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (await override?.(route, url)) return;
    const path = url.pathname;
    if (path === "/api/mode") return route.fulfill({ json: { mode: "synthetic" } });
    if (path === "/api/v1/me") return route.fulfill({ json: { user_id: "optimization-user", email: "optimization@example.test" } });
    if (path === "/api/v1/knowledge-bases") return route.fulfill({ json: { items: [base], has_more: false } });
    if (path === `/api/v1/knowledge-bases/${base.id}`) return route.fulfill({ json: base });
    if (path.endsWith("/documents")) return route.fulfill({ json: { items: [document], has_more: false } });
    if (path === "/api/v1/questions") return route.fulfill({ json: { items: [], has_more: false } });
    return route.fulfill({ status: 404, json: { code: "NOT_FOUND", message: "内容不存在或你无权访问。" } });
  });
}
