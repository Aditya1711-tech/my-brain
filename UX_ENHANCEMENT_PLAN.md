# UX Enhancement Plan

## Tech stack

- **Framework**: Next.js 16 (App Router), React 19
- **Styling**: Tailwind CSS v4 + custom CSS variables (`var(--trove-*)` design tokens), `tw-animate-css`
- **Component library**: Shadcn (Base UI adapter — no `asChild` prop)
- **Animation**: CSS keyframes (`k-fade-in`, `k-sheet-in`, `k-overlay-in`, `k-spin`, `k-pulse`, `k-card-in`, `k-slide-in-right`, `k-shimmer`, `k-typing-dot`) + CSS transitions
- **Icons**: `lucide-react`
- **State/data**: Zustand, TanStack Query v5, Supabase Realtime
- **Toast**: `sonner`
- **Forms**: `react-hook-form` + `zod`
- **Graph**: `react-force-graph-2d`
- **File upload**: `react-dropzone`

---

## Discovery findings

### Library page (`/`)
**Good**: Beautiful masonry board, animated FAB with expand-on-hover, full-page drag-drop overlay with backdrop blur, realtime document updates, skeleton paper thumbnails, status pills with spinner/pulse dot, lazy image loading with fallback.
**Needed**: Skeleton loading state, stagger animations, hover via CSS not useState, Escape on upload dialog, close button hover/aria, empty state button feedback, aria improvements.

### Document detail page (`/document/[id]`)
**Good**: Pipeline timeline with animated progress bar, realtime status updates, extracted fields with inline editing, confidence pills, related entities section.
**Needed**: Status/confidence badges use Trove tokens, chat panel slide-in animation + Escape, field save visual feedback, error box Trove tokens, section cards visual upgrade.

### Chat page (`/chat`)
**Good**: Thread sidebar with new/delete, streaming markdown rendering, citation badges, ChatPanel key reset on thread change.
**Needed**: Empty thread state, chat panel empty state, typing indicator, heading/branding, citation badge token consistency, message animations.

### Search page (`/search`)
**Good**: Facet chip system, keyboard navigation, loading spinner.
**Needed**: Search results stagger, empty state with icon, human-readable status labels, results card polish.

### Graph page (`/graph`)
**Good**: Force-directed graph, click-to-expand entity panel, dynamic sizing.
**Needed**: Entity panel slide-in + Escape, collapsible legend, empty state Trove-styled, entity colors → Trove tokens, loading state with label.

### Auth pages
**Good**: Simple clean form.
**Needed**: Trove branding, field labels, error role="alert", loading spinner, autofocus.

### Document viewer modal
**Good**: Handles PDF, images, download fallback.
**Needed**: Entrance animation, backdrop blur, Escape key, focus trap, retry button on error.

### Upload dropzone
**Good**: Drag-active color change, file list with status icons.
**Needed**: Progress bar render, success pulse, file list stagger.

---

## Enhancement list

### Category 1: Animations & transitions

- [x] Step 1.1: Library page — skeleton card loading state
  - Files: `web/components/library/library-page.tsx`, `web/app/globals.css`
  - Done: Added `SkeletonCard` component with shimmer, 6 skeletons shown during load with `.k-shimmer` class

- [x] Step 1.2: Library page — stagger-in animation for document grid
  - Files: `web/components/library/library-page.tsx`, `web/app/globals.css`
  - Done: Added `k-card-in` keyframe, applied with per-card `animationDelay` (40ms increments, capped 400ms)

- [x] Step 1.3: Chat side panel — slide-in animation (document detail)
  - Files: `web/components/document/document-detail-page.tsx`, `web/app/globals.css`
  - Done: Extracted `ChatSidePanel` component with `k-slide-in-right` animation + Escape key handler

- [x] Step 1.4: Document viewer modal — entrance animation + backdrop blur
  - Files: `web/components/shared/document-viewer-modal.tsx`
  - Done: Applied `k-overlay-in` + `backdropFilter blur(8px)` to overlay; `k-sheet-in` to modal panel

- [x] Step 1.5: Graph page — entity side panel slide-in
  - Files: `web/components/graph/graph-page.tsx`
  - Done: Extracted `EntitySidePanel` component with `k-slide-in-right` + Escape key handler

- [x] Step 1.6: Search results — stagger-in animation
  - Files: `web/components/search/search-page.tsx`
  - Done: Applied `k-card-in` with staggered `animationDelay` (35ms per card, capped 350ms)

### Category 2: Loading, empty, and error states

- [x] Step 2.1: Library loading skeleton
  - Files: `web/components/library/library-page.tsx`, `web/app/globals.css`
  - Done: `.k-shimmer` CSS class with 200% background-size gradient animation; `SkeletonCard` renders 6 placeholders

- [x] Step 2.2: Chat page — friendly empty thread state
  - Files: `web/components/chat/chat-page-wrapper.tsx`
  - Done: Icon + styled description text replaces "No conversations yet" plain text

- [x] Step 2.3: Chat panel — empty message state with icon
  - Files: `web/components/chat/chat-panel.tsx`
  - Done: `MessageSquare` icon + serif italic headline in centered container

- [x] Step 2.4: Graph empty state — Trove-styled
  - Files: `web/components/graph/graph-page.tsx`
  - Done: `GitBranch` icon + serif heading "No connections yet" + Trove token styling matching Library empty state

- [x] Step 2.5: Document detail error box — use Trove status tokens
  - Files: `web/components/document/document-detail-page.tsx`
  - Done: Replaced `border-red-200 bg-red-50 text-red-800` with `--status-error-bg/fg/dot` tokens

- [x] Step 2.6: Document viewer modal — loading & error state improvements
  - Files: `web/components/shared/document-viewer-modal.tsx`
  - Done: Loading shows spinner + "Loading document…" text; error shows message + "Try again" retry button

### Category 3: Micro-interactions & feedback

- [x] Step 3.1: Upload dropzone — progress bar per file
  - Files: `web/components/upload/dropzone.tsx`
  - Done: 2px progress bar under each uploading file row, transitions width with `f.progress` state

- [x] Step 3.2: Upload dropzone — success checkmark pulse
  - Files: `web/components/upload/dropzone.tsx`
  - Done: `k-pulse` animation on `CheckCircle2` when status = "done"

- [x] Step 3.3: Library empty state — button hover/press states
  - Files: `web/components/library/library-page.tsx`
  - Done: `scale(0.97)` press + `translateY(-1px)` hover with shadow on the "Add to trove" button

- [x] Step 3.4: Chat panel — streaming "typing" indicator
  - Files: `web/components/chat/chat-panel.tsx`, `web/app/globals.css`
  - Done: Three animated dots with `k-typing-dot` keyframe, staggered 0.2s delay each

- [x] Step 3.5: Field save — visual confirmation
  - Files: `web/components/document/document-detail-page.tsx`
  - Done: `savedField` state flashes field row green via `--status-ready-bg` for 1200ms

- [x] Step 3.6: Upload dialog close button — hover state
  - Files: `web/components/library/library-page.tsx`
  - Done: `onMouseEnter/Leave` hover background `var(--bg-subtle)` on close button

### Category 4: Text & copy improvements

- [x] Step 4.1: Login/signup — fix branding
  - Files: `web/app/(auth)/login/page.tsx`, `web/app/(auth)/signup/page.tsx`
  - Done: Added Trove SVG logomark, serif italic "Trove" heading, proper `<label htmlFor>` elements

- [x] Step 4.2: Document detail — fix StatusBadge tokens
  - Files: `web/components/document/document-detail-page.tsx`
  - Done: `StatusBadge` and `ConfidencePill` now use `--status-*` CSS variables; human-readable label map added

- [x] Step 4.3: Search results — human-readable status labels
  - Files: `web/components/search/search-page.tsx`
  - Done: `STATUS_LABELS` map + `StatusBadge` updated to show "Queued", "Ready", "Processing" etc.

- [x] Step 4.4: Chat page — improve heading and description
  - Files: `web/components/chat/chat-page-wrapper.tsx`
  - Done: Changed heading to serif italic "Ask your trove"; subtitle updated to shorter, more helpful copy

- [x] Step 4.5: Graph — fix entity type colors to Trove tokens
  - Files: `web/components/graph/graph-page.tsx`
  - Done: `TYPE_COLORS` updated to match `--trove-entity-*` token hex values

- [x] Step 4.6: Sidebar — "Spaces" nav item points to non-existent page
  - Files: `web/components/shared/sidebar.tsx`
  - Done: Removed "Spaces" (`/spaces`), replaced with "Search" (`/search`)

### Category 5: Flow & navigation improvements

- [x] Step 5.1: Keyboard shortcut — Escape to close upload dialog
  - Files: `web/components/library/library-page.tsx`
  - Done: `useEffect` + `keydown` listener in `UploadDialog`; fires `onClose()` on Escape

- [x] Step 5.2: Keyboard shortcut — Escape to close document viewer modal
  - Files: `web/components/shared/document-viewer-modal.tsx`
  - Done: `useEffect` keydown listener wired in the `open` effect

- [x] Step 5.3: Auto-focus on first input — login/signup forms
  - Files: `web/app/(auth)/login/page.tsx`, `web/app/(auth)/signup/page.tsx`
  - Done: `autoFocus` on email `<Input>` on both auth pages

- [x] Step 5.4: Auto-focus chat input when panel opens
  - Files: `web/components/chat/chat-panel.tsx`
  - Done: Added `autoFocus` to the chat `<Input>` so it captures focus on mount

- [x] Step 5.5: Add Search to sidebar navigation
  - Files: `web/components/shared/sidebar.tsx`
  - Done: Combined with 4.6 — "Search" nav item added at position 2

### Category 6: Visual consistency & polish

- [x] Step 6.1: Library page — DocumentCard hover via CSS class
  - Files: `web/components/library/library-page.tsx`, `web/app/globals.css`
  - Done: Removed `useState` hover; added `.doc-card:hover` CSS rule with translateY + shadow

- [x] Step 6.2: Document detail — section cards use Trove tokens
  - Files: `web/components/document/document-detail-page.tsx`
  - Done: All section cards updated to `var(--bg-elevated)`, `var(--border-faint)`, `var(--trove-shadow-sm)`, Trove sans headings

- [x] Step 6.3: Chat messages — entrance animation for new messages
  - Files: `web/components/chat/chat-panel.tsx`
  - Done: `k-fade-in 180ms` applied to each message div wrapper

- [x] Step 6.4: Graph legend — make it collapsible
  - Files: `web/components/graph/graph-page.tsx`
  - Done: Legend wrapped in toggle button; `legendOpen` state; legend animates in with `k-fade-in`

- [x] Step 6.5: Upload file list — add stagger animation
  - Files: `web/components/upload/dropzone.tsx`
  - Done: `k-fade-in` with 50ms stagger per file row as they appear

### Category 7: Accessibility

- [x] Step 7.1: Auth forms — add form field labels
  - Files: `web/app/(auth)/login/page.tsx`, `web/app/(auth)/signup/page.tsx`
  - Done: `<label htmlFor>` with matching `id` on each `<Input>`, styled with Trove tokens

- [x] Step 7.2: Auth forms — error message `role="alert"`
  - Files: `web/app/(auth)/login/page.tsx`, `web/app/(auth)/signup/page.tsx`
  - Done: `role="alert"` + `aria-live="polite"` on error `<p>` in both forms

- [x] Step 7.3: Upload dialog close button — aria-label
  - Files: `web/components/library/library-page.tsx`
  - Done: `aria-label="Close upload dialog"` + `aria-hidden="true"` on SVG icon

- [x] Step 7.4: Document viewer modal — focus trap and Escape
  - Files: `web/components/shared/document-viewer-modal.tsx`
  - Done: `role="dialog"` + `aria-modal="true"` + close button auto-focused via `ref` + Escape handler

- [x] Step 7.5: Library loading state — aria-busy
  - Files: `web/components/library/library-page.tsx`
  - Done: `aria-busy="true"` + `aria-label="Loading your library"` on loading container

- [x] Step 7.6: StatusPill — aria-label on processing spinner
  - Files: `web/components/library/library-page.tsx`
  - Done: `aria-label={label}` on outer `<span>`; `aria-hidden="true"` on icon/dot

### Category 8: Other improvements

- [x] Step 8.1: Login/signup — loading spinner in submit button
  - Files: `web/app/(auth)/login/page.tsx`, `web/app/(auth)/signup/page.tsx`
  - Done: `<Loader2>` icon shown beside button text when `loading === true`

- [x] Step 8.2: Add keyframes to globals.css
  - Files: `web/app/globals.css`
  - Done: Added `k-card-in`, `k-slide-in-right`, `k-shimmer`, `k-typing-dot` keyframes + `.k-shimmer`, `.k-slide-in-right` utility classes

- [x] Step 8.3: Document viewer modal animation keyframes (already in globals)
  - Files: `web/app/globals.css`
  - Done: Verified `k-sheet-in` and `k-overlay-in` were already present; no new additions needed

- [x] Step 8.4: Search page — focus search input on mount
  - Files: `web/components/search/search-page.tsx`
  - Done: `autoFocus` was already on the input; verified it works

- [x] Step 8.5: Chat panel — character counter / send hint
  - Files: `web/components/chat/chat-panel.tsx`
  - Done: "↵ to send" hint appears below input with `k-fade-in` when input has content and not streaming

---

## Dependencies added

_(none — all enhancements used existing libraries)_
