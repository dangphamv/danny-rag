"use client";

import { MessageSquare, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/lib/use-conversations";

type Props = {
  conversations: Conversation[];
  activeId: string | null;
  isStreaming: boolean;
  onCreate: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
};

export function ConversationSidebar({
  conversations,
  activeId,
  isStreaming,
  onCreate,
  onSelect,
  onDelete,
}: Props) {
  return (
    <aside className="flex h-full flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="border-b border-[var(--color-border)] p-3">
        <Button
          type="button"
          onClick={onCreate}
          disabled={isStreaming}
          className="w-full gap-2"
        >
          <Plus size={14} />
          New chat
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <div className="p-4 text-center text-xs text-[var(--color-text-dim)]">
            No conversations yet
          </div>
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {conversations.map((conv) => {
              const isActive = conv.id === activeId;
              const lastMsgs = conv.messages.length;
              return (
                <li
                  key={conv.id}
                  onClick={() => !isStreaming && !isActive && onSelect(conv.id)}
                  className={cn(
                    "group flex cursor-pointer items-start gap-2 px-3 py-3 transition-colors",
                    isActive
                      ? "bg-[var(--color-surface-2)]"
                      : "hover:bg-[var(--color-surface-2)]/50",
                    isStreaming && !isActive && "cursor-not-allowed opacity-60",
                  )}
                >
                  <MessageSquare
                    size={14}
                    className={cn(
                      "mt-0.5 shrink-0",
                      isActive
                        ? "text-[var(--color-accent)]"
                        : "text-[var(--color-text-dim)]",
                    )}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-[var(--color-text)]">
                      {conv.title}
                    </div>
                    <div className="text-[10px] text-[var(--color-text-dim)]">
                      {lastMsgs} {lastMsgs === 1 ? "msg" : "msgs"}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (isStreaming) return;
                      if (window.confirm(`Delete "${conv.title}"?`)) {
                        onDelete(conv.id);
                      }
                    }}
                    disabled={isStreaming}
                    className="shrink-0 text-[var(--color-text-dim)] opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100 disabled:cursor-not-allowed"
                    aria-label="Delete conversation"
                  >
                    <Trash2 size={12} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="border-t border-[var(--color-border)] px-3 py-2 text-[10px] text-[var(--color-text-dim)]">
        Stored in browser localStorage. Survives reloads on this device only.
      </div>
    </aside>
  );
}
