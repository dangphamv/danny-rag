"use client";

import { useCallback, useRef, useState, type DragEvent, type ChangeEvent } from "react";
import { Upload } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
};

export function UploadZone({ onFiles, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      if (disabled) return;
      const files = Array.from(e.dataTransfer.files);
      if (files.length) onFiles(files);
    },
    [onFiles, disabled],
  );

  const handleSelect = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files ?? []);
      if (files.length) onFiles(files);
      // Reset so re-selecting the same file fires the event again.
      e.target.value = "";
    },
    [onFiles],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-12 transition-colors",
        isDragging
          ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)]/30"
          : "border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-2)]",
        disabled && "pointer-events-none opacity-50",
      )}
    >
      <Upload size={32} className="text-[var(--color-text-dim)]" />
      <div className="text-center">
        <p className="text-sm font-medium text-[var(--color-text)]">
          Drop files here, or click to browse
        </p>
        <p className="mt-1 text-xs text-[var(--color-text-dim)]">
          PDF, Markdown, HTML, or plain text · max 25 MB per file
        </p>
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.md,.markdown,.html,.htm,.txt,application/pdf,text/markdown,text/html,text/plain"
        onChange={handleSelect}
        className="hidden"
      />
    </div>
  );
}
