"use client";

import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Nav } from "@/components/nav";
import { UploadZone } from "@/components/ingest/upload-zone";
import { JobList } from "@/components/ingest/job-list";
import { CorpusList } from "@/components/ingest/corpus-list";
import { useIngest } from "@/lib/use-ingest";

export default function IngestPage() {
  const { jobs, upload, clear } = useIngest();
  const isUploading = jobs.some((j) => j.status === "uploading");
  // Bumps every time another job transitions to "done" — CorpusList re-fetches
  // whenever this changes, so successful uploads automatically refresh the list.
  const doneCount = jobs.filter((j) => j.status === "done").length;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-4">
        <div className="flex items-center gap-6">
          <div>
            <h1 className="text-base font-semibold text-[var(--color-text)]">danny_rag</h1>
            <p className="text-xs text-[var(--color-text-dim)]">document ingestion</p>
          </div>
          <Nav />
        </div>
        <Button
          type="button"
          variant="ghost"
          onClick={clear}
          disabled={jobs.length === 0}
          aria-label="Clear job list"
        >
          <Trash2 size={14} />
        </Button>
      </header>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl p-6">
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-[var(--color-text)]">Ingest documents</h2>
            <p className="mt-1 text-sm text-[var(--color-text-dim)]">
              Files are chunked, embedded, and upserted into Qdrant. Re-uploading the same
              document is idempotent (MTC-02) — chunks with unchanged content hashes are skipped.
            </p>
          </div>

          <UploadZone onFiles={upload} disabled={isUploading} />

          <JobList jobs={jobs} />

          <CorpusList refreshKey={doneCount} />

          <div className="mt-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-xs text-[var(--color-text-dim)]">
            <p className="font-medium text-[var(--color-text)]">Limits (BRD-01 §3.7 MTC-09)</p>
            <ul className="mt-2 space-y-1">
              <li>• Max 25 MB per file</li>
              <li>• Allowed types: PDF, Markdown, HTML, plain text</li>
              <li>• 60 s ingestion timeout per file</li>
              <li>• At most 2 concurrent ingestions across all clients</li>
              <li>• Rate limit: 5 uploads / minute / IP</li>
            </ul>
          </div>
        </div>
      </main>
    </div>
  );
}
