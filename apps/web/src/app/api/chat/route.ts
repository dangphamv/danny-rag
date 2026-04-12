import { NextRequest } from "next/server";

// MTC-07: the API key is server-side only and never crosses to the browser.
// This route handler is a thin SSE proxy: it forwards the user question to the
// FastAPI backend with the X-API-Key header, then pipes the SSE stream back.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const apiUrl = process.env.API_URL ?? "http://localhost:8000";
  const apiKey = process.env.API_KEY;

  if (!apiKey) {
    return new Response(
      JSON.stringify({ error: "API_KEY not configured on the server" }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON body" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const upstream = await fetch(`${apiUrl}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify(body),
  });

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    return new Response(
      JSON.stringify({ error: "upstream error", status: upstream.status, body: text }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
