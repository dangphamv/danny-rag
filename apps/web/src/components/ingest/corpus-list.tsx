"use client";

import { useCallback, useEffect, useState } from "react";
import { FileText, RefreshCcw, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";

type CorpusDocument = {
  doc_id: string;
  title: string;
  source_uri: string;
  chunk_count: number;
  embedding_model: string;
  first_ingested_at: string;
  last_ingested_at: string;
};

type CorpusListResponse = {
  collection: string;
  total_chunks: number;
  documents: CorpusDocument[];
};

type Props = {
  // Bumped by the parent whenever a new upload completes, so we re-fetch.
  refreshKey: number;
};

export function CorpusList({ refreshKey }: Props) {
  const [data, setData] = useState<CorpusListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fetchList = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await fetch("/api/ingest/list");
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `HTTP ${resp.status}`);
      }
      setData((await resp.json()) as CorpusListResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchList();
  }, [fetchList, refreshKey]);

  return (
    <div className="mt-8">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-[var(--color-text-dim)]">
            Currently in corpus
          </h3>
          {data && (
            <p className="mt-1 text-xs text-[var(--color-text-dim)]">
              {data.documents.length}{" "}
              {data.documents.length === 1 ? "document" : "documents"} ·{" "}
              {data.total_chunks} {data.total_chunks === 1 ? "chunk" : "chunks"} ·{" "}
              <span className="font-mono">{data.collection}</span>
            </p>
          )}
        </div>
        <Button
          type="button"
          variant="ghost"
          onClick={fetchList}
          disabled={isLoading}
          aria-label="Refresh corpus list"
        >
          <RefreshCcw size={13} className={isLoading ? "animate-spin" : ""} />
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-900 bg-red-950/50 p-3 text-xs text-red-300">
          Failed to load corpus: {error}
        </div>
      )}

      {!error && data && data.documents.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center text-xs text-[var(--color-text-dim)]">
          <Upload size={20} />
          <span>No documents yet — drop a file above to get started.</span>
        </div>
      )}

      {!error && data && data.documents.length > 0 && (
        <ul className="divide-y divide-[var(--color-border)] overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
          {data.documents.map((doc) => {
            const fromUpload = doc.source_uri.startsWith("upload://");
            const date = doc.last_ingested_at
              ? new Date(doc.last_ingested_at).toLocaleString()
              : "—";
            return (
              <li key={doc.doc_id} className="flex items-start gap-3 p-4">
                <FileText
                  size={16}
                  className="mt-0.5 shrink-0 text-[var(--color-text-dim)]"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-sm font-medium text-[var(--color-text)]">
                      {doc.title || doc.doc_id}
                    </span>
                    <span className="shrink-0 text-[10px] tabular-nums text-[var(--color-text-dim)]">
                      {doc.chunk_count}{" "}
                      {doc.chunk_count === 1 ? "chunk" : "chunks"}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-[var(--color-text-dim)]">
                    <span className="font-mono">doc_id={doc.doc_id}</span>
                    <span
                      className={
                        fromUpload
                          ? "text-[var(--color-accent)]"
                          : ""
                      }
                    >
                      {fromUpload ? "uploaded" : "CLI"}
                    </span>
                    <span>{doc.embedding_model}</span>
                    <span>{date}</span>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
