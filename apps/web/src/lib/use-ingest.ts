"use client";

import { useCallback, useState } from "react";

export type IngestResult = {
  filename: string;
  doc_id: string;
  total_chunks: number;
  upserted: number;
  skipped_unchanged: number;
};

export type IngestJob = {
  id: string;
  filename: string;
  status: "uploading" | "done" | "error";
  result?: IngestResult;
  error?: string;
};

const MAX_BYTES = 25 * 1024 * 1024; // mirrors backend MTC-09
const ALLOWED_MIMES = new Set([
  "application/pdf",
  "text/markdown",
  "text/html",
  "text/plain",
]);
const ALLOWED_EXTENSIONS = new Set([".pdf", ".md", ".markdown", ".html", ".htm", ".txt"]);

function newId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function isAccepted(file: File): { ok: true } | { ok: false; reason: string } {
  if (file.size > MAX_BYTES) {
    return { ok: false, reason: `File exceeds ${MAX_BYTES.toLocaleString()} bytes` };
  }
  if (file.type && ALLOWED_MIMES.has(file.type)) return { ok: true };
  const dot = file.name.lastIndexOf(".");
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (ext && ALLOWED_EXTENSIONS.has(ext)) return { ok: true };
  return {
    ok: false,
    reason: `Unsupported file type (${file.type || "unknown"}). Allowed: PDF, MD, HTML, TXT.`,
  };
}

export function useIngest() {
  const [jobs, setJobs] = useState<IngestJob[]>([]);

  const upload = useCallback(async (files: File[]) => {
    const newJobs: IngestJob[] = [];
    for (const file of files) {
      const verdict = isAccepted(file);
      if (!verdict.ok) {
        newJobs.push({
          id: newId(),
          filename: file.name,
          status: "error",
          error: verdict.reason,
        });
        continue;
      }
      newJobs.push({ id: newId(), filename: file.name, status: "uploading" });
    }
    setJobs((prev) => [...newJobs, ...prev]);

    for (const job of newJobs) {
      if (job.status !== "uploading") continue;
      const file = files.find((f) => f.name === job.filename);
      if (!file) continue;

      try {
        const formData = new FormData();
        formData.append("file", file);
        const resp = await fetch("/api/ingest", { method: "POST", body: formData });
        if (!resp.ok) {
          const errBody = await resp.json().catch(() => ({}));
          throw new Error(errBody.detail || errBody.error || `HTTP ${resp.status}`);
        }
        const result = (await resp.json()) as IngestResult;
        setJobs((prev) =>
          prev.map((j) => (j.id === job.id ? { ...j, status: "done", result } : j)),
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setJobs((prev) =>
          prev.map((j) =>
            j.id === job.id ? { ...j, status: "error", error: message } : j,
          ),
        );
      }
    }
  }, []);

  const clear = useCallback(() => setJobs([]), []);

  return { jobs, upload, clear };
}
