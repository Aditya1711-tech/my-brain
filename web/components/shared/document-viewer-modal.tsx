"use client";

import { useEffect, useState } from "react";
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

  useEffect(() => {
    if (!open) return;
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
  }, [open, documentId]);

  if (!open) return null;

  const isPdf = data?.mime_type === "application/pdf";
  const isImage = data?.mime_type?.startsWith("image/");
  const canEmbed = isPdf || isImage;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="flex flex-col rounded-lg border bg-card"
        style={{ width: "min(90vw, 1000px)", height: "85vh" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-4 py-3 shrink-0">
          <span className="text-sm font-medium truncate max-w-[80%]">
            {data?.filename ?? "Document Viewer"}
          </span>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground ml-2"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-hidden flex items-center justify-center">
          {loading && (
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          )}
          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
          {data && canEmbed && (
            <iframe
              src={data.url}
              title={data.filename}
              className="w-full h-full"
              style={{ border: "none" }}
            />
          )}
          {data && !canEmbed && (
            <div className="text-center space-y-3">
              <p className="text-sm text-muted-foreground">
                Preview not available for this file type.
              </p>
              <a
                href={data.url}
                download={data.filename}
                className="inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium hover:bg-muted transition-colors"
              >
                <Download className="h-4 w-4" />
                Download {data.filename}
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
