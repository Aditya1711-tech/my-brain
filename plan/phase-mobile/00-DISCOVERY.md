# 00 — Discovery Findings

Codebase read: 2026-06-01. Branch: phase-mobile/main.

---

## 1. Next.js version and config

**File:** `web/next.config.ts`
```ts
const nextConfig: NextConfig = {
  /* config options here */
};
```
- Next.js **16.2.6** (from package.json).
- No `output: "export"` — static export is NOT the default and is NOT configured.
- No image domains, no redirects.

**Verdict on static export:** ❌ NOT feasible. See section 3.

---

## 2. Route tree

```
web/app/
├── layout.tsx                          ← root layout — loads fonts, Toaster
├── (app)/
│   ├── layout.tsx                      ← server component — auth check + AppShell
│   ├── page.tsx                        ← Library (/)
│   ├── chat/page.tsx                   ← Chat (/chat)
│   ├── document/[id]/page.tsx          ← Document detail (/document/:id)
│   ├── graph/page.tsx                  ← Connections graph (/graph)
│   └── search/page.tsx                 ← Search (/search)
├── (auth)/
│   ├── login/page.tsx                  ← /login
│   └── signup/page.tsx                 ← /signup
├── api/
│   ├── chat/route.ts                   ← POST SSE proxy → FastAPI
│   ├── documents/route.ts              ← POST create + enqueue
│   ├── documents/[id]/signed-url/route.ts
│   ├── documents/[id]/thumbnail/route.ts
│   ├── documents/retry/route.ts
│   ├── search/route.ts                 ← POST search
│   └── threads/[id]/route.ts           ← GET thread history
└── auth/callback/route.ts              ← Supabase OAuth callback
```

---

## 3. Server-side features — why static export fails

### proxy.ts (middleware)
```ts
// Creates server-side Supabase client using cookies() — Next.js server runtime only
const supabase = createServerClient(...)
const { data: { user } } = await supabase.auth.getUser();
// Redirects unauthenticated users to /login
```
The middleware runs on every request to refresh the Supabase session. It reads and writes HTTP cookies. **Requires server runtime.** Cannot run in static export.

### app/(app)/layout.tsx
```ts
export default async function AppLayout({ children }) {
  const supabase = await createClient();  // lib/supabase/server.ts — reads cookies()
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  return <AppShell user={user}>{children}</AppShell>;
}
```
Server component that reads cookies and redirects. **Requires server runtime.**

### API routes (all require server runtime)
- `/api/chat` — reads session cookie, proxies SSE to FastAPI
- `/api/documents` — reads session cookie, calls FastAPI enqueue
- `/api/search` — BFF search
- `/api/threads/[id]` — BFF thread history
- `/api/documents/[id]/signed-url` — generates signed URL
- `/api/documents/[id]/thumbnail` — fetches thumbnail via signed URL

**Conclusion: Static export is impossible. Must use hosted-in-WebView approach.**

---

## 4. Auth — Supabase SSR cookie flow

**lib/supabase/server.ts:**
```ts
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";  // Next.js server runtime only

export async function createClient() {
  const cookieStore = await cookies();
  return createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll() { return cookieStore.getAll(); },
      setAll(cookiesToSet) {
        try { cookiesToSet.forEach(({ name, value, options }) =>
          cookieStore.set(name, value, options)); }
        catch { /* Server Component — ignore, proxy handles it */ }
      },
    },
  });
}
```

**lib/supabase/client.ts:**
```ts
import { createBrowserClient } from "@supabase/ssr";
export function createClient() {
  return createBrowserClient(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY);
}
```

Auth is SSR cookie-based. In a hosted-in-WebView setup, the WebView has its own cookie jar — this works identically to a browser. No changes needed.

---

## 5. Supabase Realtime

**lib/hooks/use-realtime-documents.ts:**
```ts
const channel = supabase
  .channel("documents-realtime")
  .on("postgres_changes", { event: "INSERT", schema: "public", table: "documents" }, ...)
  .on("postgres_changes", { event: "UPDATE", ... }, ...)
  .subscribe();
```
Uses `@supabase/supabase-js` WebSocket connection. Works in iOS WKWebView and Android WebView without changes.

---

## 6. File uploads

**components/upload/dropzone.tsx** — react-dropzone → Supabase Storage client SDK → BFF:
1. `react-dropzone` uses `<input type="file">` — works in WebView (triggers native file picker)
2. `supabase.storage.from("user-uploads").upload(...)` — XHR/fetch to Supabase — works in WebView
3. `/api/documents` BFF call — standard fetch — works in WebView

No native Capacitor plugin required for basic file uploads. `@capacitor/camera` could be added later for camera capture (out of scope for Phase A+B).

---

## 7. SSE chat streaming

**app/api/chat/route.ts** — returns `new Response(res.body, { headers: { "Content-Type": "text/event-stream" } })`

**components/chat/chat-panel.tsx** — consumes via:
```ts
const res = await fetch("/api/chat", { method: "POST", ... });
const reader = res.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();
  ...
}
```
Uses `fetch` + `ReadableStream.getReader()`. This is the correct pattern and works in:
- iOS WKWebView (iOS 14.5+, shipped 2021) ✅
- Android System WebView (Chromium 88+, 2021) ✅

No EventSource polyfill needed.

---

## 8. CSS and layout

**globals.css** — Tailwind v4, CSS variables, no custom breakpoint config.
Default Tailwind breakpoints apply: `sm: 640px`, `md: 768px`, `lg: 1024px`.

Current layout uses **inline styles** almost exclusively — no Tailwind layout classes except in chat-panel.tsx (`flex flex-col h-full`, `max-w-[85%]`, etc.).

**Board/masonry grid:**
```css
.board { columns: 260px; column-gap: 20px; }
```
On a 360px phone: `columns: 260px` → 1 column. On a 428px phone: 1 column. Good — auto-collapses. But padding `40px 40px` in library-page.tsx is too large for mobile.

**Sidebar** — fixed `width: 76px`, always visible. Must be hidden on mobile.

---

## 9. Module-level window/document access

No `window.*`, `document.*`, or `localStorage.*` at module load time found in `/web/lib/` or `/web/stores/`. Client components are all `"use client"` with React hooks — safe for SSR.

Note: `react-force-graph-2d` is loaded via `dynamic(..., { ssr: false })` — already guarded. ✅

---

## 10. API URLs and env vars

**web/.env.local:**
```
NEXT_PUBLIC_SUPABASE_URL=https://rumpjmbpfiqfcvlplckc.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...   ← server-only (no NEXT_PUBLIC prefix)
BACKEND_API_KEY=trove              ← server-only
APP_API_URL=http://localhost:8000  ← server-only, FastAPI URL
```

`APP_API_URL` is **server-only** — never exposed to the client. The mobile WebView never calls FastAPI directly; it calls Next.js BFF routes which call FastAPI server-to-server. This is correct and secure.

No `NEXT_PUBLIC_API_URL` exists or is needed.

---

## Key constraints summary

| Feature | Works in WebView? | Notes |
|---------|------------------|-------|
| Supabase cookie auth | ✅ | WebView has cookie jar |
| Supabase Realtime (WS) | ✅ | Native WS support |
| SSE streaming (fetch+ReadableStream) | ✅ | iOS 14.5+, Android WebView Chromium 88+ |
| File upload (input[type=file]) | ✅ | WebView triggers native picker |
| Supabase Storage upload | ✅ | Standard XHR/fetch |
| react-force-graph-2d (canvas) | ✅ | Client-only, dynamic import |
| Server middleware (proxy.ts) | ✅ | Runs on server, not in WebView |
| Static export | ❌ | Server features required |
