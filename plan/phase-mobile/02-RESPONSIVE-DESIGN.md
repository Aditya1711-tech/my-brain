# 02 — Responsive Design Plan

Mobile breakpoint: `≤767px` (max-width: 767px in media queries, or Tailwind `md:` prefix for ≥768px).
Touch target minimum: 44×44px.

---

## Bottom tab bar (replaces sidebar on mobile)

The sidebar is a 76px-wide vertical rail. On mobile it must be replaced by a bottom tab bar.

**Tabs and routes:**
| Icon | Label | Route |
|------|-------|-------|
| Library | Library | `/` |
| Search | Search | `/search` |
| MessageSquare | Chat | `/chat` |
| GitBranch | Graph | `/graph` |

**Design:**
- Fixed bottom, full width
- Height: 60px + `env(safe-area-inset-bottom)` for home indicator
- Background: `var(--bg-elevated)` with `border-top: 1px solid var(--border-faint)`
- Each tab: icon + label, 44px minimum tap target
- Active tab: `var(--accent)` color icon + label; inactive: `var(--fg-subtle)`
- Active indicator: 2px line above the tab

**Implementation:**
- New component: `components/shared/bottom-nav.tsx`
- `app-shell.tsx`: render `<Sidebar>` on md+ (hidden on mobile), render `<BottomNav>` on mobile (hidden on md+)
- `main` element gets `padding-bottom: calc(60px + env(safe-area-inset-bottom))` on mobile to prevent content hiding behind bottom bar

---

## Top app bar pattern

Most pages have sticky headers already (e.g., `BoardSearchHeader` in library). On mobile:
- Existing sticky headers work fine
- Font size of `"Search your trove…"` (60px) reduced to 32px on mobile
- Header padding reduced: `40px 40px` → `16px 16px` on mobile

No separate top app bar component needed — existing headers adapt.

---

## Library page (components/library/library-page.tsx)

**Current:** `padding: "8px 40px 120px"` — too wide for 360px phones.

**Changes:**
- Outer padding: `8px 40px 120px` → responsive: `8px 16px 100px` on mobile, `8px 40px 120px` on desktop
- Search header padding: `"40px 40px 28px"` → `"20px 16px 16px"` on mobile
- Search header `fontSize: 60` → `fontSize: 32` on mobile (when idle)
- Search input `fontSize: 32` → `fontSize: 22` on mobile (when active)
- FAB: `right: 32, bottom: 32` → `right: 20, bottom: calc(72px + env(safe-area-inset-bottom))` on mobile (clear bottom bar)
- `.board` CSS: add mobile override — `columns: 160px` (gives 2 columns on 360px phone)
- Search chip wrapping: current `flexWrap: "wrap"` already works on mobile ✅

---

## Search page (components/search/search-page.tsx)

- Input and chip row already uses flex — needs padding reduction only
- Outer padding: reduce to `16px` on mobile
- Search results: same responsive grid as library board

---

## Chat page (components/chat/chat-panel.tsx)

**Keyboard-aware layout:**
The chat input must stay above the keyboard on mobile. This is handled by:
1. CSS: `env(keyboard-inset-height)` (Chrome Android) — not yet widely supported
2. Better approach: Capacitor `@capacitor/keyboard` plugin resizes the WebView — no CSS hack needed
3. Fallback: `padding-bottom: env(safe-area-inset-bottom)` on the input bar

**Changes:**
- Input bar padding: add `padding-bottom: max(12px, env(safe-area-inset-bottom))`
- Message bubbles: `max-w-[85%]` already responsive ✅
- Citation badges: `max-w-[80px]` on filename truncation — increase to `120px` on wider screens
- Chat page wrapper: needs `height: 100%` from top to work on mobile (already has `flex flex-col h-full`) ✅

---

## Document detail (components/document/document-detail-page.tsx)

Document detail is a split layout (fields + chat). On mobile:
- Stack vertically (fields panel on top, chat panel below, or tabbed)
- Each section individually scrollable
- Action buttons (View, Open) get full-width treatment on mobile
- Pipeline stage list collapses to simple status text on mobile (optional)

Concrete change: detect mobile via CSS and switch from horizontal split to vertical stack.

---

## Upload dialog (UploadDialog in library-page.tsx)

Current: `width: "min(560px, 100%)"`, `padding: 24`.
On mobile, this already spans full width minus padding — acceptable.

Small changes:
- `padding: 24` → `padding: 12` on mobile for the overlay
- Dialog border-radius: 18px stays
- Drag-and-drop drop area text is fine as-is

---

## Graph page (components/graph/graph-page.tsx)

The force graph uses canvas with dynamic dimensions (`containerRef` + `ResizeObserver`).
On mobile:
- Canvas fills available width automatically (containerRef.current.offsetWidth) ✅
- Entity detail panel: currently a fixed side panel — on mobile, convert to bottom sheet style (slide up from bottom)
- Legend: already collapsible — starts collapsed on mobile

---

## Tailwind breakpoint conventions

Use `md:` prefix for ≥768px (tablet/desktop). Mobile-first.

Since the codebase uses primarily inline styles (not Tailwind classes), responsive changes are implemented via CSS media queries added to `globals.css` using CSS classes, and via conditional inline styles using `useIsMobile()` hook.

**`useIsMobile` hook:**
```ts
// lib/hooks/use-is-mobile.ts
function useIsMobile() {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return isMobile;
}
```

Used in components with lots of inline styles where CSS-only changes aren't clean. CSS media queries used in globals.css for global layout rules.

---

## Files requiring responsive updates

| File | Change type |
|------|-------------|
| `web/app/globals.css` | Safe area CSS vars, `.board` mobile columns, `body` mobile padding |
| `web/app/layout.tsx` | Add viewport meta (if not already present in Next.js default) |
| `web/components/shared/app-shell.tsx` | Show/hide sidebar vs bottom nav |
| `web/components/shared/sidebar.tsx` | Add `display: none` on mobile (via CSS class) |
| `web/components/shared/bottom-nav.tsx` | **New file** — bottom tab bar |
| `web/lib/hooks/use-is-mobile.ts` | **New file** — mobile detection hook |
| `web/components/library/library-page.tsx` | Padding, search font size, FAB position |
| `web/components/chat/chat-panel.tsx` | Input bar safe area padding |
| `web/components/document/document-detail-page.tsx` | Vertical stacking on mobile |
| `web/components/search/search-page.tsx` | Padding adjustments |
| `web/components/graph/graph-page.tsx` | Entity panel → bottom sheet on mobile |
