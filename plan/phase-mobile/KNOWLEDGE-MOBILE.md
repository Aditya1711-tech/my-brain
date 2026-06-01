# Knowledge — Mobile Phase

Living notes. Updated as implementation proceeds.

---

## Capacitor

- **Version:** Capacitor 8.x (8.3.4 core/cli, 8.1.0 app, 8.0.x plugins) — installed 2026-06-01.
- **Node requirement:** Capacitor 8 requires Node >=22. Project was on Node 20. Switched to Node 24.16.0 via `nvm install lts`.
- **PATH fix on Windows bash:** After `nvm use`, node is not on PATH automatically. Prefix all `npx cap` commands with `export PATH="/c/nvm4w/nodejs:$PATH"`.
- **`cap init` skips if config exists:** Running `npx cap init` errors if `capacitor.config.ts` already exists — that's expected. Run `npx cap add ios/android` directly.
- **`webDir` must exist and contain `index.html`:** Even in hosted mode, `cap sync` requires the webDir to exist and contain `index.html`. Solution: point `webDir` to `public/` and add a placeholder `public/index.html`.
- **Hosted mode:** Set `CAPACITOR_SERVER_URL` env var to the deployed Next.js URL. The `capacitor.config.ts` reads this env var and sets `server.url` when present.

## iOS

- `ios/App/App/Assets.xcassets/AppIcon.appiconset/` — needs `AppIcon-512@2x.png` (1024×1024).
- Placeholder icon generated with Pillow (Python). Replace with proper Trove brand icon before release.
- Xcode project at `ios/App/App.xcodeproj`. Workspace (with SPM plugins) at `ios/App/App.xcworkspace`.
- To open: `export PATH="/c/nvm4w/nodejs:$PATH" && npx cap open ios` (requires macOS + Xcode).

## Android

- Android project at `android/`. Icons generated in `mipmap-*` folders using Pillow.
- To open: `export PATH="/c/nvm4w/nodejs:$PATH" && npx cap open android` (requires Android Studio).
- `npx cap open android` on Windows may need Android Studio in PATH.

## SSE / Streaming

- Chat uses `fetch` + `ReadableStream.getReader()` — works in iOS WKWebView (14.5+) and Android WebView (Chromium 88+). No polyfill needed.
- `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive` — all set in `/api/chat/route.ts` ✅

## Auth / Cookies

- Supabase SSR cookie auth works identically in Capacitor WebView.
- WebView has its own cookie jar scoped to the loaded origin.
- No SameSite issues because the WebView loads from the app's own origin.

## CSS / Layout

- App uses **inline styles** almost exclusively — responsive changes need `useIsMobile()` hook.
- `useIsMobile()` hook at `lib/hooks/use-is-mobile.ts` — `window.matchMedia("(max-width: 767px)")`.
- CSS classes `.trove-sidebar` and `.trove-bottom-nav` toggle visibility at the 767px breakpoint via `globals.css`.
- Safe area: `env(safe-area-inset-top/bottom)` works when `viewport-fit=cover` is set in the Next.js `viewport` export.
- Bottom nav height: `--bottom-nav-height: 60px`. Content padding bottom: `var(--mobile-content-pb)` = `calc(60px + env(safe-area-inset-bottom) + 16px)`.
- StatusBar backgroundColor `#131316` matches `--bg-canvas` dark theme.
- `body { padding-top: env(safe-area-inset-top) }` in `globals.css` pushes content below the native status bar.

## Deferred enhancements (add after current implementation)

- Offline fallback page: bundled webDir + @capacitor/network plugin to show a graceful offline screen when the hosted app is unreachable
- Dev workflow: env-driven capacitor.config.ts (dev vs prod), `next dev -H 0.0.0.0`, scripts for the localhost / 10.0.2.2 / LAN-IP matrix
- proxy.ts matcher audit: confirm static assets and public routes excluded; consider longer Supabase session on mobile to reduce refresh frequency
- Replace placeholder app icons with proper Trove brand icons (1024×1024 PNG on teal background)
