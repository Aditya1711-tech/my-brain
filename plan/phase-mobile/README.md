# Phase Mobile — Plan Index

Mobile app shell for Trove using Capacitor + responsive CSS.

## Read order

1. **00-DISCOVERY.md** — Codebase findings that drove all decisions. Read this first.
2. **01-STRATEGY.md** — Why Capacitor + hosted-in-WebView. Scope definition.
3. **02-RESPONSIVE-DESIGN.md** — Per-component mobile design plan.
4. **03-CAPACITOR-SETUP.md** — Capacitor config, plugins, iOS/Android init.
5. **04-AUTH-AND-API.md** — Auth, SSE, uploads inside WebView — confirms nothing needs to change.
6. **05-EXECUTION-PLAN.md** — Task list with IDs, dependencies, verification steps.

## Living files

- **PROGRESS-MOBILE.md** — Checklist of all task IDs. Mark [x] as completed.
- **KNOWLEDGE-MOBILE.md** — Notes discovered during implementation (quirks, version pins, gotchas).

## Session protocol

At the start of each session:
1. Read PROGRESS-MOBILE.md — find the first unchecked task
2. Read KNOWLEDGE-MOBILE.md — apply any gotchas already discovered
3. Implement the task
4. Mark it done in PROGRESS-MOBILE.md with timestamp
5. Update KNOWLEDGE-MOBILE.md if anything new was discovered
6. Move to next task

## Branch

`phase-mobile/main` — all changes on this branch. Merge to master at the end.

## Key decisions (summary)

- **Hosting model:** Hosted-in-WebView (NOT static export — server features required)
- **Capacitor WebView** loads the deployed Next.js URL (`server.url` in config)
- **Auth:** SSR cookies work identically in WebView — no changes needed
- **SSE:** `fetch` + `ReadableStream.getReader()` works on iOS 14.5+ and Android WebView Chromium 88+
- **File uploads:** Web `<input type="file">` → Supabase Storage SDK — no native plugin needed
- **Bottom tab bar** on mobile (≤767px) replaces the 76px sidebar
