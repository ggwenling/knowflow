import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const cookieName = "knowflow_session";
const forwardedHeaders = [
  "accept",
  "content-type",
  "range",
  "idempotency-key",
  "x-request-id",
] as const;
const responseHeaders = [
  "accept-ranges",
  "content-disposition",
  "content-range",
  "content-type",
  "retry-after",
  "x-request-id",
] as const;
type RouteContext = { params: Promise<{ path: string[] }> };

function failure(status: number, code: string) {
  return Response.json({ code, message: code }, { status, headers: { "Cache-Control": "no-store" } });
}

function sameOriginRequest(request: NextRequest) {
  const origin = request.headers.get("origin");
  const host = (request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? request.nextUrl.host).split(",", 1)[0].trim();
  const protocol = (request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol.slice(0, -1)).split(",", 1)[0].trim();
  return Boolean(origin && host && origin === `${protocol}://${host}`);
}

function expireSession(response: Response) {
  response.headers.append("Set-Cookie", `${cookieName}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${process.env.NODE_ENV === "production" ? "; Secure" : ""}`);
}

async function proxy(request: NextRequest, { params }: RouteContext) {
  const path = (await params).path;
  const pathname = `/api/v1/${path.map(encodeURIComponent).join("/")}`;
  const authPath = path.join("/") === "auth/login" || path.join("/") === "auth/register";
  const isLogout = path.join("/") === "auth/logout";
  if (request.method !== "GET" && !sameOriginRequest(request)) {
    return failure(403, "CROSS_ORIGIN_REQUEST");
  }
  const declaredLength = Number(request.headers.get("content-length") ?? 0);
  if (declaredLength > 9 * 1024 * 1024) return failure(413, "REQUEST_TOO_LARGE");

  const token = request.cookies.get(cookieName)?.value;
  if (!authPath && !token) return failure(401, "UNAUTHENTICATED");

  const apiBase = process.env.KNOWFLOW_API_BASE_URL;
  if (!apiBase) return failure(503, "API_NOT_CONFIGURED");

  const headers = new Headers();
  for (const name of forwardedHeaders) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (token && !authPath) headers.set("authorization", `Bearer ${token}`);

  try {
    const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
    if (body && body.byteLength > 9 * 1024 * 1024) return failure(413, "REQUEST_TOO_LARGE");
    const upstream = await fetch(`${apiBase.replace(/\/$/, "")}${pathname}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body,
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(40_000)]),
      cache: "no-store",
    });

    if (upstream.status === 401) {
      const response = new Response(upstream.body, { status: upstream.status });
      expireSession(response);
      response.headers.set("Cache-Control", "no-store");
      return response;
    }

    const outgoing = new Headers({ "Cache-Control": "no-store" });
    for (const name of responseHeaders) {
      const value = upstream.headers.get(name);
      if (value) outgoing.set(name, value);
    }
    if (upstream.headers.get("content-type")?.includes("text/event-stream")) {
      outgoing.set("Cache-Control", "no-cache, no-transform");
      outgoing.set("X-Accel-Buffering", "no");
    }

    if (authPath && upstream.ok) {
      const payload = await upstream.json() as { access_token?: string; expires_at?: string };
      const expires = Date.parse(payload.expires_at ?? "");
      if (!payload.access_token || !Number.isFinite(expires) || expires <= Date.now()) {
        return failure(502, "INVALID_AUTH_RESPONSE");
      }
      const maxAge = Math.floor((expires - Date.now()) / 1000);
      outgoing.append("Set-Cookie", `${cookieName}=${encodeURIComponent(payload.access_token)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}${process.env.NODE_ENV === "production" ? "; Secure" : ""}`);
      delete payload.access_token;
      return Response.json(payload, { status: upstream.status, headers: outgoing });
    }

    if (isLogout && upstream.ok) {
      outgoing.append("Set-Cookie", `${cookieName}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${process.env.NODE_ENV === "production" ? "; Secure" : ""}`);
    }
    return new Response(upstream.body, { status: upstream.status, headers: outgoing });
  } catch {
    return failure(502, "API_UNAVAILABLE");
  }
}

export { proxy as GET, proxy as POST, proxy as DELETE };
