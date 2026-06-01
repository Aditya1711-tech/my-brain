# 01 — Strategy

## Why Capacitor + responsive CSS

**Capacitor** wraps the existing Next.js web app in a native iOS/Android shell with zero rewrite. The app continues to run as a standard web app; Capacitor provides:
- Native app packaging (.ipa / .apk)
- Access to native device APIs (camera, file system, status bar, keyboard)
- The "app" feel: full-screen, no browser chrome, home screen icon, splash screen

**Responsive CSS** makes the existing UI work well on phone-sized screens. This is independent of Capacitor and improves the mobile browser experience too.

**Why not alternatives:**

| Approach | Verdict |
|----------|---------|
| PWA-only | No iOS home screen persistence; no App Store distribution; no native APIs |
| Expo / React Native | Full rewrite required — weeks of work |
| Static export + bundled | ❌ Impossible: middleware, server components, and 6+ API routes require server runtime |
| Tauri Mobile | Immature; different build toolchain |

---

## Hosting model: Hosted-in-WebView (NOT static export)

**Decision: The Capacitor WebView loads the deployed Next.js app over HTTPS.**

This is the only viable approach because the app has server-side requirements that cannot be statically exported:
- `proxy.ts` middleware refreshes Supabase sessions via SSR cookies on every request
- `(app)/layout.tsx` is a server component that redirects unauthenticated users
- Six API route handlers (`/api/chat`, `/api/documents`, `/api/search`, etc.) run server-side

In `capacitor.config.ts`, the `server.url` field is set to the deployed Next.js URL:
- **Production:** `https://trove.vercel.app` (or whatever the actual URL is)
- **Development:** `http://192.168.x.x:3000` (local IP of the dev machine — NOT localhost, since the device/emulator has a different network namespace)

### Architecture diagram

```
[iOS/Android Device]
  └── Capacitor Native Shell
        └── WKWebView / System WebView
              └── loads → https://trove.vercel.app
                            └── Next.js (Vercel / server)
                                  ├── proxy.ts (auth middleware)
                                  ├── /api/chat → FastAPI SSE
                                  ├── /api/documents → FastAPI enqueue
                                  └── /api/search → FastAPI search
                                        └── FastAPI (deployed separately)
```

### What lives where

| Thing | Location |
|-------|----------|
| React bundle | Served by Next.js on Vercel |
| API routes (BFF) | Served by Next.js on Vercel |
| FastAPI backend | Deployed separately (Fly.io, Railway, etc.) |
| Native shell | /web/ios, /web/android (Capacitor projects) |
| Capacitor plugins | Compiled into native shell |

---

## Trade-offs

| Pro | Con |
|-----|-----|
| Zero code rewrite | Requires deployed URL (not offline-capable by default) |
| Auth works identically (cookie jar) | Network latency (loads over HTTPS) |
| SSE streaming works | Need server running for dev testing on device |
| All existing flows preserved | App Store review may inspect WebView-heavy apps |
| Capacitor native APIs available | |

---

## Scope

### In scope
- Responsive CSS for all 5 main screens (library, chat, document detail, search, graph)
- Bottom tab bar on mobile (≤767px) replacing the sidebar
- Safe area insets (notch, home indicator)
- Keyboard-aware chat input
- Capacitor iOS + Android project initialization
- capacitor.config.ts with hosted server URL
- App icon and splash screen placeholders
- Capacitor plugins: @capacitor/keyboard, @capacitor/status-bar, @capacitor/app, @capacitor/haptics

### Explicitly out of scope
- Push notifications
- In-app purchases
- App Store / Play Store submission
- Deep linking
- Native Swift/Kotlin modules
- Offline mode
- Biometric auth
- Camera capture for upload (deferred — web file input is sufficient)
- @capacitor/filesystem (not needed — uploads use Supabase Storage directly)
