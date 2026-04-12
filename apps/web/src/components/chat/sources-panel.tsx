"use client";

import { FileText } from "lucide-react";
import type { ChatMessage } from "@/lib/types";

type Props = {
  messages: ChatMessage[];
};

export function SourcesPanel({ messages }: Props) {
  const lastAssistant = [...messages]
    .reverse()
    .find((m) => m.role === "assistant" && m.citations && m.citations.length > 0);

  const citations = lastAssistant?.citations ?? [];

  return (
    <aside className="flex h-full flex-col border-l border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="border-b border-[var(--color-border)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--color-text-dim)]">
          Sources used
        </h2>
        <p className="mt-1 text-xs text-[var(--color-text-dim)]">
          Top {citations.length || "—"} chunks for the last answer
        </p>
      </div>
      <div className="flex-1 overflow-y-auto">
        {citations.length === 0 ? (
          <div className="p-4 text-xs text-[var(--color-text-dim)]">
            Sources will appear here after the assistant answers a question.
          </div>
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {citations.map((c, i) => (
              <li key={`${c.doc_id}-${c.chunk_index}-${i}`} className="p-4">
                <div className="flex items-start gap-2">
                  <FileText
                    size={14}
                    className="mt-0.5 shrink-0 text-[var(--color-text-dim)]"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-xs font-medium text-[var(--color-text)]">
                        {c.title || c.doc_id}
                      </span>
                      <span className="shrink-0 text-[10px] tabular-nums text-[var(--color-text-dim)]">
                        {c.score.toFixed(3)}
                      </span>
                    </div>
                    <div className="mt-0.5 truncate text-[10px] text-[var(--color-text-dim)]">
                      doc_id={c.doc_id} · chunk={c.chunk_index}
                      {c.page != null && ` · p.${c.page}`}
                    </div>
                    <div className="mt-2 text-xs leading-relaxed text-[var(--color-text-dim)]">
                      {c.snippet}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
