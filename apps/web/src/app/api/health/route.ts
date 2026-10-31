export async function GET() {
  return Response.json({
    status: "ok",
    service: "knowflow-web",
    mock: process.env.NEXT_PUBLIC_USE_MOCK === "true",
  });
}
