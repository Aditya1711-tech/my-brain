"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { Search, X, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";

interface SearchChip {
  facet: string;
  value: string;
  display: string;
}

interface DocumentResult {
  id: string;
  original_filename: string;
  file_type: string;
  status: string;
  doc_type: string | null;
  domain: string | null;
  summary: string | null;
  created_at: string;
}

// Trove facet chip styles — inline styles to use design tokens
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

export function SearchPage({ initialQuery }: { initialQuery?: string }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [chips, setChips] = useState<SearchChip[]>([]);
  const [term, setTerm] = useState("");
  const [documents, setDocuments] = useState<DocumentResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const runSearch = useCallback(
    async (searchChips: SearchChip[], newTerm?: string) => {
      setLoading(true);
      try {
        const res = await fetch("/api/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            term: newTerm ?? null,
            chips: searchChips.map((c) => ({
              facet: c.facet,
              value: c.value,
              display: c.display,
            })),
          }),
        });

        if (!res.ok) return;

        const data = await res.json();

        // If a new chip was resolved, add it
        if (data.chip) {
          const newChip: SearchChip = data.chip;
          setChips((prev) => [...prev, newChip]);
        }

        setDocuments(data.documents ?? []);
        setSearched(true);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  // Handle initial query from URL
  useEffect(() => {
    if (initialQuery) {
      runSearch([], initialQuery); // eslint-disable-line react-hooks/set-state-in-effect -- initial URL query
    }
  }, [initialQuery, runSearch]);

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && term.trim()) {
      runSearch(chips, term.trim());
      setTerm("");
    } else if (e.key === "Backspace" && term === "" && chips.length > 0) {
      // Remove last chip
      const newChips = chips.slice(0, -1);
      setChips(newChips);
      if (newChips.length > 0) {
        runSearch(newChips);
      } else {
        setDocuments([]);
        setSearched(false);
      }
    }
  };

  const removeChip = (index: number) => {
    const newChips = chips.filter((_, i) => i !== index);
    setChips(newChips);
    if (newChips.length > 0) {
      runSearch(newChips);
    } else {
      setDocuments([]);
      setSearched(false);
    }
  };

  return (
    <div style={{ padding: "40px 40px 80px", display: "flex", flexDirection: "column", gap: 24 }}>
      <h2
        style={{
          fontFamily: "var(--trove-serif, Georgia, serif)",
          fontStyle: "italic",
          fontWeight: 400,
          fontSize: 44,
          letterSpacing: "-0.02em",
          color: "var(--fg-strong)",
        }}
      >
        Search your trove
      </h2>

      {/* Search input with chips */}
      <div
        style={{
          borderRadius: 14,
          border: "1px solid var(--border)",
          background: "var(--bg-elevated)",
          padding: 12,
        }}
      >
        <div className="flex flex-wrap items-center gap-2">
          {chips.map((chip, i) => {
            const s = FACET_STYLES[chip.facet] ?? FACET_STYLES.content;
            return (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 rounded-full text-xs font-medium"
                style={{ padding: "4px 4px 4px 10px", background: s.bg, border: `1px solid ${s.border}`, color: s.color }}
              >
                <span style={{ fontFamily: "var(--font-geist-mono, monospace)", fontSize: 10, color: s.facetColor }}>
                  {chip.facet}
                </span>
                {chip.display}
                <button
                  onClick={() => removeChip(i)}
                  className="inline-flex items-center justify-center rounded-full"
                  style={{ width: 18, height: 18, color: "var(--trove-stone-400)" }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "rgba(0,0,0,0.06)"; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </span>
            );
          })}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              ref={inputRef}
              placeholder={chips.length > 0 ? "Add another filter…" : "Ask anything about your trove…"}
              className="border-0 pl-8 shadow-none focus-visible:ring-0 text-sm"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              onKeyDown={handleKeyDown}
              autoFocus
            />
          </div>
          {loading && <Loader2 className="h-4 w-4 animate-spin" style={{ color: "var(--trove-teal-400)" }} />}
        </div>
      </div>

      {/* Empty results */}
      {searched && documents.length === 0 && (
        <div className="text-center py-12">
          <p className="text-muted-foreground text-sm">Nothing matches that combination.</p>
          {chips.length > 0 && (
            <button
              onClick={() => removeChip(chips.length - 1)}
              className="mt-2 text-sm hover:underline"
              style={{ color: "var(--trove-teal-600)" }}
            >
              Try removing the last filter
            </button>
          )}
        </div>
      )}

      {/* Results grid */}
      {documents.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="rounded-[10px] border bg-card cursor-pointer transition-shadow"
              style={{ padding: "14px 16px 12px" }}
              onClick={() => router.push(`/document/${doc.id}`)}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.boxShadow = "var(--trove-shadow-md)"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.boxShadow = "none"; }}
            >
              <p className="font-medium text-sm truncate" style={{ color: "var(--trove-stone-900)" }}>
                {doc.original_filename}
              </p>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-[11px] font-mono uppercase tracking-wide" style={{ color: "var(--trove-stone-400)" }}>
                  {doc.file_type}
                </span>
                <StatusBadge status={doc.status} />
              </div>
              {doc.doc_type && (
                <p className="mt-1.5 text-[12px]" style={{ color: "var(--trove-stone-500)" }}>
                  {doc.doc_type.replace(/_/g, " ")}
                </p>
              )}
              {doc.summary && (
                <p className="mt-1 text-xs line-clamp-2" style={{ color: "var(--trove-stone-500)" }}>
                  {doc.summary}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, { bg: string; color: string }> = {
    uploaded:   { bg: "var(--trove-stone-100)",  color: "var(--trove-stone-500)" },
    ready:      { bg: "var(--trove-sage-50)",    color: "var(--trove-sage-700)" },
    failed:     { bg: "var(--trove-clay-50)",    color: "var(--trove-clay-700)" },
  };
  const s = styles[status] ?? { bg: "var(--trove-amber-50)", color: "var(--trove-amber-700)" };

  return (
    <span
      className="rounded-full px-2 py-0.5 text-[11px] font-medium"
      style={{ background: s.bg, color: s.color }}
    >
      {status}
    </span>
  );
}
