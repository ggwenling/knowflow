import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { POST, GET } from "./[...path]/route";

const context = (path: string[]) => ({ params: Promise.resolve({ path }) });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

describe("same-origin API proxy", () => {
  it("keeps the login token in an HttpOnly cookie and strips it from JSON", async () => {
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
});
