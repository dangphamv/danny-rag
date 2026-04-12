import { NextRequest } from "next/server";

// MTC-07: server-side proxy for GET /ingest/list. The API key never crosses
// to the browser; this handler injects it as X-API-Key when forwarding to
// FastAPI.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: NextRequest) {
  const apiUrl = process.env.API_URL ?? "http://localhost:8000";
  const apiKey = process.env.API_KEY;

  if (!apiKey) {
    return Response.json(
      { error: "API_KEY not configured on the server" },
      { status: 500 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiUrl}/ingest/list`, {
      method: "GET",
      headers: { "X-API-Key": apiKey },
    });
  } catch (err) {
    return Response.json(
      { error: "upstream unreachable", detail: String(err) },
      { status: 502 },
    );
  }

  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
