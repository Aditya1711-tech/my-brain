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

const FACET_COLORS: Record<string, string> = {
  file_type: "bg-blue-100 text-blue-800",
  doc_type: "bg-purple-100 text-purple-800",
  domain: "bg-green-100 text-green-800",
  entity: "bg-orange-100 text-orange-800",
  folder: "bg-yellow-100 text-yellow-800",
  tag: "bg-pink-100 text-pink-800",
  relation: "bg-cyan-100 text-cyan-800",
  content: "bg-gray-100 text-gray-800",
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
      runSearch([], initialQuery);
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
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Search</h2>

      {/* Search input with chips */}
      <div className="rounded-lg border p-3">
        <div className="flex flex-wrap items-center gap-2">
          {chips.map((chip, i) => (
            <span
              key={i}
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${FACET_COLORS[chip.facet] ?? FACET_COLORS.content}`}
            >
              <span className="opacity-60">{chip.facet}:</span>
              {chip.display}
              <button
                onClick={() => removeChip(i)}
                className="ml-0.5 rounded-full hover:bg-black/10 p-0.5"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-2 top-2 h-4 w-4 text-muted-foreground" />
            <Input
              ref={inputRef}
              placeholder={
                chips.length > 0
                  ? "Add another filter..."
                  : "Type a search term and press Enter..."
              }
              className="border-0 pl-8 shadow-none focus-visible:ring-0"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              onKeyDown={handleKeyDown}
              autoFocus
            />
          </div>
          {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        </div>
      </div>

      {/* Results */}
      {searched && documents.length === 0 && (
        <div className="text-center py-12">
          <p className="text-muted-foreground">No documents found</p>
          {chips.length > 0 && (
            <button
              onClick={() => removeChip(chips.length - 1)}
              className="mt-2 text-sm text-blue-600 hover:underline"
            >
              Try removing the last filter
            </button>
          )}
        </div>
      )}

      {documents.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="rounded-lg border p-4 hover:bg-accent/50 transition-colors cursor-pointer"
              onClick={() => router.push(`/document/${doc.id}`)}
            >
              <p className="font-medium text-sm truncate">
                {doc.original_filename}
              </p>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-xs text-muted-foreground uppercase">
                  {doc.file_type}
                </span>
                <StatusBadge status={doc.status} />
              </div>
              {doc.doc_type && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {doc.doc_type.replace(/_/g, " ")}
                </p>
              )}
              {doc.summary && (
                <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
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
  const colors: Record<string, string> = {
    uploaded: "bg-yellow-100 text-yellow-800",
    ready: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };
  const color = colors[status] ?? "bg-blue-100 text-blue-800";

  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}
