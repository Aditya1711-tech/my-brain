# 04 — Auth and API

## Supabase auth inside Capacitor WebView

**Cookie-based auth works correctly in hosted-in-WebView mode.**

When the Capacitor WebView loads `https://trove.vercel.app`, it behaves exactly like a browser:
- Supabase session cookies are set by the Next.js server (via `proxy.ts` middleware and API routes)
- The WebView's cookie jar stores them
- Every subsequent request from the WebView includes those cookies automatically
- The middleware refreshes the session on each request, keeping it alive

No changes to `lib/supabase/server.ts` or `lib/supabase/client.ts` are required.

**Potential gotcha — SameSite:** Supabase SSR sets cookies with `SameSite=Lax` by default. Since the WebView loads the app from its origin directly (not cross-origin), SameSite poses no issue.

---

## CORS

The Next.js app (on Vercel) makes BFF-to-FastAPI calls **server-side**, not from the WebView. The WebView only talks to `trove.vercel.app`, never directly to FastAPI. CORS configuration is not needed.

---

## Static export alternative (if ever needed)

If the hosted URL becomes unavailable and we need to bundle the app:
1. Remove all API routes and the server middleware
2. Replace BFF calls with direct Supabase/FastAPI calls from client
3. Switch Supabase auth from SSR cookies to client-side `localStorage` via `@supabase/supabase-js`
4. Use `@capacitor/preferences` for token storage

This is not planned. Documented here for reference only.

---

## API URL — FastAPI

`APP_API_URL` is a server-only env var used in:
- `app/api/chat/route.ts` → `${apiUrl}/chat`
- `app/api/documents/route.ts` → `${apiUrl}/enqueue`

The WebView never calls FastAPI directly. The Next.js server (Vercel) calls FastAPI over the private network. No changes needed for mobile.

For production: `APP_API_URL` must be set to the deployed FastAPI URL in Vercel environment variables.

---

## JWT forwarding

`/api/chat/route.ts` reads the session and passes `Authorization: Bearer ${session.access_token}` to FastAPI. This is server-side. Works identically in mobile because cookies are still present.

---

## File uploads — Supabase Storage from WebView

Upload flow:
1. User selects file via `react-dropzone` `<input type="file">` — WebView triggers native file picker ✅
2. `supabase.storage.from("user-uploads").upload(...)` — SDK makes XHR/fetch to `https://*.supabase.co/storage/v1/object/user-uploads/...` — cross-origin fetch from WebView ✅
3. Supabase Storage CORS is configured to allow any origin by default for public buckets; for authenticated uploads, the `apikey` header (anon key) is used — works ✅
4. BFF `/api/documents` call — same-origin (to `trove.vercel.app`) — works ✅

No changes needed.

---

## SSE streaming inside WebView

**iOS WKWebView** — `fetch` + `ReadableStream.getReader()` works since iOS 14.5 (March 2021). Minimum iOS target for new Capacitor apps is iOS 14, so this is safe.

**Android System WebView** — `fetch` + `ReadableStream` works in Chromium 88+ (shipped in Android WebView 88, early 2021). Capacitor's minimum Android target is API 23 (Android 6); WebView is auto-updated on modern devices.

The current implementation in `chat-panel.tsx` uses `res.body.getReader()` — this is the correct pattern. No EventSource polyfill needed.

**One risk:** Response buffering. Some intermediate proxies (Vercel Edge Network) may buffer SSE responses. Verify that `Cache-Control: no-cache` and `Connection: keep-alive` headers are set on the `/api/chat` response. Currently: ✅ already set in `app/api/chat/route.ts`.

---

## Summary of changes required for auth/API

**None required** for the hosted-in-WebView approach. All existing auth and API patterns work correctly in the WebView context.

The only configuration needed:
- Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` as Vercel env vars (already in `.env.local` for local dev)
- Set `APP_API_URL` to the deployed FastAPI URL in Vercel env vars
