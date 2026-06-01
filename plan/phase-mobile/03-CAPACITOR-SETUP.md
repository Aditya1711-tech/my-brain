# 03 — Capacitor Setup

## Required packages

```bash
npm install @capacitor/core @capacitor/cli
npm install @capacitor/ios @capacitor/android
npm install @capacitor/keyboard @capacitor/status-bar @capacitor/app @capacitor/haptics
```

All Capacitor packages should be the same major version. As of 2026-06: **Capacitor 7.x**.

---

## capacitor.config.ts

Location: `web/capacitor.config.ts`

```ts
import { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.trove.app",
  appName: "Trove",
  webDir: "out",            // Not used for hosted mode, but required by Capacitor CLI
  server: {
    url: "https://your-deployed-url.vercel.app",   // ← production URL
    cleartext: false,
  },
  plugins: {
    Keyboard: {
      resize: "body",          // Resize WebView body when keyboard appears
      resizeOnFullScreen: true,
    },
    StatusBar: {
      style: "dark",           // Light status bar text (Trove dark theme)
      overlaysWebView: false,
    },
  },
};

export default config;
```

**For local development:** Change `server.url` to `http://192.168.x.x:3000` (your local IP). Capacitor does not use `localhost` for device connections. Set `cleartext: true` for HTTP during dev.

---

## iOS project

Location: `web/ios/`

Initialize: `cd web && npx cap add ios`

### Info.plist additions (automatic via plugin declarations)
- `NSPhotoLibraryUsageDescription` — file upload from photo library
- `NSCameraUsageDescription` — future camera capture (placeholder)

### Safe area and status bar
- `capacitor.config.ts` `StatusBar.overlaysWebView: false` — status bar does NOT overlay the WebView
- The WebView starts below the status bar automatically
- Use `env(safe-area-inset-bottom)` in CSS for home indicator

### App icons
Required sizes for iOS: 1024×1024 (App Store), plus Xcode generates the rest.
Location: `web/ios/App/App/Assets.xcassets/AppIcon.appiconset/`

Placeholder: Use the Trove SVG mark scaled to 1024×1024 on a `#1B4D52` (teal) background.

### Splash screen
Use `@capacitor/splash-screen` (optional — can defer).

---

## Android project

Location: `web/android/`

Initialize: `cd web && npx cap add android`

### AndroidManifest.xml additions
- `<uses-permission android:name="android.permission.INTERNET" />` (auto-added)
- `<uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />` — for file upload

### App icons
Location: `web/android/app/src/main/res/mipmap-*/`
Standard Android adaptive icon sizes. Generate with Android Studio or online tool.

### Cleartext for local dev
Add to `android/app/src/main/res/xml/network_security_config.xml`:
```xml
<network-security-config>
  <domain-config cleartextTrafficPermitted="true">
    <domain includeSubdomains="true">192.168.x.x</domain>
  </domain-config>
</network-security-config>
```

---

## webDir and build process

`webDir: "out"` is specified but not actually used in hosted mode — Capacitor needs this field populated, but when `server.url` is set, the WebView loads from the remote URL instead of local files.

For a true offline/bundled build (future):
1. `next build` → `next export` (would require removing server features — not planned)
2. Copy `out/` to native project

For now: `server.url` approach means no `next export` step is needed.

---

## Native plugins included

| Plugin | Why |
|--------|-----|
| `@capacitor/keyboard` | Resize WebView on keyboard show/hide; prevents input being obscured |
| `@capacitor/status-bar` | Style/hide status bar for dark theme |
| `@capacitor/app` | Handle back button (Android), app state events |
| `@capacitor/haptics` | Optional tactile feedback on interactions |

Plugins NOT included (out of scope):
- `@capacitor/camera` — deferred
- `@capacitor/filesystem` — not needed
- `@capacitor/push-notifications` — out of scope
- `@capacitor/preferences` — not needed (Supabase auth uses cookies, not localStorage)

---

## Sync command

After any code change:
```bash
cd web && npx cap sync
```

This copies the web build (if bundled) and updates native project dependencies. With hosted mode, sync mainly updates plugin dependencies in native projects.

---

## Opening native projects

```bash
# iOS (requires macOS + Xcode)
cd web && npx cap open ios

# Android (requires Android Studio)
cd web && npx cap open android
```

---

## Deep linking

Defer. Default Capacitor URL scheme (`com.trove.app://`) is created automatically but not configured for any routes. No changes needed.
