"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChatEvent, ChatMessage } from "./types";

// ---------- types ----------

export type Conversation = {
  id: string;
  title: string;
  messages: ChatMessage[];
  sessionId: string | null;
  createdAt: number;
  updatedAt: number;
};

type Store = {
  conversations: Conversation[];
  activeId: string | null;
};

const STORAGE_KEY = "danny_rag.conversations.v1";
const NEW_CONV_TITLE = "New conversation";
const TITLE_MAX = 50;

// ---------- localStorage helpers ----------

function loadStore(): Store {
  if (typeof window === "undefined") return { conversations: [], activeId: null };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { conversations: [], activeId: null };
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.conversations)) {
      return { conversations: [], activeId: null };
    }
    return parsed as Store;
  } catch {
    return { conversations: [], activeId: null };
  }
}

function saveStore(store: Store): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    // localStorage full or disabled — silently ignore
  }
}

// ---------- pure helpers ----------

function newId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function deriveTitle(firstMessage: string): string {
  const cleaned = firstMessage.trim().replace(/\s+/g, " ");
  if (cleaned.length <= TITLE_MAX) return cleaned;
  return cleaned.slice(0, TITLE_MAX - 1) + "…";
}

function parseSseChunk(buffer: string): { events: ChatEvent[]; remainder: string } {
  const events: ChatEvent[] = [];
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";
  for (const part of parts) {
    const line = part.trim();
    if (!line.startsWith("data: ")) continue;
    const payload = line.slice(6);
    if (payload === "[DONE]") continue;
    try {
      events.push(JSON.parse(payload) as ChatEvent);
    } catch {
      // Ignore malformed event — backend should never emit invalid JSON.
    }
  }
  return { events, remainder };
}

// ---------- hook ----------

export function useConversations() {
  // Initial state must be SSR-safe (no window). Hydrate after mount.
  const [store, setStore] = useState<Store>({ conversations: [], activeId: null });
  const [isHydrated, setIsHydrated] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Hydrate from localStorage on mount.
  useEffect(() => {
    setStore(loadStore());
    setIsHydrated(true);
  }, []);

  // Persist on every change. Skip until hydrated so we don't clobber an
  // existing store with an empty initial state.
  useEffect(() => {
    if (isHydrated) saveStore(store);
  }, [store, isHydrated]);

  // Sorted view, newest activity first.
  const conversations = useMemo(
    () => [...store.conversations].sort((a, b) => b.updatedAt - a.updatedAt),
    [store.conversations],
  );

  const active = useMemo(
    () => store.conversations.find((c) => c.id === store.activeId) ?? null,
    [store.conversations, store.activeId],
  );

  const messages = active?.messages ?? [];

  // ---------- conversation list actions ----------

  const createConversation = useCallback((): string => {
    const id = newId();
    const now = Date.now();
    const newConv: Conversation = {
      id,
      title: NEW_CONV_TITLE,
      messages: [],
      sessionId: null,
      createdAt: now,
      updatedAt: now,
    };
    setStore((prev) => ({
      conversations: [...prev.conversations, newConv],
      activeId: id,
    }));
    return id;
  }, []);

  const selectConversation = useCallback((id: string) => {
    setStore((prev) => ({ ...prev, activeId: id }));
  }, []);

  const deleteConversation = useCallback((id: string) => {
    setStore((prev) => {
      const remaining = prev.conversations.filter((c) => c.id !== id);
      // If we deleted the active one, fall back to the most recently updated remaining.
      let nextActive = prev.activeId;
      if (prev.activeId === id) {
        const sorted = [...remaining].sort((a, b) => b.updatedAt - a.updatedAt);
        nextActive = sorted[0]?.id ?? null;
      }
      return { conversations: remaining, activeId: nextActive };
    });
  }, []);

  const renameConversation = useCallback((id: string, title: string) => {
    setStore((prev) => ({
      ...prev,
      conversations: prev.conversations.map((c) =>
        c.id === id
          ? { ...c, title: title.trim() || NEW_CONV_TITLE, updatedAt: Date.now() }
          : c,
      ),
    }));
  }, []);

  // ---------- streaming send ----------

  const send = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || isStreaming) return;

      // Make sure there's an active conversation. Capture the id we'll target
      // so subsequent state updates don't accidentally race a switch.
      let targetId = store.activeId;
      if (!targetId) {
        targetId = createConversation();
      }

      const conversationId = targetId;
      setError(null);
      const userMsgId = newId();
      const assistantMsgId = newId();

      // Append user msg + empty assistant msg, set title if this is the first.
      setStore((prev) => ({
        ...prev,
        conversations: prev.conversations.map((c) => {
          if (c.id !== conversationId) return c;
          const isFirst = c.messages.length === 0;
          return {
            ...c,
            title: isFirst ? deriveTitle(trimmed) : c.title,
            messages: [
              ...c.messages,
              { id: userMsgId, role: "user", content: trimmed },
              { id: assistantMsgId, role: "assistant", content: "", status: "streaming" },
            ],
            updatedAt: Date.now(),
          };
        }),
      }));

      setIsStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;

      // Patch the assistant message in the target conversation.
      const patchAssistant = (patch: Partial<ChatMessage>) => {
        setStore((prev) => ({
          ...prev,
          conversations: prev.conversations.map((c) => {
            if (c.id !== conversationId) return c;
            return {
              ...c,
              updatedAt: Date.now(),
              messages: c.messages.map((m) =>
                m.id === assistantMsgId ? { ...m, ...patch } : m,
              ),
            };
          }),
        }));
      };

      const setSessionId = (sid: string) => {
        setStore((prev) => ({
          ...prev,
          conversations: prev.conversations.map((c) =>
            c.id === conversationId ? { ...c, sessionId: sid } : c,
          ),
        }));
      };

      // Snapshot the current sessionId from the conversation we're targeting,
      // not from `active` which could change if the user switches conversations.
      const currentSessionId =
        store.conversations.find((c) => c.id === conversationId)?.sessionId ?? null;

      try {
        const resp = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: trimmed, session_id: currentSessionId }),
          signal: controller.signal,
        });

        if (!resp.ok || !resp.body) {
          const text = await resp.text().catch(() => "");
          throw new Error(`Backend error ${resp.status}: ${text || resp.statusText}`);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let answer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const { events, remainder } = parseSseChunk(buffer);
          buffer = remainder;

          for (const event of events) {
            if (event.type === "start") {
              setSessionId(event.session_id);
            } else if (event.type === "token") {
              answer += event.content;
              patchAssistant({ content: answer, status: "streaming" });
            } else if (event.type === "citations") {
              patchAssistant({ citations: event.citations });
            } else if (event.type === "grade") {
              patchAssistant({
                groundingScore: event.score,
                rewriteCount: event.rewrite_count,
              });
            } else if (event.type === "retry") {
              answer = "";
              patchAssistant({
                content: "",
                citations: undefined,
                status: "retrying",
                rewriteCount: event.rewrite_count,
              });
            } else if (event.type === "error") {
              throw new Error(event.message);
            } else if (event.type === "done") {
              patchAssistant({ status: "done" });
            }
          }
        }
        patchAssistant({ status: "done" });
      } catch (err) {
        const isAbort =
          (err instanceof DOMException && err.name === "AbortError") ||
          (err instanceof Error && err.name === "AbortError");
        if (isAbort) {
          patchAssistant({ status: "done" });
        } else {
          const message = err instanceof Error ? err.message : String(err);
          setError(message);
          patchAssistant({ status: "error", error: message });
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [createConversation, isStreaming, store.activeId, store.conversations],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    isHydrated,
    conversations,
    activeId: store.activeId,
    active,
    messages,
    isStreaming,
    error,
    createConversation,
    selectConversation,
    deleteConversation,
    renameConversation,
    send,
    stop,
  };
}
