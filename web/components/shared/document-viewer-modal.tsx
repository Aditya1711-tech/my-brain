"use client";

import { useEffect, useRef, useState } from "react";
import { X, Loader2, Download } from "lucide-react";

interface DocumentViewerModalProps {
  documentId: string;
  open: boolean;
  onClose: () => void;
}

interface SignedUrlData {
  url: string;
  mime_type: string;
  filename: string;
}

export function DocumentViewerModal({ documentId, open, onClose }: DocumentViewerModalProps) {
  const [data, setData] = useState<SignedUrlData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  const loadFile = () => {
    setData(null);
    setError(null);
    setLoading(true);
    fetch(`/api/documents/${documentId}/signed-url`)
      .then((r) => {
        if (!r.ok) throw new Error("Failed to load file");
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!open) return;
    loadFile();
    // Escape key
    const handler = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    // Auto-focus close button for keyboard accessibility
    setTimeout(() => closeBtnRef.current?.focus(), 50);
    return () => document.removeEventListener("keydown", handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, documentId]);

  if (!open) return null;

  const isPdf = data?.mime_type === "application/pdf";
  const isImage = data?.mime_type?.startsWith("image/");
  const canEmbed = isPdf || isImage;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={data?.filename ?? "Document Viewer"}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 50,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.65)",
        backdropFilter: "blur(8px)",
        animation: "k-overlay-in 160ms var(--trove-ease-out, ease-out) both",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          width: "min(90vw, 1000px)",
          height: "85vh",
          display: "flex",
          flexDirection: "column",
          borderRadius: 14,
          border: "1px solid var(--border)",
          background: "var(--bg-elevated)",
          boxShadow: "var(--trove-shadow-lg)",
          animation: "k-sheet-in 220ms var(--trove-ease-out, ease-out) both",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: "1px solid var(--border-faint)",
            padding: "12px 16px",
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 500, color: "var(--fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "80%" }}>
            {data?.filename ?? "Document Viewer"}
          </span>
          <button
            ref={closeBtnRef}
            aria-label="Close document viewer"
            onClick={onClose}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--bg-subtle)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "none"; }}
            style={{
              width: 30, height: 30, borderRadius: 8, border: 0,
              background: "none", cursor: "pointer", display: "flex",
              alignItems: "center", justifyContent: "center",
              color: "var(--fg-muted)", marginLeft: 8,
              transition: "background var(--trove-dur-fast, 140ms)",
            }}
          >
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center" }}>
          {loading && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
              <Loader2 aria-hidden="true" className="h-6 w-6 animate-spin" style={{ color: "var(--fg-muted)" }} />
              <p style={{ fontSize: 13, color: "var(--fg-muted)", fontFamily: "var(--trove-sans, sans-serif)" }}>
                Loading document…
              </p>
            </div>
          )}
          {error && (
            <div style={{ textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
              <p style={{ fontSize: 13, color: "var(--status-error-fg)", fontFamily: "var(--trove-sans, sans-serif)" }}>
                {error}
              </p>
              <button
                onClick={loadFile}
                style={{
                  padding: "8px 16px",
                  borderRadius: 8,
                  border: "1px solid var(--border)",
                  background: "var(--bg-elevated)",
                  color: "var(--fg)",
                  cursor: "pointer",
                  fontSize: 13,
                  fontFamily: "var(--trove-sans, sans-serif)",
                }}
              >
                Try again
              </button>
            </div>
          )}
          {data && canEmbed && (
            <iframe
              src={data.url}
              title={data.filename}
              style={{ width: "100%", height: "100%", border: "none" }}
            />
          )}
          {data && !canEmbed && (
            <div style={{ textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
              <p style={{ fontSize: 13, color: "var(--fg-muted)", fontFamily: "var(--trove-sans, sans-serif)" }}>
                Preview not available for this file type.
              </p>
              <a
                href={data.url}
                download={data.filename}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 16px",
                  borderRadius: 8,
                  border: "1px solid var(--border)",
                  background: "var(--bg-elevated)",
                  color: "var(--fg)",
                  textDecoration: "none",
                  fontSize: 13,
                  fontFamily: "var(--trove-sans, sans-serif)",
                  fontWeight: 500,
                }}
              >
                <Download aria-hidden="true" className="h-4 w-4" />
                Download {data.filename}
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
