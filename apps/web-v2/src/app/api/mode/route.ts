export const dynamic = "force-dynamic";

export async function GET() {
  const mode = process.env.KNOWFLOW_WEB_MODEL_MODE;
  return Response.json({ mode: mode === "synthetic" || mode === "external" ? mode : "unknown" }, {
    headers: { "Cache-Control": "no-store" },
  });
}
