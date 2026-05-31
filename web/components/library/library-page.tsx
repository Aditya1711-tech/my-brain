"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { createClient } from "@/lib/supabase/client";
import { Loader2, Plus, Upload, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { Dropzone } from "@/components/upload/dropzone";
import { useRealtimeDocuments } from "@/lib/hooks/use-realtime-documents";

// ── Skeleton card ────────────────────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div
      style={{
        borderRadius: 12,
        overflow: "hidden",
        background: "var(--bg-elevated)",
        border: "1px solid var(--border-faint)",
      }}
    >
      {/* Thumbnail skeleton */}
      <div className="k-shimmer" style={{ aspectRatio: "3 / 4", width: "100%" }} />
      {/* Footer skeleton */}
      <div style={{ padding: "9px 12px 11px" }}>
        <div className="k-shimmer" style={{ height: 8, width: "40%", borderRadius: 4, marginBottom: 6 }} />
        <div className="k-shimmer" style={{ height: 12, width: "85%", borderRadius: 4, marginBottom: 4 }} />
        <div className="k-shimmer" style={{ height: 12, width: "60%", borderRadius: 4 }} />
      </div>
    </div>
  );
}

interface DocumentItem {
  id: string;
  original_filename: string;
  file_type: string;
  status: string;
  doc_type: string | null;
  created_at: string;
}

interface SearchChip {
  facet: string;
  value: string;
  display: string;
}

const STAGE_LABELS: Record<string, string> = {
  uploaded: "Queued",
  extracting_text: "Extracting text",
  classified: "Classifying",
  schema_built: "Building schema",
  extracted: "Extracting fields",
  verified: "Verifying",
  integrated: "Integrating",
  vectorized: "Vectorizing",
  ready: "Ready",
  failed: "Failed",
};

// Document type palette
const DOC_TYPE_COLOR: Record<string, string> = {
  pdf:  "var(--trove-clay-500, #A0341D)",
  img:  "#6B4FA0",
  doc:  "var(--trove-teal-500, #1B4D52)",
  csv:  "var(--trove-stone-500, #6C6B62)",
  xlsx: "var(--trove-sage-500, #2D6A4F)",
  pptx: "var(--trove-amber-500, #B8821E)",
  txt:  "var(--trove-stone-400, #97968D)",
};

// Facet chip styles — inline design tokens
const FACET_STYLES: Record<string, { bg: string; border: string; color: string; facetColor: string }> = {
  file_type: { bg: "var(--trove-teal-50)",   border: "var(--trove-teal-100)",   color: "var(--trove-teal-700)",   facetColor: "var(--trove-teal-400)" },
  doc_type:  { bg: "#ECE6F5",                 border: "#C9BBE0",                 color: "#43317A",                  facetColor: "#6B4FA0" },
  domain:    { bg: "var(--trove-sage-50)",    border: "var(--trove-sage-200)",   color: "var(--trove-sage-700)",   facetColor: "var(--trove-sage-500)" },
  entity:    { bg: "#ECE6F5",                 border: "#C9BBE0",                 color: "#43317A",                  facetColor: "#6B4FA0" },
  folder:    { bg: "var(--trove-stone-100)", border: "var(--trove-stone-300)", color: "var(--trove-stone-700)", facetColor: "var(--trove-stone-500)" },
  tag:       { bg: "#FBEAE5",                 border: "#F0C9BC",                 color: "var(--trove-clay-700)",   facetColor: "var(--trove-clay-500)" },
  relation:  { bg: "var(--trove-teal-50)",   border: "var(--trove-teal-100)",   color: "var(--trove-teal-700)",   facetColor: "var(--trove-teal-400)" },
  content:   { bg: "var(--trove-stone-100)", border: "var(--trove-stone-200)", color: "var(--trove-stone-700)", facetColor: "var(--trove-stone-500)" },
};

// ── Sub-components ──────────────────────────────────────────────────────────

/** Minimal paper-ish document thumbnail — fills card edge-to-edge */
function PaperThumb({ lines = 10, fileType }: { lines?: number; fileType: string }) {
  const color = DOC_TYPE_COLOR[fileType] ?? "var(--trove-teal-500)";
  return (
    <div
      style={{
        position: "relative",
        background: "#EDEAE2",
        aspectRatio: "3 / 4",
        overflow: "hidden",
        padding: "16px 16px 12px",
      }}
    >
      {/* dog-ear */}
      <div
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          width: 24,
          height: 24,
          background: "rgba(0,0,0,0.07)",
          clipPath: "polygon(100% 0, 0 0, 100% 100%)",
        }}
      />
      {/* header row */}
      <div className="k-row" style={{ gap: 6, marginBottom: 14 }}>
        <div style={{ width: 12, height: 12, borderRadius: 3, background: color, opacity: 0.65 }} />
        <div style={{ height: 3.5, width: "42%", borderRadius: 2, background: "#1A1816", opacity: 0.18 }} />
      </div>
      {/* body lines */}
      <div style={{ display: "flex", flexDirection: "column", gap: 5.5 }}>
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            style={{
              height: 2.5,
              borderRadius: 2,
              background: "#1A1816",
              opacity: 0.11,
              width: `${[92, 78, 88, 64, 84, 72, 90, 58, 80, 70, 86][i % 11]}%`,
            }}
          />
        ))}
      </div>
    </div>
  );
}

/** Status pill with dot */
function StatusPill({ status, stageLabel }: { status: string; stageLabel?: string }) {
  const configs = {
    ready:      { bg: "var(--status-ready-bg)",      fg: "var(--status-ready-fg)",      dot: "var(--status-ready-dot)" },
    failed:     { bg: "var(--status-error-bg)",      fg: "var(--status-error-fg)",      dot: "var(--status-error-dot)" },
    uploaded:   { bg: "rgba(108,107,98,0.14)",       fg: "var(--fg-muted)",             dot: "var(--fg-subtle)" },
    processing: { bg: "var(--status-processing-bg)", fg: "var(--status-processing-fg)", dot: "var(--status-processing-dot)" },
  };
  const key = status === "ready" ? "ready"
    : status === "failed" ? "failed"
    : status === "uploaded" ? "uploaded"
    : "processing";
  const cfg = configs[key];
  const label = status === "ready" ? "Ready"
    : status === "failed" ? "Failed"
    : status === "uploaded" ? "Queued"
    : stageLabel ?? "Processing";

  return (
    <span
      aria-label={label}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 8px",
        borderRadius: 999,
        background: cfg.bg,
        color: cfg.fg,
        fontFamily: "var(--trove-sans, sans-serif)",
        fontSize: 11.5,
        fontWeight: 500,
        whiteSpace: "nowrap",
      }}
    >
      {key === "processing" ? (
        <Loader2
          aria-hidden="true"
          size={10}
          strokeWidth={2}
          style={{ animation: "k-spin 1.2s linear infinite", flexShrink: 0 }}
        />
      ) : (
        <span
          aria-hidden="true"
          className={key === "uploaded" ? "k-pulse" : ""}
          style={{
            width: 5,
            height: 5,
            borderRadius: 999,
            background: cfg.dot,
            flexShrink: 0,
            display: "inline-block",
          }}
        />
      )}
      {label}
    </span>
  );
}

/** Real thumbnail — natural height, fills card edge-to-edge */
function DocThumbnail({ docId, fileType }: { docId: string; fileType: string }) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);

  if (failed) return <PaperThumb fileType={fileType} />;

  return (
    <div style={{ background: "#EDEAE2", minHeight: loaded ? 0 : 160 }}>
      <img
        src={`/api/documents/${docId}/thumbnail`}
        alt=""
        onLoad={() => setLoaded(true)}
        onError={() => setFailed(true)}
        style={{ width: "100%", height: "auto", display: "block" }}
      />
    </div>
  );
}

/** Individual document card */
function DocumentCard({ doc, onClick }: { doc: DocumentItem; onClick: () => void }) {
  const isReady = doc.status === "ready";

  return (
    <div
      onClick={onClick}
      className="doc-card"
      style={{
        borderRadius: 12,
        overflow: "hidden",
        cursor: "pointer",
        background: "var(--bg-elevated)",
        border: "1px solid var(--border-faint)",
        transition: "transform 200ms ease, border-color 140ms ease, box-shadow 200ms ease",
      }}
    >
      {/* Thumbnail — edge-to-edge, natural height */}
      <DocThumbnail docId={doc.id} fileType={doc.file_type} />

      {/* Footer — type + name only */}
      <div style={{ padding: "9px 12px 11px" }}>
        {doc.doc_type && (
          <div style={{
            fontFamily: "var(--trove-mono, monospace)",
            fontSize: 9,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--fg-subtle)",
            marginBottom: 3,
          }}>
            {doc.doc_type.replace(/_/g, " ")}
          </div>
        )}
        <div style={{
          fontSize: 13,
          fontWeight: 450,
          color: "var(--fg)",
          lineHeight: 1.35,
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}>
          {doc.original_filename.replace(/\.[^/.]+$/, "")}
        </div>

        {/* Status only for non-ready docs */}
        {!isReady && (
          <div style={{ marginTop: 7 }}>
            <StatusPill status={doc.status} stageLabel={STAGE_LABELS[doc.status]} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── FAB (floating upload button) ───────────────────────────────────────────
function Fab({ onClick }: { onClick: () => void }) {
  const [hover, setHover] = useState(false);
  const [press, setPress] = useState(false);
  return (
    <button
      aria-label="Add a document"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setPress(false); }}
      onMouseDown={() => setPress(true)}
      onMouseUp={() => setPress(false)}
      style={{
        position: "fixed",
        right: 32,
        bottom: 32,
        zIndex: 40,
        display: "inline-flex",
        alignItems: "center",
        gap: 10,
        height: 56,
        padding: hover ? "0 22px 0 18px" : "0 18px",
        borderRadius: 999,
        background: "var(--accent)",
        color: "var(--fg-on-accent)",
        border: 0,
        cursor: "pointer",
        boxShadow: hover
          ? "0 12px 32px -8px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.06) inset"
          : "0 8px 24px -8px rgba(0,0,0,0.5)",
        transform: press ? "translateY(1px)" : hover ? "translateY(-1px)" : "none",
        transition: "all var(--trove-dur-base, 220ms) var(--trove-ease-out, ease-out)",
        fontFamily: "var(--trove-sans, sans-serif)",
        fontSize: 14,
        fontWeight: 600,
      }}
    >
      <Plus size={22} strokeWidth={2} />
      <span
        style={{
          maxWidth: hover ? 120 : 0,
          overflow: "hidden",
          whiteSpace: "nowrap",
          opacity: hover ? 1 : 0,
          transition: "max-width var(--trove-dur-base, 220ms) var(--trove-ease-out, ease-out), opacity var(--trove-dur-fast, 140ms)",
        }}
      >
        Add to trove
      </span>
    </button>
  );
}

// ── Upload dialog ──────────────────────────────────────────────────────────
function UploadDialog({
  open,
  onClose,
  onComplete,
}: {
  open: boolean;
  onClose: () => void;
  onComplete: () => void;
}) {
  // Escape key to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 70,
        background: "color-mix(in srgb, var(--bg-sunken) 72%, transparent)",
        backdropFilter: "blur(6px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        animation: "k-overlay-in 160ms var(--trove-ease-out, ease-out)",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(560px, 100%)",
          background: "var(--bg-elevated)",
          border: "1px solid var(--border)",
          borderRadius: 18,
          boxShadow: "var(--trove-shadow-lg)",
          overflow: "hidden",
          animation: "k-sheet-in 220ms var(--trove-ease-out, ease-out)",
        }}
      >
        {/* Header */}
        <div
          className="k-row"
          style={{
            justifyContent: "space-between",
            padding: "16px 18px",
            borderBottom: "1px solid var(--border-faint)",
          }}
        >
          <span
            style={{
              fontFamily: "var(--trove-serif, Georgia, serif)",
              fontStyle: "italic",
              fontSize: 20,
              color: "var(--fg-strong)",
            }}
          >
            Add to trove
          </span>
          <button
            aria-label="Close upload dialog"
            onClick={onClose}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--bg-subtle)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "none"; }}
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--fg-muted)",
              border: 0,
              background: "none",
              cursor: "pointer",
              transition: "background var(--trove-dur-fast, 140ms)",
            }}
          >
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: 18 }}>
          <Dropzone onUploadComplete={() => { onComplete(); onClose(); }} />
          <p
            style={{
              fontFamily: "var(--trove-sans, sans-serif)",
              fontSize: 11.5,
              color: "var(--fg-subtle)",
              textAlign: "center",
              marginTop: 12,
            }}
          >
            Encrypted in transit &amp; at rest. Your library, your call.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Search header ──────────────────────────────────────────────────────────
function BoardSearchHeader({
  query,
  setQuery,
  scrolled,
  chips,
  removeChip,
  onSearch,
  searchLoading,
}: {
  query: string;
  setQuery: (q: string) => void;
  scrolled: boolean;
  chips: SearchChip[];
  removeChip: (i: number) => void;
  onSearch: (chips: SearchChip[], term: string) => void;
  searchLoading: boolean;
}) {
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const active = focused || query.length > 0 || chips.length > 0;

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && query.trim()) {
      onSearch(chips, query.trim());
      setQuery("");
    } else if (e.key === "Backspace" && query === "" && chips.length > 0) {
      removeChip(chips.length - 1);
    }
  };

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 20,
        padding: active ? "22px 40px 18px" : "40px 40px 28px",
        background: scrolled
          ? "color-mix(in srgb, var(--bg-canvas) 86%, transparent)"
          : "transparent",
        backdropFilter: scrolled ? "blur(14px) saturate(120%)" : "none",
        borderBottom: scrolled ? "1px solid var(--border-faint)" : "1px solid transparent",
        transition: "padding 220ms var(--trove-ease-out, ease-out), background 220ms, border-color 220ms",
      }}
    >
      {!active ? (
        <button
          onClick={() => { setFocused(true); setTimeout(() => inputRef.current?.focus(), 0); }}
          style={{
            fontFamily: "var(--trove-serif, Georgia, serif)",
            fontStyle: "italic",
            fontWeight: 400,
            fontSize: 60,
            lineHeight: 1.0,
            letterSpacing: "-0.02em",
            color: "var(--fg-subtle)",
            textAlign: "left",
            display: "block",
            background: "none",
            border: 0,
            cursor: "text",
            padding: 0,
          }}
        >
          Search your trove…
        </button>
      ) : (
        <div className="k-fade-in" style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 44, flexWrap: "wrap" }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--fg-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
          </svg>

          {/* Active filter chips */}
          {chips.map((chip, i) => {
            const s = FACET_STYLES[chip.facet] ?? FACET_STYLES.content;
            return (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 rounded-full text-xs font-medium"
                style={{ padding: "4px 4px 4px 10px", background: s.bg, border: `1px solid ${s.border}`, color: s.color, flexShrink: 0 }}
              >
                <span style={{ fontFamily: "var(--font-geist-mono, monospace)", fontSize: 10, color: s.facetColor }}>
                  {chip.facet}
                </span>
                {chip.display}
                <button
                  onClick={() => removeChip(i)}
                  className="inline-flex items-center justify-center rounded-full"
                  style={{ width: 18, height: 18, color: "var(--trove-stone-400)", border: 0, background: "none", cursor: "pointer", padding: 0 }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "rgba(0,0,0,0.06)"; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                >
                  <X size={10} />
                </button>
              </span>
            );
          })}

          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={handleKeyDown}
            placeholder={chips.length > 0 ? "Add another filter…" : "Search across everything…"}
            style={{
              all: "unset",
              flex: 1,
              minWidth: 180,
              fontFamily: "var(--trove-serif, Georgia, serif)",
              fontStyle: "italic",
              fontSize: 32,
              lineHeight: 1.2,
              color: "var(--fg-strong)",
              letterSpacing: "-0.01em",
            }}
          />

          {searchLoading && (
            <Loader2
              size={16}
              style={{ color: "var(--trove-teal-400)", animation: "k-spin 1.2s linear infinite", flexShrink: 0 }}
            />
          )}
        </div>
      )}
    </header>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────
function EmptyState({ onUpload }: { onUpload: () => void }) {
  const [press, setPress] = useState(false);
  const [hover, setHover] = useState(false);
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 16,
        padding: "80px 0",
        textAlign: "center",
      }}
    >
      <div
        style={{
          width: 72,
          height: 72,
          borderRadius: 20,
          background: "var(--accent-soft)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--accent-ink)",
        }}
      >
        <Upload size={32} strokeWidth={1.5} />
      </div>
      <h2
        style={{
          fontFamily: "var(--trove-serif, Georgia, serif)",
          fontStyle: "italic",
          fontWeight: 400,
          fontSize: 36,
          color: "var(--fg-strong)",
          letterSpacing: "-0.015em",
        }}
      >
        Drop your first document.
      </h2>
      <p style={{ fontFamily: "var(--trove-sans, sans-serif)", fontSize: 16, color: "var(--fg-muted)" }}>
        Trove handles the rest.
      </p>
      <button
        onClick={onUpload}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => { setHover(false); setPress(false); }}
        onMouseDown={() => setPress(true)}
        onMouseUp={() => setPress(false)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "10px 20px",
          borderRadius: 999,
          background: hover ? "var(--accent-hover)" : "var(--accent)",
          color: "var(--fg-on-accent)",
          border: 0,
          cursor: "pointer",
          fontFamily: "var(--trove-sans, sans-serif)",
          fontSize: 14,
          fontWeight: 600,
          marginTop: 8,
          transform: press ? "scale(0.97)" : hover ? "translateY(-1px)" : "none",
          boxShadow: hover && !press ? "0 6px 20px -6px rgba(0,0,0,0.4)" : "none",
          transition: "background var(--trove-dur-fast, 140ms), transform var(--trove-dur-fast, 140ms), box-shadow var(--trove-dur-fast, 140ms)",
        }}
      >
        <Plus size={16} strokeWidth={2.5} />
        Add to trove
      </button>
      <p style={{ fontFamily: "var(--trove-sans, sans-serif)", fontSize: 12, color: "var(--fg-subtle)", marginTop: 4 }}>
        PDF · images · DOCX · XLSX · PPTX · CSV · TXT
      </p>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────
export function LibraryPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [scrolled, setScrolled] = useState(false);
  const [chips, setChips] = useState<SearchChip[]>([]);
  const [searchResults, setSearchResults] = useState<DocumentItem[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const router = useRouter();

  const loadDocuments = useCallback(async () => {
    const supabase = createClient();
    const { data } = await supabase
      .from("documents")
      .select("id, original_filename, file_type, status, doc_type, created_at")
      .is("deleted_at", null)
      .order("created_at", { ascending: false });

    if (data) setDocuments(data);
    setLoading(false);
  }, []);

  useEffect(() => {
    loadDocuments(); // eslint-disable-line react-hooks/set-state-in-effect -- initial data fetch
  }, [loadDocuments]);

  const handleInsert = useCallback((doc: DocumentItem) => {
    setDocuments((prev) => {
      if (prev.some((d) => d.id === doc.id)) return prev;
      return [doc, ...prev];
    });
  }, []);

  const handleUpdate = useCallback((doc: DocumentItem) => {
    setDocuments((prev) => prev.map((d) => (d.id === doc.id ? { ...d, ...doc } : d)));
  }, []);

  useRealtimeDocuments({ onInsert: handleInsert, onUpdate: handleUpdate });

  const runSearch = useCallback(async (searchChips: SearchChip[], newTerm?: string) => {
    setSearchLoading(true);
    try {
      const res = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          term: newTerm ?? null,
          chips: searchChips.map((c) => ({ facet: c.facet, value: c.value, display: c.display })),
        }),
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.chip) {
        const newChip: SearchChip = data.chip;
        setChips((prev) => {
          const exists = prev.some((c) => c.facet === newChip.facet && c.value === newChip.value);
          return exists ? prev : [...prev, newChip];
        });
      }
      setSearchResults(data.documents ?? []);
      setSearched(true);
    } finally {
      setSearchLoading(false);
    }
  }, []);

  const removeChip = useCallback((index: number) => {
    const newChips = chips.filter((_, i) => i !== index);
    setChips(newChips);
    if (newChips.length > 0) {
      runSearch(newChips);
    } else {
      setSearched(false);
      setSearchResults([]);
    }
  }, [chips, runSearch]);

  const displayDocs = searched ? searchResults : documents;

  if (loading) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading your library"
        style={{ height: "100%", overflowY: "auto" }}
      >
        {/* Mimic the sticky header area */}
        <div style={{ padding: "40px 40px 28px" }}>
          <div className="k-shimmer" style={{ height: 56, width: "38%", borderRadius: 8 }} />
        </div>
        <div style={{ padding: "8px 40px 120px" }}>
          <div className="board">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="board-card">
                <SkeletonCard />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      onScroll={(e) => setScrolled((e.target as HTMLElement).scrollTop > 12)}
      style={{ height: "100%", overflowY: "auto" }}
    >
      {/* Sticky search header */}
      <BoardSearchHeader
        query={query}
        setQuery={setQuery}
        scrolled={scrolled}
        chips={chips}
        removeChip={removeChip}
        onSearch={(currentChips, term) => runSearch(currentChips, term)}
        searchLoading={searchLoading}
      />

      {/* Board content */}
      <div style={{ padding: "8px 40px 120px" }}>
        {/* No-results message after a search */}
        {searched && !searchLoading && searchResults.length === 0 && (
          <div style={{ textAlign: "center", padding: "80px 0" }}>
            <p style={{ fontFamily: "var(--trove-sans, sans-serif)", fontSize: 16, color: "var(--fg-muted)" }}>
              Nothing matches that combination.
            </p>
            {chips.length > 0 && (
              <button
                onClick={() => removeChip(chips.length - 1)}
                style={{
                  marginTop: 12,
                  fontFamily: "var(--trove-sans, sans-serif)",
                  fontSize: 14,
                  color: "var(--trove-teal-600)",
                  background: "none",
                  border: 0,
                  cursor: "pointer",
                  textDecoration: "underline",
                }}
              >
                Try removing the last filter
              </button>
            )}
          </div>
        )}

        {/* Empty library (no docs at all) */}
        {!searched && documents.length === 0 && (
          <EmptyState onUpload={() => setUploadOpen(true)} />
        )}

        {/* Document grid */}
        {displayDocs.length > 0 && (
          <div className="board">
            {displayDocs.map((doc, i) => (
              <div
                key={doc.id}
                className="board-card"
                style={{
                  animation: "k-card-in 280ms var(--trove-ease-out, ease-out) both",
                  animationDelay: `${Math.min(i * 40, 400)}ms`,
                }}
              >
                <DocumentCard
                  doc={doc}
                  onClick={() => router.push(`/document/${doc.id}`)}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* FAB */}
      <Fab onClick={() => setUploadOpen(true)} />

      {/* Upload dialog */}
      <UploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onComplete={loadDocuments}
      />
    </div>
  );
}
