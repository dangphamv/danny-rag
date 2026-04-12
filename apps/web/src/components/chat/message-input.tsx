"use client";

import { Send, Square } from "lucide-react";
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";

type Props = {
  onSend: (q: string) => void;
  onStop: () => void;
  isStreaming: boolean;
};

export function MessageInput({ onSend, onStop, isStreaming }: Props) {
  const [value, setValue] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!value.trim() || isStreaming) return;
    onSend(value);
    setValue("");
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(e);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="border-t border-[var(--color-border)] bg-[var(--color-surface)] p-4"
    >
      <div className="flex items-end gap-2">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKey}
          rows={2}
          placeholder="Ask anything about your ingested documents…"
          className="min-h-[60px] flex-1 resize-none rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
          disabled={isStreaming}
        />
        {isStreaming ? (
          <Button type="button" variant="ghost" onClick={onStop} aria-label="Stop">
            <Square size={16} />
          </Button>
        ) : (
          <Button type="submit" disabled={!value.trim()} aria-label="Send">
            <Send size={16} />
          </Button>
        )}
      </div>
      <div className="mt-2 text-xs text-[var(--color-text-dim)]">
        Enter to send · Shift+Enter for newline
      </div>
    </form>
  );
}
