import type { Page } from "@playwright/test";

type Fiber = { child: Fiber | null; sibling: Fiber | null; return: Fiber | null; type: unknown; stateNode: unknown; flags: number };
type Probe = { active: boolean; counts: Record<string, number> };
type ProbeWindow = Window & { __renderProbe: Probe; __REACT_DEVTOOLS_GLOBAL_HOOK__: unknown };

/** Observe actual production React commits without changing the application bundle. */
export async function installRenderProbe(page: Page) {
  await page.addInitScript(() => {
    const target = window as unknown as ProbeWindow;
    target.__renderProbe = { active: false, counts: {} };
    let id = 0;
    const previous = new Map<string, Fiber>();
    target.__REACT_DEVTOOLS_GLOBAL_HOOK__ = { supportsFiber: true, inject: () => ++id, onCommitFiberUnmount() {}, onPostCommitFiberRoot() {}, onCommitFiberRoot(_id: number, root: { current: Fiber }) {
      const nodes: Fiber[] = [];
      function walk(fiber: Fiber | null) { if (!fiber) return; nodes.push(fiber); walk(fiber.child); walk(fiber.sibling); }
      walk(root.current);
      const selectors = { shell: "main#main-content", home: "#home-title", composer: "#desk-question", history: 'input[name="history"]', documents: '[class*="docsHead"]', answer: '[class*="answerBody"]' };
      for (const [label, selector] of Object.entries(selectors)) {
        const element = document.querySelector(selector);
        if (!element) continue;
        let fiber: Fiber | null | undefined = nodes.find((item) => item.stateNode === element);
        while (fiber && typeof fiber.type !== "function") fiber = fiber.return;
        // Bailouts can reuse a fiber carrying flags from its last render.
        if (fiber && target.__renderProbe.active && fiber !== previous.get(label) && fiber.flags & 1) target.__renderProbe.counts[label] = (target.__renderProbe.counts[label] ?? 0) + 1;
        if (fiber) previous.set(label, fiber);
      }
    } };
  });
}

export async function beginRenderProbe(page: Page) {
  await page.evaluate(async () => { await document.fonts.ready; await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame); });
  await page.evaluate(() => { (window as unknown as ProbeWindow).__renderProbe = { active: true, counts: {} }; });
}
export async function endRenderProbe(page: Page) {
  return page.evaluate(() => { const probe = (window as unknown as ProbeWindow).__renderProbe; probe.active = false; return probe.counts; });
}
