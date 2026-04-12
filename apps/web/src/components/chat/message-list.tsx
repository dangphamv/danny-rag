"use client";

import { useEffect, useRef } from "react";
import { Bot, RefreshCcw, User } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";

type Props = {
  messages: ChatMessage[];
};

export function MessageList({ messages }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-[var(--color-text-dim)]">
        <div className="max-w-md text-center">
          <p className="text-lg font-medium text-[var(--color-text)]">
            Ask a question about your ingested documents
          </p>
          <p className="mt-2 text-sm">
            Answers are grounded in retrieved chunks. Citations appear in the right panel.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 overflow-y-auto p-6">
      {messages.map((m) => (
        <div key={m.id} className="flex gap-3">
          <div
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
              m.role === "user"
                ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                : "bg-[var(--color-surface-2)] text-[var(--color-text-dim)]",
            )}
          >
            {m.role === "user" ? <User size={16} /> : <Bot size={16} />}
          </div>
          <div className="flex-1 pt-1">
            <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-[var(--color-text-dim)]">
              <span>{m.role}</span>
              {m.role === "assistant" && m.groundingScore != null && (
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-[10px] tabular-nums",
                    m.groundingScore >= 0.7
                      ? "bg-green-950/60 text-green-300"
                      : "bg-yellow-950/60 text-yellow-300",
                  )}
                  title={`Grounding score · rewrite ${m.rewriteCount ?? 1}`}
                >
                  grounding {m.groundingScore.toFixed(2)}
                </span>
              )}
              {m.role === "assistant" && (m.rewriteCount ?? 0) > 1 && (
                <span
                  className="flex items-center gap-1 rounded bg-[var(--color-surface-2)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-dim)]"
                  title="Self-grading loop fired — answer below is from a rewritten query"
                >
                  <RefreshCcw size={9} /> rephrased
                </span>
              )}
            </div>
            {m.status === "retrying" && (
              <div className="mt-1 flex items-center gap-2 text-xs text-[var(--color-text-dim)]">
                <RefreshCcw size={12} className="animate-spin" />
                Grounding was low — rephrasing the query and retrying…
              </div>
            )}
            <div className="mt-1 whitespace-pre-wrap text-[var(--color-text)]">
              {m.content}
              {m.status === "streaming" && (
                <span className="ml-1 inline-block h-4 w-2 animate-pulse bg-[var(--color-accent)]" />
              )}
            </div>
            {m.status === "error" && m.error && (
              <div className="mt-2 rounded border border-red-900 bg-red-950/50 p-2 text-xs text-red-300">
                {m.error}
              </div>
            )}
          </div>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
