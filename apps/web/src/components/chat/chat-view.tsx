"use client";

import { useEffect } from "react";
import { useConversations } from "@/lib/use-conversations";
import { Nav } from "@/components/nav";
import { MessageList } from "./message-list";
import { MessageInput } from "./message-input";
import { SourcesPanel } from "./sources-panel";
import { ConversationSidebar } from "./conversation-sidebar";

export function ChatView() {
  const {
    isHydrated,
    conversations,
    activeId,
    active,
    messages,
    isStreaming,
    error,
    createConversation,
    selectConversation,
    deleteConversation,
    send,
    stop,
  } = useConversations();

  // Auto-create the first conversation after hydration if the store is empty.
  useEffect(() => {
    if (isHydrated && conversations.length === 0) {
      createConversation();
    }
  }, [isHydrated, conversations.length, createConversation]);

  // If we hydrated and the active id is gone (e.g., it was deleted), pick the
  // most recent conversation as the new active.
  useEffect(() => {
    if (isHydrated && !activeId && conversations.length > 0) {
      selectConversation(conversations[0].id);
    }
  }, [isHydrated, activeId, conversations, selectConversation]);

  // Don't flash the layout before localStorage hydration finishes — avoids a
  // jarring "no conversations" → "your conversations" pop on every reload.
  if (!isHydrated) {
    return (
      <div className="flex h-screen items-center justify-center text-xs text-[var(--color-text-dim)]">
        loading…
      </div>
    );
  }

  return (
    <div className="grid h-screen grid-cols-1 md:grid-cols-[260px_1fr] lg:grid-cols-[260px_1fr_360px]">
      <ConversationSidebar
        conversations={conversations}
        activeId={activeId}
        isStreaming={isStreaming}
        onCreate={createConversation}
        onSelect={selectConversation}
        onDelete={deleteConversation}
      />

      <main className="flex h-full min-w-0 flex-col overflow-hidden">
        <header className="flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-4">
          <div className="flex min-w-0 items-center gap-6">
            <div className="min-w-0">
              <h1 className="text-base font-semibold text-[var(--color-text)]">
                danny_rag
              </h1>
              <p className="truncate text-xs text-[var(--color-text-dim)]">
                {active?.title ?? "no conversation"}
                {active?.sessionId && (
                  <span className="ml-2 font-mono">
                    · session {active.sessionId.slice(0, 8)}
                  </span>
                )}
              </p>
            </div>
            <Nav />
          </div>
        </header>

        {error && (
          <div className="border-b border-red-900 bg-red-950/50 px-6 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="flex-1 overflow-hidden">
          <MessageList messages={messages} />
        </div>

        <MessageInput onSend={send} onStop={stop} isStreaming={isStreaming} />
      </main>

      <div className="hidden lg:block">
        <SourcesPanel messages={messages} />
      </div>
    </div>
  );
}
