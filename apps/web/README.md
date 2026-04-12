# danny_rag web

Next.js 15 (App Router) chat UI for the RAG knowledge chatbot. TypeScript + Tailwind v4 + a project-local custom streaming `useChat` hook.

## Setup

```bash
# from repo root
docker compose up -d            # data plane (qdrant, postgres, langfuse, ...)

# in apps/api (separate terminal)
cd apps/api
uv sync
uv run uvicorn src.main:app --reload --port 8000

# in apps/web
cd apps/web
cp .env.local.example .env.local      # API_URL + API_KEY (server-side only)
pnpm install
pnpm dev                              # http://localhost:3000
```

Open <http://localhost:3000>, ingest a doc first via the CLI:

```bash
cd apps/api && uv run python -m src.ingestion.cli ../../data/sample.txt
```

Then ask a question in the UI. Tokens stream in real-time; the right panel shows the source chunks the assistant grounded in.

## Layout

```
apps/web/
├── package.json              # Next 15, React 19, Tailwind 4, lucide-react
├── tsconfig.json             # strict, paths @/* → ./src/*
├── next.config.ts            # SSE-friendly headers on /api/chat
├── postcss.config.mjs        # @tailwindcss/postcss
├── eslint.config.mjs         # next/core-web-vitals + next/typescript (flat)
├── .env.local.example
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx          # mounts <ChatView />
│   │   ├── globals.css       # @import "tailwindcss"; + theme vars
│   │   └── api/
│   │       └── chat/
│   │           └── route.ts  # SSE proxy → FastAPI; injects X-API-Key (MTC-07)
│   ├── components/
│   │   ├── chat/
│   │   │   ├── chat-view.tsx
│   │   │   ├── message-list.tsx
│   │   │   ├── message-input.tsx
│   │   │   └── sources-panel.tsx
│   │   └── ui/
│   │       └── button.tsx
│   └── lib/
│       ├── utils.ts          # cn(...)
│       ├── types.ts          # ChatEvent, ChatMessage, Citation (mirrors backend)
│       └── use-chat.ts       # custom streaming hook (60 lines, no AI SDK)
```

## Why a custom hook instead of Vercel AI SDK `useChat`

The plan said to use Vercel AI SDK's `useChat`, but the AI SDK consumes its own data-stream protocol (LLM-shaped events with specific framing). Our FastAPI `/chat` emits a simpler custom SSE protocol (`{type: "token" | "citations" | "done", ...}`) coming straight out of LangGraph's custom stream writer.

Two ways to bridge:
1. Convert in the Next.js route handler from our format to AI SDK format, then use `useChat`. Adds a translation layer and couples us to AI SDK version churn.
2. Write a thin local hook that consumes our own protocol directly.

Option 2 is what's wired here: `src/lib/use-chat.ts` is ~140 lines, has no external streaming dependency, and exposes the same surface as Vercel's hook (`messages`, `isStreaming`, `send`, `stop`, `reset`). When (if) Vercel AI SDK adds a "passthrough SSE" mode we can revisit. **This deviation should become an ADR in M14.**

## Server-side API key (MTC-07)

The browser **never** sees the FastAPI API key.

```
browser → POST /api/chat (no auth) → Next route handler →
  POST {API_URL}/chat with X-API-Key: {API_KEY} → SSE stream piped back
```

`API_KEY` lives in `.env.local` (gitignored) and is read server-side only. There is **no** `NEXT_PUBLIC_API_KEY`. Verify with `grep -r NEXT_PUBLIC src/ — ` should return zero matches related to the key.

## Commands

```bash
pnpm dev                  # dev server on :3000
pnpm build                # production build
pnpm typecheck            # tsc --noEmit
pnpm lint                 # next lint
```

## Known gaps

- **No traces page.** Just open Langfuse at <http://localhost:3001> directly.
- **No tests.** Add Playwright e2e in M13 — the project's `playwright` MCP is wired and ready.

## Routes

| Route | Purpose |
|---|---|
| `/` | Streaming chat UI |
| `/ingest` | Drag-drop document upload (PDF/MD/HTML/TXT, ≤25 MB, MTC-09) |
| `/api/chat` | Server-side SSE proxy → FastAPI `/chat` (injects `X-API-Key`) |
| `/api/ingest` | Server-side multipart proxy → FastAPI `/ingest` (injects `X-API-Key`) |
