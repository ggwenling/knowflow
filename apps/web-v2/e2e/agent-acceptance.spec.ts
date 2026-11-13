import { expect, test, type Page, type Locator } from "@playwright/test";
import { randomBytes, randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

// Actual browser + API + database + object store + synthetic AI; no happy-path routes are mocked.
test.use({ trace: "off" }); // Never persist authentication bodies/passwords in a browser trace.
test("M1/M2/M3 agent acceptance on the real Compose stack", async ({ page, browser, baseURL }) => {
  test.setTimeout(600_000);
  test.info().annotations.push({ type: "scope", description: "real Compose / synthetic business model; excludes paid-model quality" });
  const out = resolve(process.env.KNOWFLOW_ACCEPTANCE_OUT_DIR ?? test.info().outputPath("agent-evidence"));
  await mkdir(out, { recursive: true });
  const model = process.env.KNOWFLOW_ACCEPTANCE_MODEL ?? "CI runner (not an agent signature)";
  const project = process.env.KNOWFLOW_ACCEPTANCE_PROJECT;
  await page.addInitScript(() => {
    const captures: Record<string, Promise<string>> = {};
    (window as unknown as { agentStreams: typeof captures }).agentStreams = captures;
    const original = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const response = await original(input, init);
      if (String(input).endsWith("/questions/stream") && typeof init?.body === "string") {
        const text = JSON.parse(init.body).question as string;
        if (!text.startsWith("[e2e:slow]")) captures[text] = response.clone().text();
      }
      return response;
    };
  });
  const manifest = {
    started_at: new Date().toISOString(), finished_at: "", status: "INCOMPLETE",
    executor: { model, browser: `Chromium ${browser.version()}`, environment: `${process.platform}/${process.arch}; ${process.version}; ${baseURL}` },
    product_mode: "synthetic", cases: [] as { id: string; status: string; at: string; evidence: string; detail: unknown }[],
    signature: "", cleanup: "pending",
  };
  const requests: { method: string; url: string; type: string }[] = [];
  page.on("request", request => {
    const url = new URL(request.url());
    if (["http:", "https:"].includes(url.protocol)) requests.push({ method: request.method(), url: url.origin + url.pathname, type: request.resourceType() });
  });
  const save = () => writeFile(resolve(out, "modules-manifest.json"), JSON.stringify(manifest, null, 2));
  async function step(id: string, action: () => Promise<unknown>) {
    await test.step(id, async () => {
      const evidence = `${id}.png`;
      try {
        const detail = await action();
        await page.screenshot({ path: resolve(out, evidence) });
        manifest.cases.push({ id, status: "PASS", at: new Date().toISOString(), evidence, detail: detail ?? null });
      } catch (error) {
        await page.screenshot({ path: resolve(out, evidence) }).catch(() => undefined);
        manifest.cases.push({ id, status: "FAIL", at: new Date().toISOString(), evidence, detail: String(error) });
        throw error;
      } finally { await save(); }
    });
  }
  async function api(path: string, options: Parameters<Page["request"]["fetch"]>[1] = {}) {
    const response = await page.request.fetch(`/api/v1/${path}`, { ...options, headers: { Origin: baseURL!, ...options?.headers } });
    expect(response.ok(), `${path}: HTTP ${response.status()}`).toBeTruthy();
    return response.status() === 204 ? null : response.json();
  }
  async function createBase(name: string) {
    await page.getByLabel("新知识库名称").fill(name);
    const accepted = page.waitForResponse(r => r.url().endsWith("/api/v1/knowledge-bases") && r.request().method() === "POST");
    await page.getByRole("button", { name: "创建知识库", exact: true }).click();
    const result = await (await accepted).json();
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${result.id}$`));
    return result.id as string;
  }
  async function upload(name: string, buffer: Buffer, mimeType = "text/markdown") {
    const accepted = page.waitForResponse(r => /\/documents$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
    await page.locator('input[type="file"]').first().setInputFiles({ name, mimeType, buffer });
    const result = await (await accepted).json();
    await expect(page.getByRole("article").filter({ hasText: name })).toContainText("已就绪", { timeout: 90_000 });
    return result.document_id as string;
  }
  async function allDocuments(base: string) {
    const rows = [];
    for (let offset = 0;;) {
      const result = await api(`knowledge-bases/${base}/documents?limit=50&offset=${offset}`);
      rows.push(...result.items);
      if (!result.has_more) return rows;
      expect(result.items.length).toBeGreaterThan(0);
      offset += result.items.length;
    }
  }
  async function getDocument(base: string, id: string) { return (await allDocuments(base)).find(d => d.id === id); }
  async function ask(text: string) {
    await page.getByPlaceholder("例如：这个接口有哪些必填字段？").fill(text);
    const response = page.waitForResponse(r => r.url().endsWith("/questions/stream"));
    await page.getByRole("button", { name: "提问", exact: true }).click();
    return response;
  }
  async function historyItem(text: string) {
    const result = await api("questions?limit=100");
    return result.items.find((q: { question: string }) => q.question === text);
  }
  async function historyPanel() {
    const button = page.getByRole("button", { name: "历史记录", exact: true });
    if (await button.isVisible()) { await button.click(); return page.getByRole("dialog", { name: "对话历史" }); }
    return page.locator("aside").filter({ has: page.getByRole("heading", { name: "对话历史", exact: true }) });
  }
  const bases: string[] = [];
  const password = randomBytes(24).toString("hex");
  const baseName = `Agent 主资料库 ${randomUUID().slice(0, 8)}`;
  const pdfBaseName = `Agent PDF 资料库 ${randomUUID().slice(0, 8)}`;
  let mainBase = "", pdfBase = "", markdownId = "", pdfId = "", textQuestionId = "";
  let apiStopped = false;
  const textQuestion = `主资料来源 ${randomUUID()}`;
  let textSource: { source_id: string; document_id: string; content_version_id: string; quote: string };
  try {
    await step("M1-01-register", async () => {
      await page.goto("/register");
      await page.getByLabel("Email", { exact: true }).fill(`m123-${randomUUID()}@example.test`);
      await page.getByLabel("Password", { exact: true }).fill(password);
      await page.getByRole("button", { name: "Create account", exact: true }).click();
      await expect(page.getByRole("heading", { name: "KnowFlow", exact: true })).toBeVisible();
      await expect(page.getByText("这里还没有知识库。")).toBeVisible();
      await page.getByRole("link", { name: "创建知识库", exact: true }).click();
      mainBase = await createBase(baseName); bases.push(mainBase);
      return { registered_via: "browser UI", empty_state: true, base: mainBase };
    });
    await step("M1-02-upload-ready", async () => {
      markdownId = await upload("flow.md", Buffer.from("Agent 验收事实。\n索引状态只有 READY 时才会参与问答。\n版本一原文。\n"));
      const ready = await getDocument(mainBase, markdownId);
      expect(ready.status).toBe("READY"); expect(ready.active_index_version_id).toBeTruthy();
      await page.reload();
      await expect(page.getByRole("article").filter({ hasText: "flow.md" })).toContainText("已就绪");
      return ready;
    });
    await step("M1-03-pdf", async () => {
      pdfBase = await createBase(pdfBaseName); bases.push(pdfBase);
      pdfId = await upload("agent-source.pdf", await readFile(resolve("../../services/ai/tests/fixtures/pdf/chinese-pages.pdf")), "application/pdf");
      await expect(page.getByRole("article").filter({ hasText: "agent-source.pdf" })).toContainText("PDF");
      return { document: pdfId, base: pdfBase };
    });
    await page.goto(`/knowledge-bases/${mainBase}`);
    await step("M1-04-update", async () => {
      const before = await getDocument(mainBase, markdownId);
      const previousAnswer = await api(`knowledge-bases/${mainBase}/questions`, { method: "POST", headers: { "idempotency-key": randomUUID() }, data: { question: "Agent 更新前原文" } });
      const priorSource = previousAnswer.sources[0];
      await page.getByRole("button", { name: "flow.md 操作", exact: true }).click();
      await page.getByRole("menuitem", { name: "更新资料", exact: true }).click();
      const accepted = page.waitForResponse(r => r.url().endsWith(`/documents/${markdownId}/contents`) && r.request().method() === "POST");
      await page.getByLabel("选择更新资料").setInputFiles({ name: "flow.md", mimeType: "text/markdown", buffer: Buffer.from("Agent 验收事实。\n索引状态只有 READY 时才会参与问答。\n版本二更新原文。\n") });
      expect((await accepted).status()).toBe(202);
      const during = await getDocument(mainBase, markdownId);
      expect(during.active_index_version_id).toBeTruthy();
      if (during.source_sha256 === before.source_sha256) expect(during.active_index_version_id).toBe(before.active_index_version_id);
      await expect.poll(async () => (await getDocument(mainBase, markdownId)).source_sha256, { timeout: 90_000 }).not.toBe(before.source_sha256);
      const after = await getDocument(mainBase, markdownId);
      const updatedAnswer = await api(`knowledge-bases/${mainBase}/questions`, { method: "POST", headers: { "idempotency-key": randomUUID() }, data: { question: "Agent 更新后原文" } });
      const updatedSource = updatedAnswer.sources[0];
      expect(updatedSource.content_version_id).not.toBe(priorSource.content_version_id);
      const file = await page.request.get(`/api/v1/documents/${markdownId}/contents/${updatedSource.content_version_id}/file`);
      expect(await file.text()).toContain("版本二更新原文");
      const previous = await page.request.get(`/api/v1/documents/${markdownId}/contents/${priorSource.content_version_id}/file`);
      expect(previous.status()).toBe(200);
      return { before, during, after };
    });
    await step("M1-05-rebuild", async () => {
      const before = await getDocument(mainBase, markdownId);
      await page.getByRole("article").filter({ hasText: "flow.md" }).getByRole("button", { name: "flow.md 操作", exact: true }).click();
      await page.getByRole("menuitem", { name: "重建索引", exact: true }).click();
      await expect.poll(async () => (await getDocument(mainBase, markdownId)).active_index_version_id, { timeout: 90_000 }).not.toBe(before.active_index_version_id);
      const after = await getDocument(mainBase, markdownId);
      expect(after.status).toBe("READY"); expect(after.source_sha256).toBe(before.source_sha256);
      return { before, after };
    });
    await step("M1-06-pagination", async () => {
      const seeded = await page.evaluate(async base => {
        const ids = [];
        for (let i = 0; i < 50; i++) {
          const form = new FormData(); form.append("file", new File([`Agent 分页事实 ${i}。索引状态 READY。`], `page-${String(i).padStart(2, "0")}.md`, { type: "text/markdown" }));
          const response = await fetch(`/api/v1/knowledge-bases/${base}/documents`, { method: "POST", body: form });
          if (!response.ok) throw new Error(`Fixture upload HTTP ${response.status}`);
          ids.push((await response.json()).document_id);
        }
        return ids;
      }, mainBase);
      await page.reload();
      await expect(page.getByRole("article")).toHaveCount(50);
      await page.getByRole("button", { name: "加载更多资料", exact: true }).click();
      await expect(page.getByRole("article")).toHaveCount(51);
      const names = await page.getByRole("article").locator("strong").allTextContents();
      expect(new Set(names).size).toBe(51);
      expect(new Set(names)).toEqual(new Set((await allDocuments(mainBase)).map(d => d.original_name)));
      await expect(page.getByRole("button", { name: "加载更多资料", exact: true })).toHaveCount(0);
      return { seed_method: "same-origin real upload API", seeded_document_ids: seeded, rendered: names };
    });
    await step("M1-07-isolation", async () => {
      const other = await browser.newContext();
      try {
        const second = await other.newPage(); await second.goto(`${baseURL}/register`);
        await second.getByLabel("Email", { exact: true }).fill(`m123-other-${randomUUID()}@example.test`);
        await second.getByLabel("Password", { exact: true }).fill(password);
        await second.getByRole("button", { name: "Create account", exact: true }).click();
        await expect(second.getByText("这里还没有知识库。")).toBeVisible();
        await second.goto(`${baseURL}/knowledge-bases/${mainBase}`);
        await expect(second.getByText("内容不存在或你无权访问。", { exact: true })).toBeVisible();
        const listing = await second.request.get(`${baseURL}/api/v1/knowledge-bases/${mainBase}/documents`);
        const missing = await second.request.get(`${baseURL}/api/v1/knowledge-bases/${randomUUID()}/documents`);
        expect(listing.status()).toBe(200);
        expect(await listing.json()).toEqual(await missing.json());
        expect((await listing.json()).items).toEqual([]);
        expect((await second.request.get(`${baseURL}/api/v1/documents/${markdownId}`)).status()).toBe(404);
        await second.screenshot({ path: resolve(out, "M1-07-isolation-account-b.png") });
      } finally { await other.close(); }
      return { account_b_page_denied: true, document_status: 404, list: "empty and identical to nonexistent base" };
    });
    await page.goto("/conversations");
    await page.getByLabel("切换知识库").selectOption(mainBase);
    await step("M2-01-stream", async () => {
      const response = await ask(textQuestion);
      expect(response.ok()).toBeTruthy();
      const body = await page.evaluate(text => (window as unknown as { agentStreams: Record<string, Promise<string>> }).agentStreams[text], textQuestion);
      const events = body.split(/\r?\n\r?\n/).filter(f => f.includes("data:")).map(frame => ({
        event: frame.match(/event:\s*(\w+)/)?.[1], data: JSON.parse(frame.split(/\r?\n/).filter(l => l.startsWith("data:")).map(l => l.slice(5).trim()).join("\n")),
      }));
      expect(events[0].event).toBe("started"); expect(events.at(-1)?.event).toBe("completed");
      expect(events.some(e => e.event === "delta")).toBeTruthy();
      expect(events.filter(e => ["completed", "error", "cancelled"].includes(e.event ?? ""))).toHaveLength(1);
      events.forEach((e, i) => expect(e.data).toMatchObject({ contract_version: "0.2.0", sequence: i + 1, request_id: events[0].data.request_id }));
      textSource = events.find(e => e.event === "sources")!.data.sources[0];
      await expect(page.getByText("原文依据", { exact: false }).first()).toBeVisible();
      const item = await historyItem(textQuestion); textQuestionId = item.question_id;
      return { events, question_id: textQuestionId };
    });
    await step("M2-02-cancel", async () => {
      const text = `[e2e:slow] agent stop ${randomUUID()}`;
      await ask(text);
      await expect(page.getByText("正在检索并生成回答…")).toBeVisible();
      await page.getByRole("button", { name: "停止生成", exact: true }).click();
      await expect(page.getByText("此问答状态：已取消。可在历史记录中查看。")).toBeVisible();
      await expect.poll(async () => (await historyItem(text))?.status).toBe("CANCELLED");
      const cancelled = await historyItem(text);
      await page.waitForTimeout(4500); // Exceeds the deterministic adapter's completion deadline: detects late success.
      expect((await api(`questions/${cancelled.question_id}`)).status).toBe("CANCELLED");
      await page.goto(`/conversations/${cancelled.question_id}`); await page.reload();
      await expect(page.getByText("此问答状态：已取消。可在历史记录中查看。")).toBeVisible();
      return cancelled;
    });
    await page.goto(`/conversations/${textQuestionId}`);
    await step("M2-03-source", async () => {
      const citation = page.getByRole("button").filter({ hasText: "字符" }).first();
      await citation.click();
      const dialog = page.getByRole("dialog", { name: "原文依据" });
      await expect(dialog.locator("pre")).toBeVisible();
      await expect(page.getByRole("button", { name: "关闭原文", exact: true })).toBeFocused();
      await dialog.screenshot({ path: resolve(out, "M2-03-text-dialog.png") });
      await page.keyboard.press("Escape"); await expect(dialog).toHaveCount(0); await expect(citation).toBeFocused();
      return { source: textSource.source_id, document: textSource.document_id, content_version: textSource.content_version_id };
    });
    await step("M2-04-pdf", async () => {
      await page.getByLabel("切换知识库").selectOption(pdfBase);
      await ask(`Agent PDF 引用 ${randomUUID()}`);
      const citation = page.getByRole("button").filter({ hasText: "agent-source.pdf" }).filter({ hasText: "第" }).first();
      await citation.click();
      const iframe = page.getByRole("dialog", { name: "原文依据" }).locator("iframe");
      await expect(iframe).toHaveAttribute("src", /#page=\d+$/);
      const src = await iframe.getAttribute("src");
      expect((await page.request.get(src!.split("#")[0])).status()).toBe(200);
      await page.screenshot({ path: resolve(out, "M2-04-pdf-dialog.png") });
      await page.keyboard.press("Escape");
      return { iframe_src: src, pdf_document: pdfId };
    });
    await step("M2-05-expired-source", async () => {
      await page.goto(`/conversations/${textQuestionId}`);
      await expect(page.getByRole("button").filter({ hasText: "字符" }).first()).toBeVisible();
      const deletionPage = await page.context().newPage();
      try {
        await deletionPage.goto(`${baseURL}/knowledge-bases/${mainBase}`);
        await expect(deletionPage.getByRole("article")).toHaveCount(50);
        const name = (await getDocument(mainBase, textSource.document_id)).original_name;
        const more = deletionPage.getByRole("button", { name: "加载更多资料", exact: true });
        if (await more.isVisible()) await more.click();
        await deletionPage.getByRole("button", { name: `${name} 操作`, exact: true }).click();
        await deletionPage.getByRole("menuitem", { name: "删除资料", exact: true }).click();
        await deletionPage.getByRole("button", { name: "确认删除", exact: true }).click();
        await expect(deletionPage.getByRole("article").filter({ hasText: name })).toHaveCount(0);
      } finally { await deletionPage.close(); }
      expect((await page.request.get(`/api/v1/sources/${textSource.source_id}`)).status()).toBe(404);
      await page.getByRole("button").filter({ hasText: "字符" }).first().click();
      const dialog = page.getByRole("dialog", { name: "原文依据" });
      await expect(dialog.getByText("来源已删除或版本已失效，请返回历史记录确认。")).toBeVisible();
      await expect(dialog.locator("pre,iframe,blockquote")).toHaveCount(0);
      await page.keyboard.press("Escape");
      await page.reload();
      const history = await api(`questions/${textQuestionId}`);
      expect(history.sources.every((s: { quote: string | null }) => s.quote === null)).toBeTruthy();
      return { source_http: 404, cached_dialog_content_visible: false, historical_quotes: history.sources.map((s: { quote: string | null }) => s.quote) };
    });
    await step("M2-06-history", async () => {
      for (let i = 0; i < 51; i++) await api(`knowledge-bases/${pdfBase}/questions`, { method: "POST", headers: { "idempotency-key": randomUUID() }, data: { question: `Agent 历史分页 ${i}` } });
      await page.goto("/conversations");
      const panel = await historyPanel();
      await expect(panel.locator('a[href^="/conversations/"]')).toHaveCount(50);
      const initial = await panel.locator('a[href^="/conversations/"]').count();
      expect(initial).toBe(50);
      await panel.getByRole("button", { name: "加载更多问答", exact: true }).click();
      await expect.poll(async () => panel.locator('a[href^="/conversations/"]').count()).toBeGreaterThan(50);
      const hrefs = await panel.locator('a[href^="/conversations/"]').evaluateAll(items => items.map(e => e.getAttribute("href")));
      expect(new Set(hrefs).size).toBe(hrefs.length);
      await expect(page.getByRole("button", { name: "退出", exact: true }).last()).toBeVisible();
      return { first_page: initial, loaded: hrefs.length, unique: new Set(hrefs).size, logout_visible: true };
    });
    await step("M2-07-switch-refresh", async () => {
      await page.goto("/conversations"); await page.getByLabel("切换知识库").selectOption(pdfBase);
      const text = `[e2e:slow] Agent 切库 ${randomUUID()}`;
      await ask(text); await expect(page.getByRole("button", { name: "停止生成", exact: true })).toBeVisible();
      await page.getByLabel("切换知识库").selectOption(mainBase);
      await expect(page.getByRole("button", { name: "停止生成", exact: true })).toHaveCount(0);
      await expect(page.locator('section[aria-label="问答"]')).not.toContainText(text);
      await expect.poll(async () => (await historyItem(text))?.status).toBe("CANCELLED");
      await page.getByLabel("切换知识库").selectOption(pdfBase);
      const refreshedText = `[e2e:slow] Agent 刷新 ${randomUUID()}`;
      await ask(refreshedText); await page.reload();
      await expect.poll(async () => (await historyItem(refreshedText))?.status, { timeout: 20_000 }).toMatch(/CANCELLED|SUCCEEDED/);
      const item = await historyItem(refreshedText); const server = await api(`questions/${item.question_id}`);
      await page.goto(`/conversations/${item.question_id}`);
      if (server.status === "CANCELLED") await expect(page.getByText("此问答状态：已取消。可在历史记录中查看。")).toBeVisible();
      else await expect(page.getByText("本地合成验证：", { exact: false }).first()).toBeVisible();
      return { switched: await historyItem(text), reloaded: server.status };
    });
    await step("M2-08-responsive", async () => {
      for (const width of [390, 768, 1440]) {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
        await page.goto("/"); await expect(page.getByRole("heading", { name: "KnowFlow", exact: true })).toBeVisible();
        await page.waitForTimeout(400); // Let the home entrance animation settle before capturing evidence.
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
        await page.screenshot({ path: resolve(out, `M2-08-home-${width}.png`), fullPage: true });
        await page.goto("/conversations");
        const composer = page.getByRole("textbox", { name: "问题", exact: true });
        await expect(composer).toBeVisible(); await composer.scrollIntoViewIfNeeded();
        expect(await composer.evaluate(e => e.getBoundingClientRect().bottom <= innerHeight)).toBeTruthy();
        const history = page.getByRole("button", { name: "历史记录", exact: true });
        if (await history.isVisible()) {
          await history.click(); await expect(page.getByRole("dialog", { name: "对话历史" })).toBeVisible(); await page.keyboard.press("Escape");
          await page.getByRole("button", { name: "资料", exact: true }).click(); await expect(page.getByRole("dialog", { name: "资料" })).toBeVisible(); await page.keyboard.press("Escape");
        }
        await page.screenshot({ path: resolve(out, `M2-08-chat-${width}.png`) });
      }
      return { widths: [390, 768, 1440], no_horizontal_overflow: true, drawers_and_composer: true };
    });
    await step("M2-09-keyboard", async () => {
      async function tabTo(target: Locator) {
        await expect(target).toBeVisible();
        for (let i = 0; i < 100 && !(await target.evaluate(e => e === document.activeElement)); i++) await page.keyboard.press("Tab");
        await expect(target).toBeFocused();
      }
      await page.setViewportSize({ width: 1440, height: 900 }); await page.goto("/");
      await tabTo(page.getByRole("link", { name: "跳到主要内容" }));
      await page.keyboard.press("Enter"); await expect(page.locator("#main-content")).toBeFocused();
      await page.goto("/knowledge-bases"); const search = page.getByRole("textbox", { name: "搜索知识库" });
      await tabTo(search); await expect(search.locator('xpath=ancestor::*[@data-composite-field][1]')).toHaveCSS("outline-width", "2px");
      await page.goto("/conversations"); await page.getByLabel("切换知识库").selectOption(pdfBase);
      const input = page.getByRole("textbox", { name: "问题", exact: true }); await tabTo(input); await expect(input.locator('xpath=ancestor::*[@data-composite-field][1]')).toHaveCSS("outline-width", "2px");
      await page.keyboard.type(`Agent keyboard ${randomUUID()}`); await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: "提问", exact: true })).toBeFocused(); await page.keyboard.press("Enter");
      const citation = page.getByRole("button").filter({ hasText: "agent-source.pdf" }).filter({ hasText: "第" }).first();
      await expect(citation).toBeVisible();
      // Reach the citation through Tab (not programmatic focus), then open and close it using keys.
      for (let i = 0; i < 80 && !(await citation.evaluate(e => e === document.activeElement)); i++) await page.keyboard.press("Tab");
      await expect(citation).toBeFocused(); await page.keyboard.press("Enter");
      await expect(page.getByRole("button", { name: "关闭原文", exact: true })).toBeFocused();
      await page.keyboard.press("Escape"); await expect(citation).toBeFocused();
      return { keyboard_submit: true, keyboard_source_and_return: true, focus_ring: true };
    });
    await step("M3-01-mode", async () => {
      await expect(page.getByText("本地合成验证", { exact: false }).first()).toBeVisible();
      expect((await page.request.get("/api/mode")).ok()).toBeTruthy();
      const mode = await (await page.request.get("/api/mode")).json(); expect(mode.mode).toBe("synthetic");
      return mode;
    });
    await step("M3-02-settings", async () => {
      await page.goto("/settings");
      await expect(page.getByText("合成模型（本地工程验证）", { exact: true })).toBeVisible();
      await expect(page.getByText("单轮问答 · 每次提问独立检索", { exact: true })).toBeVisible();
      await expect(page.getByText("文档片段与问题仅发送给当前配置的模型服务", { exact: true })).toBeVisible();
      return { mode: "synthetic", single_turn: true, outbound_scope_disclosed: true };
    });
    await step("M3-03-service-error", async () => {
      if (!project || !/^knowflow-(local|e2e-[a-f0-9]+)$/.test(project)) throw new Error("A scoped KNOWFLOW_ACCEPTANCE_PROJECT is required for the real API outage test");
      try {
        execFileSync("docker", ["stop", "--time", "1", `${project}-api-1`], { stdio: "pipe" }); apiStopped = true;
        await page.reload();
        await expect(page.getByText("服务暂时不可用，请稍后重试。", { exact: true })).toBeVisible();
        await expect(page.getByRole("button", { name: "重试连接", exact: true })).toBeVisible();
        expect(await page.locator("body").innerText()).not.toMatch(/jdbc:|postgresql:|Traceback|password=|Exception at/);
        await page.screenshot({ path: resolve(out, "M3-03-api-stopped.png") });
      } finally {
        execFileSync("docker", ["start", `${project}-api-1`], { stdio: "pipe" }); apiStopped = false;
      }
      await expect.poll(async () => (await page.request.get("/api/v1/me")).status(), { timeout: 90_000 }).toBe(200);
      await page.getByRole("button", { name: "重试连接", exact: true }).click();
      await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
      return { actual_api_container_stop: true, retry_restored_session: true, internal_error_redacted: true };
    });
    await step("M3-04-network", async () => {
      const external = requests.filter(r => new URL(r.url).origin !== new URL(baseURL!).origin);
      expect(external).toEqual([]);
      expect(requests.some(r => r.method === "POST" && r.url.endsWith("/questions/stream"))).toBeTruthy();
      expect(requests.some(r => r.method === "POST" && r.url.endsWith("/documents"))).toBeTruthy();
      await writeFile(resolve(out, "network-metadata.json"), JSON.stringify({ note: "No headers, bodies, query strings, cookies or credentials persisted", requests }, null, 2));
      return { requests: requests.length, external_requests: external.length, metadata_only: true };
    });
    expect(manifest.cases).toHaveLength(20);
    manifest.status = "PASS";
    if (process.env.KNOWFLOW_ACCEPTANCE_MODEL) manifest.signature = `agent:${model}; executed ${new Date().toISOString()}; M1 7/7, M2 9/9, M3 4/4; synthetic business model only`;
  } finally {
    if (apiStopped && project) execFileSync("docker", ["start", `${project}-api-1`], { stdio: "pipe" });
    const cleanup = [];
    for (const base of bases) {
      const response = await page.request.delete(`/api/v1/knowledge-bases/${base}`, { headers: { Origin: baseURL! } });
      cleanup.push({ base, status: response.status() });
    }
    manifest.cleanup = cleanup.every(r => r.status === 204) ? "PASS" : "FAIL";
    if (manifest.cleanup !== "PASS") { manifest.status = "INCOMPLETE"; manifest.signature = ""; }
    manifest.finished_at = new Date().toISOString();
    await writeFile(resolve(out, "cleanup.json"), JSON.stringify(cleanup, null, 2));
    await save();
    await test.info().attach("agent-module-manifest", { path: resolve(out, "modules-manifest.json"), contentType: "application/json" });
    expect(manifest.cleanup).toBe("PASS");
  }
});
