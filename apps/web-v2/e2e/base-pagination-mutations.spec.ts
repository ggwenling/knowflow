import { expect, test } from "@playwright/test";
import { base, document, mockWorkspace } from "./helpers/workspace";

test("a valid newly created deep link keeps its documents and uploads in the route base", async ({ page }) => {
  const server = Array.from({ length: 51 }, (_, index) => ({ ...base, id: `old-${index + 1}`, name: `旧知识库 ${index + 1}` }));
  const fresh = { ...base, id: "fresh-base", name: "新知识库 B" };
  const freshDocument = { ...document, id: "fresh-doc", original_name: "B 的资料.txt" };
  const oldDocument = { ...document, id: "old-doc", original_name: "A 的资料.txt" };
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let pendingPage = false;
  let pageFinished = false;
  const documentReads: string[] = [];
  const uploads: string[] = [];
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname === "/api/v1/knowledge-bases") {
      const offset = Number(url.searchParams.get("offset"));
      if (offset) { pendingPage = true; await gate; }
      const items = server.slice(offset, offset + 50);
      const has_more = offset + items.length < server.length;
      await route.fulfill({ json: { items, has_more } });
      if (offset) pageFinished = true;
      return true;
    }
    if (url.pathname === `/api/v1/knowledge-bases/${fresh.id}`) {
      await route.fulfill({ json: fresh });
      return true;
    }
    if (url.pathname.endsWith("/documents")) {
      const owner = url.pathname.split("/").at(-2)!;
      if (route.request().method() === "POST") {
        uploads.push(owner);
        await route.fulfill({ status: 202, json: { document_id: "uploaded-to-b", task_id: "new-upload-task" } });
      } else {
        documentReads.push(owner);
        await route.fulfill({ json: { items: [owner === fresh.id ? freshDocument : oldDocument], has_more: false } });
      }
      return true;
    }
    if (url.pathname === "/api/v1/documents/uploaded-to-b") {
      await route.fulfill({ json: { ...freshDocument, id: "uploaded-to-b", original_name: "route-scope.txt", latest_task_id: "new-upload-task", latest_task_status: "SUCCEEDED" } });
      return true;
    }
    if (url.pathname === "/api/v1/tasks/new-upload-task") {
      await route.fulfill({ json: { task_id: "new-upload-task", status: "SUCCEEDED", failure_code: null } });
      return true;
    }
    return false;
  });
  try {
    // A separate client creates B after this list's first page was read.
    await page.goto("/knowledge-bases");
    await expect.poll(() => pendingPage).toBe(true);
    server.unshift(fresh);
    // The shipped Next router models opening an externally supplied deep link
    // without reloading the workspace or dropping its pending list request.
    await page.evaluate(id => {
      const client = window as unknown as { next: { router: { push(path: string): void } } };
      client.next.router.push(`/knowledge-bases/${id}`);
    }, fresh.id);
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${fresh.id}$`));
    await expect(page.getByRole("heading", { name: fresh.name, exact: true })).toBeVisible();
    await expect(page.getByRole("article").filter({ hasText: freshDocument.original_name })).toBeVisible();
    documentReads.length = 0;
    release();
    await expect.poll(() => pageFinished).toBe(true);
    // Waiting for the create control to enable also observes the final list render.
    await page.getByRole("textbox", { name: "新知识库名称" }).fill("分页已结束");
    await expect(page.getByRole("button", { name: "创建知识库", exact: true })).toBeEnabled();
    await page.locator('input[type="file"]').first().setInputFiles({ name: "route-scope.txt", mimeType: "text/plain", buffer: Buffer.from("synthetic route scope fixture") });
    await expect.poll(() => uploads.length).toBe(1);
    expect(uploads).toEqual([fresh.id]);
    expect(documentReads.every(id => id === fresh.id)).toBe(true);
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${fresh.id}$`));
    await expect(page.getByRole("heading", { name: fresh.name, exact: true })).toBeVisible();
    await expect(page.getByRole("article").filter({ hasText: oldDocument.original_name })).toHaveCount(0);
  } finally { release(); }
});

test("a late conversation selection cannot redirect a detail route's documents or uploads", async ({ page }) => {
  const other = { ...base, id: "route-base-b", name: "路由知识库 B" };
  const ownDocument = { ...document, id: "route-document-b", original_name: "路由 B 的资料.txt" };
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let pendingQuestion = false;
  let questionReturned = false;
  const uploads: string[] = [];
  await mockWorkspace(page, async (route, url) => {
    if (url.pathname === "/api/v1/knowledge-bases") {
      await route.fulfill({ json: { items: [base, other], has_more: false } });
      return true;
    }
    if (url.pathname === "/api/v1/questions/late-question") {
      pendingQuestion = true;
      await gate;
      await route.fulfill({ json: { question_id: "late-question", knowledge_base_id: base.id, question: "旧问答", status: "SUCCEEDED", finished_at: null, answer: "旧答案", has_answer: false, failure_code: null, sources: [] } });
      questionReturned = true;
      return true;
    }
    if (url.pathname === `/api/v1/knowledge-bases/${other.id}`) {
      await route.fulfill({ json: other });
      return true;
    }
    if (url.pathname.endsWith("/documents")) {
      const owner = url.pathname.split("/").at(-2)!;
      if (route.request().method() === "POST") {
        uploads.push(owner);
        await route.fulfill({ status: 202, json: { document_id: "late-upload", task_id: "late-upload-task" } });
      } else {
        await route.fulfill({ json: { items: [owner === other.id ? ownDocument : document], has_more: false } });
      }
      return true;
    }
    return false;
  });
  try {
    await page.goto("/conversations/late-question");
    await expect.poll(() => pendingQuestion).toBe(true);
    await page.getByRole("link", { name: other.name, exact: true }).click();
    await expect(page.getByRole("heading", { name: other.name, exact: true })).toBeVisible();
    await expect(page.getByRole("article").filter({ hasText: ownDocument.original_name })).toBeVisible();
    release();
    await expect.poll(() => questionReturned).toBe(true);
    // Observe the late selection through the sidebar before issuing a write.
    await expect(page.locator('aside a[href="/knowledge-bases/base-1"]').first()).toHaveClass(/baseActive/);
    await page.locator('input[type="file"]').first().setInputFiles({ name: "late-selection.txt", mimeType: "text/plain", buffer: Buffer.from("synthetic late selection fixture") });
    await expect.poll(() => uploads.length).toBe(1);
    expect(uploads).toEqual([other.id]);
    await expect(page.getByRole("article").filter({ hasText: ownDocument.original_name })).toBeVisible();
    await expect(page.getByRole("article").getByText(document.original_name, { exact: true })).toHaveCount(0);
  } finally { release(); }
});

for (const timing of ["executed after deletion", "captured before deletion"] as const) {
  test(`deletion restarts OFFSET pagination with a pending page ${timing}`, async ({ page }) => {
    const server = Array.from({ length: 51 }, (_, index) => ({ ...base, id: `base-${index + 1}`, name: `知识库 ${index + 1}` }));
    const deletedBase = server[0];
    const lastBase = server.at(-1)!;
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    let pendingPage = false;
    let deleted = false;
    let restarted = false;
    await mockWorkspace(page, async (route, url) => {
      if (url.pathname === `/api/v1/knowledge-bases/${deletedBase.id}` && route.request().method() === "DELETE") {
        server.splice(server.findIndex(item => item.id === deletedBase.id), 1);
        deleted = true;
        await route.fulfill({ status: 204 });
        return true;
      }
      if (url.pathname !== "/api/v1/knowledge-bases") return false;
      const offset = Number(url.searchParams.get("offset"));
      const captured = server.slice(offset, offset + 50);
      if (offset === 50) { pendingPage = true; await gate; }
      if (deleted && offset === 0) restarted = true;
      const items = timing === "captured before deletion" ? captured : server.slice(offset, offset + 50);
      await route.fulfill({ json: { items, has_more: offset + items.length < server.length } }).catch(() => {});
      return true;
    });
    try {
      await page.goto("/knowledge-bases");
      await expect.poll(() => pendingPage).toBe(true);
      await expect(page.getByRole("article")).toHaveCount(50);
      await page.getByRole("button", { name: `删除知识库 ${deletedBase.name}`, exact: true }).click();
      await page.getByRole("button", { name: "确认删除", exact: true }).click();
      await expect.poll(() => deleted).toBe(true);
      // Also cover an old snapshot arriving only after the replacement read.
      if (timing === "captured before deletion") {
        await expect.poll(() => restarted).toBe(true);
        await expect(page.getByRole("button", { name: `删除知识库 ${lastBase.name}`, exact: true })).toBeVisible();
      }
      release();
      await expect(page.getByRole("button", { name: `删除知识库 ${lastBase.name}`, exact: true })).toBeVisible();
      await expect(page.getByRole("article")).toHaveCount(50);
      await expect(page.getByRole("button", { name: `删除知识库 ${deletedBase.name}`, exact: true })).toHaveCount(0);
      expect(restarted).toBe(true);
      expect(server).toHaveLength(50);
    } finally { release(); }
  });
}
