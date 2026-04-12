"use client";

import { CheckCircle2, FileText, Loader2, XCircle } from "lucide-react";
import type { IngestJob } from "@/lib/use-ingest";

type Props = {
  jobs: IngestJob[];
};

export function JobList({ jobs }: Props) {
  if (jobs.length === 0) {
    return null;
  }

  return (
    <ul className="mt-6 divide-y divide-[var(--color-border)] overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
      {jobs.map((job) => (
        <li key={job.id} className="flex items-center gap-3 p-4">
          <FileText size={16} className="shrink-0 text-[var(--color-text-dim)]" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-[var(--color-text)]">
              {job.filename}
            </div>
            {job.status === "uploading" && (
              <div className="mt-1 flex items-center gap-1.5 text-xs text-[var(--color-text-dim)]">
                <Loader2 size={11} className="animate-spin" />
                Uploading and ingesting…
              </div>
            )}
            {job.status === "done" && job.result && (
              <div className="mt-1 text-xs text-[var(--color-text-dim)]">
                doc_id={job.result.doc_id} · {job.result.total_chunks} chunks ·{" "}
                <span className="text-green-300">{job.result.upserted} upserted</span>
                {job.result.skipped_unchanged > 0 && (
                  <>
                    {" · "}
                    <span className="text-[var(--color-text-dim)]">
                      {job.result.skipped_unchanged} unchanged (idempotent)
                    </span>
                  </>
                )}
              </div>
            )}
            {job.status === "error" && (
              <div className="mt-1 text-xs text-red-300">{job.error}</div>
            )}
          </div>
          {job.status === "done" && (
            <CheckCircle2 size={16} className="shrink-0 text-green-300" />
          )}
          {job.status === "error" && (
            <XCircle size={16} className="shrink-0 text-red-400" />
          )}
        </li>
      ))}
    </ul>
  );
}
