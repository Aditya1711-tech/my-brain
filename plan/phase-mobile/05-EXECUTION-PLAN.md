# 05 — Execution Plan

## Phase A: Responsive CSS (do first — independent of Capacitor)

### M-A-01: Safe area CSS + mobile globals
**What:** Add safe area insets, mobile board grid, and viewport meta to globals.
**Files:** `web/app/globals.css`, `web/app/layout.tsx`
**Verify:** Open in browser, resize to 360px wide — grid shows 2 columns, no horizontal scroll.
**Time:** 20 min

### M-A-02: `useIsMobile` hook
**What:** Create `web/lib/hooks/use-is-mobile.ts` — media query hook used by components.
**Files:** `web/lib/hooks/use-is-mobile.ts`
**Verify:** Import in a component, log result.
**Time:** 10 min

### M-A-03: BottomNav component
**What:** Create `web/components/shared/bottom-nav.tsx` — Library / Search / Chat / Graph tabs.
**Files:** `web/components/shared/bottom-nav.tsx`
**Verify:** Render on mobile — 4 tabs visible, active tab highlighted, tap navigates.
**Time:** 30 min

### M-A-04: AppShell — sidebar/bottom-nav switch
**What:** Update `app-shell.tsx` to hide sidebar and show BottomNav on mobile; add bottom padding to `<main>`.
**Files:** `web/components/shared/app-shell.tsx`
**Depends on:** M-A-02, M-A-03
**Verify:** At 375px: no sidebar visible, bottom nav present. At 768px+: sidebar visible, no bottom nav.
**Time:** 20 min

### M-A-05: Library page responsive
**What:** Reduce padding, shrink search font size, reposition FAB above bottom bar.
**Files:** `web/components/library/library-page.tsx`
**Depends on:** M-A-02
**Verify:** Library loads on 375px with proper padding, search header readable, FAB not hidden behind bottom bar.
**Time:** 25 min

### M-A-06: Chat panel — safe area keyboard
**What:** Add `padding-bottom: max(12px, env(safe-area-inset-bottom))` to input bar.
**Files:** `web/components/chat/chat-panel.tsx`
**Verify:** Input bar not obscured on iPhone simulator (home indicator area).
**Time:** 15 min

### M-A-07: Search page responsive
**What:** Reduce outer padding on mobile, responsive search results.
**Files:** `web/components/search/search-page.tsx`
**Verify:** Search renders cleanly at 375px.
**Time:** 15 min

### M-A-08: Document detail — vertical stack on mobile
**What:** On mobile, stack the fields panel above the chat panel (instead of side-by-side).
**Files:** `web/components/document/document-detail-page.tsx`
**Depends on:** M-A-02
**Verify:** Document detail renders on 375px with fields stacked above chat.
**Time:** 30 min

### M-A-09: Graph page — entity panel mobile
**What:** On mobile, entity detail panel slides up from bottom instead of fixed right side panel.
**Files:** `web/components/graph/graph-page.tsx`
**Depends on:** M-A-02
**Verify:** Force graph fills mobile width; tap node → panel appears from bottom.
**Time:** 25 min

---

## Phase B: Capacitor scaffolding + first run

### M-B-01: Install Capacitor packages
**What:** `npm install @capacitor/core @capacitor/cli @capacitor/ios @capacitor/android @capacitor/keyboard @capacitor/status-bar @capacitor/app @capacitor/haptics`
**Files:** `web/package.json`, `web/node_modules/`
**Verify:** `npx cap --version` returns version.
**Time:** 10 min

### M-B-02: capacitor.config.ts
**What:** Create `web/capacitor.config.ts` with appId, server.url, plugin config.
**Files:** `web/capacitor.config.ts`
**Verify:** File parses, `npx cap doctor` reports no errors.
**Time:** 10 min

### M-B-03: Initialize Capacitor + add iOS
**What:** `npx cap init` (if needed) + `npx cap add ios`
**Files:** `web/ios/`
**Verify:** `web/ios/App/App.xcworkspace` exists.
**Time:** 5 min

### M-B-04: Add Android
**What:** `npx cap add android`
**Files:** `web/android/`
**Verify:** `web/android/app/src/main/java/` exists.
**Time:** 5 min

### M-B-05: cap sync
**What:** `npx cap sync` — updates native projects with plugin changes.
**Files:** Updates `web/ios/` and `web/android/`
**Verify:** No errors in sync output.
**Time:** 5 min

### M-B-06: Verify native project opens
**What:** `npx cap open ios` and `npx cap open android` — confirm projects open in Xcode/Android Studio.
**Files:** None
**Verify:** Xcode shows App.xcworkspace with correct bundle ID. Android Studio shows android/ project.
**Time:** 10 min (environment-dependent)

---

## Phase C: Native polish

### M-C-01: Status bar and safe area CSS
**What:** Confirm `env(safe-area-inset-top/bottom)` applied correctly. Set StatusBar style in capacitor.config.ts.
**Files:** `web/capacitor.config.ts`, `web/app/globals.css`
**Verify:** Status bar does not overlap content on simulator.
**Time:** 15 min

### M-C-02: App icons placeholder
**What:** Add placeholder icons for iOS and Android.
**Files:** `web/ios/App/App/Assets.xcassets/AppIcon.appiconset/`, `web/android/app/src/main/res/mipmap-*/`
**Verify:** Xcode shows icon preview without errors.
**Time:** 20 min

### M-C-03: Keyboard plugin wiring
**What:** Ensure `@capacitor/keyboard` `resize: "body"` is active; verify no content hidden under keyboard.
**Files:** `web/capacitor.config.ts`
**Verify:** On simulator, focus chat input → keyboard appears → input stays visible.
**Time:** 15 min

---

## Phase D: Native-only features (deferred)

All Phase D items are out of scope for this session. Listed for future reference:
- D-01: Camera capture for file upload (via `@capacitor/camera`)
- D-02: Native share sheet (via `@capacitor/share`)
- D-03: Haptic feedback on send message

---

## Phase E: Build verification

### M-E-01: iOS debug build check
**What:** In Xcode, build the project for simulator. Confirm no build errors.
**Verify:** Build succeeds with 0 errors.
**Time:** 10 min (Xcode build time varies)

### M-E-02: Android debug build check
**What:** In Android Studio, build and run on emulator.
**Verify:** App launches, loads remote URL, renders library.
**Time:** 15 min

---

## Dependencies

```
M-A-01
M-A-02 (independent)
M-A-03 (independent)
M-A-04 → M-A-02, M-A-03
M-A-05 → M-A-02
M-A-06 (independent)
M-A-07 (independent)
M-A-08 → M-A-02
M-A-09 → M-A-02
M-B-01 (independent of Phase A — can run in parallel)
M-B-02 → M-B-01
M-B-03 → M-B-02
M-B-04 → M-B-02
M-B-05 → M-B-03, M-B-04
M-B-06 → M-B-05
M-C-01 → M-B-05
M-C-02 → M-B-05
M-C-03 → M-B-05
M-E-01 → M-C-01, M-C-02, M-C-03
M-E-02 → M-E-01
```
