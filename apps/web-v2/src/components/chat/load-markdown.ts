let pending: Promise<typeof import("./markdown-answer")> | undefined;

export function loadMarkdown() {
  pending ??= import("./markdown-answer").catch((error: unknown) => { pending = undefined; throw error; });
  return pending;
}

export function preloadMarkdown() { void loadMarkdown().catch(() => { /* Rendering can retry a failed prefetch. */ }); }
