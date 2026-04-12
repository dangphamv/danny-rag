// Mirrors apps/api/src/graph/state.py:Citation
export type Citation = {
  doc_id: string;
  chunk_index: number;
  title: string;
  source_uri: string;
  page: number | null;
  snippet: string;
  score: number;
};

// SSE event types emitted by the FastAPI /chat endpoint
// (see apps/api/src/routes/chat.py and src/graph/nodes.py).
export type ChatEvent =
  | { type: "start"; session_id: string }
  | { type: "token"; content: string }
  | { type: "citations"; citations: Citation[] }
  | { type: "grade"; score: number; rewrite_count: number; skipped: boolean }
  | { type: "retry"; rewrite_count: number }
  | { type: "done" }
  | { type: "error"; message: string };

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  status?: "streaming" | "retrying" | "done" | "error";
  error?: string;
  // M10: populated when the self-grading loop fires. Surfaces the final
  // grounding score and how many rewrites were spent.
  groundingScore?: number;
  rewriteCount?: number;
};
