import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { POST, GET } from "./[...path]/route";

const context = (path: string[]) => ({ params: Promise.resolve({ path }) });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

describe("same-origin API proxy", () => {
  it("keeps the login token in an HttpOnly cookie and strips it from JSON", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("KNOWFLOW_API_BASE_URL", "http://java:8080");
    const token = "private-login-token";
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({
      contract_version: "draft", user_id: "u-1", email: "a@example.test",
      access_token: token, expires_at: new Date(Date.now() + 3_600_000).toISOString(),
    })));
    const request = new NextRequest("http://web.test/api/v1/auth/login", {
      method: "POST", headers: { origin: "http://web.test", "content-type": "application/json" }, body: "{}",
    });

    const response = await POST(request, context(["auth", "login"]));
    const body = await response.text();

    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain("HttpOnly");
    expect(response.headers.get("set-cookie")).toContain("SameSite=Lax");
    expect(response.headers.get("set-cookie")).toContain("Secure");
    expect(response.headers.get("set-cookie")).toContain(encodeURIComponent(token));
    expect(body).not.toContain(token);
  });

  it("rejects cross-origin writes before reaching Java", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const request = new NextRequest("http://web.test/api/v1/knowledge-bases", {
      method: "POST", headers: { origin: "http://elsewhere.test", cookie: "knowflow_session=token" }, body: "{}",
    });

    const response = await POST(request, context(["knowledge-bases"]));

    expect(response.status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("accepts same-origin writes behind a host port proxy", async () => {
    vi.stubEnv("KNOWFLOW_API_BASE_URL", "http://java:8080");
    const fetch = vi.fn(async () => Response.json({ id: "kb-1" }));
    vi.stubGlobal("fetch", fetch);
    const request = new NextRequest("http://web:3000/api/v1/knowledge-bases", {
      method: "POST",
      headers: {
        origin: "http://127.0.0.1:3577",
        host: "web:3000",
        "x-forwarded-host": "127.0.0.1:3577",
        "x-forwarded-proto": "http",
        cookie: "knowflow_session=secret",
      },
      body: "{}",
    });

    const response = await POST(request, context(["knowledge-bases"]));

    expect(response.status).toBe(200);
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("forwards file ranges with the server-held bearer token", async () => {
    vi.stubEnv("KNOWFLOW_API_BASE_URL", "http://java:8080/");
    const fetch = vi.fn(async (_url: string, init: RequestInit) => {
      expect(new Headers(init.headers).get("authorization")).toBe("Bearer secret");
      expect(new Headers(init.headers).get("range")).toBe("bytes=0-7");
      return new Response("pdf-data", { status: 206, headers: { "content-range": "bytes 0-7/8", "content-type": "application/pdf" } });
    });
    vi.stubGlobal("fetch", fetch);
    const request = new NextRequest("http://web.test/api/v1/documents/d/contents/v/file", {
      headers: { cookie: "knowflow_session=secret", range: "bytes=0-7" },
    });

    const response = await GET(request, context(["documents", "d", "contents", "v", "file"]));

    expect(response.status).toBe(206);
    expect(response.headers.get("content-range")).toBe("bytes 0-7/8");
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it.each(["success", "upstream failure", "disconnected", "unconfigured"])("clears the local logout cookie when %s", async (outcome) => {
    vi.stubEnv("KNOWFLOW_API_BASE_URL", outcome === "unconfigured" ? "" : "http://java:8080");
    vi.stubEnv("NODE_ENV", "production");
    vi.stubGlobal("fetch", vi.fn(async () => {
      if (outcome === "disconnected") throw new TypeError("network disconnected");
      return new Response(null, { status: outcome === "success" ? 204 : 503 });
    }));
    const response = await POST(new NextRequest("http://web.test/api/v1/auth/logout", {
      method: "POST", headers: { origin: "http://web.test", cookie: "knowflow_session=secret" }, body: "{}",
    }), context(["auth", "logout"]));

    expect(response.status).toBe(outcome === "success" ? 204 : outcome === "disconnected" ? 502 : 503);
    expect(response.headers.get("set-cookie")).toBe("knowflow_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0; Secure");
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("does not clear the cookie for rejected cross-origin logout", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const response = await POST(new NextRequest("http://web.test/api/v1/auth/logout", {
      method: "POST", headers: { origin: "http://elsewhere.test", cookie: "knowflow_session=secret" }, body: "{}",
    }), context(["auth", "logout"]));

    expect(response.status).toBe(403);
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("does not turn a GET request into logout", async () => {
    vi.stubEnv("KNOWFLOW_API_BASE_URL", "http://java:8080");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 405 })));
    const response = await GET(new NextRequest("http://web.test/api/v1/auth/logout", {
      headers: { cookie: "knowflow_session=secret" },
    }), context(["auth", "logout"]));

    expect(response.status).toBe(405);
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("expires rejected sessions while preserving the upstream error response", async () => {
    vi.stubEnv("KNOWFLOW_API_BASE_URL", "http://java:8080");
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ code: "UNAUTHENTICATED" }, {
      status: 401, headers: { "x-request-id": "request-401" },
    })));
    const response = await GET(new NextRequest("http://web.test/api/v1/me", {
      headers: { cookie: "knowflow_session=expired" },
    }), context(["me"]));

    expect(response.status).toBe(401);
    expect(response.headers.get("set-cookie")).toContain("Max-Age=0");
    expect(response.headers.get("content-type")).toContain("application/json");
    expect(response.headers.get("x-request-id")).toBe("request-401");
    expect(await response.json()).toEqual({ code: "UNAUTHENTICATED" });
  });

  it.each(["null", "invalid JSON", "missing token", "non-string token", "invalid token", "invalid expiry", "expired"])("rejects an auth response with %s", async (invalid) => {
    vi.stubEnv("KNOWFLOW_API_BASE_URL", "http://java:8080");
    const valid = { access_token: "valid-token", expires_at: new Date(Date.now() + 3_600_000).toISOString() };
    const payload = invalid === "null" ? null
      : invalid === "missing token" ? { ...valid, access_token: undefined }
        : invalid === "non-string token" ? { ...valid, access_token: { private: true } }
          : invalid === "invalid token" ? { ...valid, access_token: "token with spaces" }
            : invalid === "invalid expiry" ? { ...valid, expires_at: "not-a-date" }
              : invalid === "expired" ? { ...valid, expires_at: new Date(Date.now() - 1_000).toISOString() } : valid;
    vi.stubGlobal("fetch", vi.fn(async () => invalid === "invalid JSON" ? new Response("not-json") : Response.json(payload)));
    const response = await POST(new NextRequest("http://web.test/api/v1/auth/login", {
      method: "POST", headers: { origin: "http://web.test" }, body: "{}",
    }), context(["auth", "login"]));

    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ code: "INVALID_AUTH_RESPONSE", message: "INVALID_AUTH_RESPONSE" });
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it.each(["declared", "actual"])("rejects oversized %s request bodies before contacting Java", async (kind) => {
    vi.stubEnv("KNOWFLOW_API_BASE_URL", "http://java:8080");
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const headers = new Headers({ origin: "http://web.test", cookie: "knowflow_session=secret" });
    if (kind === "declared") headers.set("content-length", String(9 * 1024 * 1024 + 1));
    const request = new NextRequest("http://web.test/api/v1/knowledge-bases/kb/documents", {
      method: "POST", headers, body: kind === "actual" ? "x".repeat(9 * 1024 * 1024 + 1) : "small",
    });
    const response = await POST(request, context(["knowledge-bases", "kb", "documents"]));

    expect(response.status).toBe(413);
    expect((await response.json()).code).toBe("REQUEST_TOO_LARGE");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("preserves unsatisfiable range status and size metadata", async () => {
    vi.stubEnv("KNOWFLOW_API_BASE_URL", "http://java:8080");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, {
      status: 416, headers: { "content-range": "bytes */8", "accept-ranges": "bytes" },
    })));
    const response = await GET(new NextRequest("http://web.test/api/v1/documents/d/contents/v/file", {
      headers: { cookie: "knowflow_session=secret", range: "bytes=99-100" },
    }), context(["documents", "d", "contents", "v", "file"]));

    expect(response.status).toBe(416);
    expect(response.headers.get("content-range")).toBe("bytes */8");
    expect(response.headers.get("accept-ranges")).toBe("bytes");
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("streams events without buffering and propagates browser cancellation", async () => {
    vi.stubEnv("KNOWFLOW_API_BASE_URL", "http://java:8080");
    let stream!: ReadableStreamDefaultController<Uint8Array>;
    let upstreamSignal!: AbortSignal;
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init: RequestInit) => {
      upstreamSignal = init.signal!;
      return new Response(new ReadableStream<Uint8Array>({ start(controller) { stream = controller; } }), {
        headers: { "content-type": "text/event-stream", "x-request-id": "stream-request" },
      });
    }));
    const browser = new AbortController();
    const response = await POST(new NextRequest("http://web.test/api/v1/knowledge-bases/kb/questions/stream", {
      method: "POST", signal: browser.signal,
      headers: { origin: "http://web.test", cookie: "knowflow_session=secret" }, body: '{"question":"hello"}',
    }), context(["knowledge-bases", "kb", "questions", "stream"]));
    expect(response.headers.get("content-type")).toBe("text/event-stream");
    expect(response.headers.get("cache-control")).toBe("no-cache, no-transform");
    expect(response.headers.get("x-accel-buffering")).toBe("no");
    const reader = response.body!.getReader();
    stream.enqueue(new TextEncoder().encode("event: started\n\n"));
    expect(new TextDecoder().decode((await reader.read()).value)).toBe("event: started\n\n");
    browser.abort();
    expect(upstreamSignal.aborted).toBe(true);
    stream.close();
    reader.releaseLock();
  });
});
