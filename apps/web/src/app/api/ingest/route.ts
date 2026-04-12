import { NextRequest } from "next/server";

// MTC-07 mirror of /api/chat: API key never leaves the server.
// MTC-09 cap is enforced server-side by FastAPI; we mirror the limit here so
// the browser sees a clean 413 instead of getting cut off mid-upload.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_BYTES = 25 * 1024 * 1024; // matches Settings.upload_max_bytes (MTC-09)

export async function POST(req: NextRequest) {
  const apiUrl = process.env.API_URL ?? "http://localhost:8000";
  const apiKey = process.env.API_KEY;

  if (!apiKey) {
    return Response.json(
      { error: "API_KEY not configured on the server" },
      { status: 500 },
    );
  }

  // Pre-flight size check from Content-Length so we abort huge uploads before
  // streaming the body. Real enforcement still happens in FastAPI.
  const contentLength = Number(req.headers.get("content-length") ?? "0");
  if (contentLength > MAX_BYTES * 1.05) {
    return Response.json(
      { error: `file exceeds ${MAX_BYTES} bytes` },
      { status: 413 },
    );
  }

  // Forward the multipart boundary from the browser. Without this, FastAPI
  // sees raw bytes with no boundary marker and can't parse the `file` field.
  const upstreamHeaders: Record<string, string> = { "X-API-Key": apiKey };
  const incomingContentType = req.headers.get("content-type");
  if (incomingContentType) {
    upstreamHeaders["Content-Type"] = incomingContentType;
  }
  const incomingContentLength = req.headers.get("content-length");
  if (incomingContentLength) {
    upstreamHeaders["Content-Length"] = incomingContentLength;
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiUrl}/ingest`, {
      method: "POST",
      headers: upstreamHeaders,
      body: req.body,
      // @ts-expect-error duplex is required by undici when streaming a body
      duplex: "half",
    });
  } catch (err) {
    return Response.json(
      { error: "upstream unreachable", detail: String(err) },
      { status: 502 },
    );
  }

  // Pass through the FastAPI response (status + body) verbatim.
  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
