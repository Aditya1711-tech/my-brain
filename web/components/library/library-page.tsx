"use client";

import { useCallback, useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Upload, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { Dropzone } from "@/components/upload/dropzone";
import { useRealtimeDocuments } from "@/lib/hooks/use-realtime-documents";

interface DocumentItem {
  id: string;
  original_filename: string;
  file_type: string;
  status: string;
  doc_type: string | null;
  created_at: string;
}

export function LibraryPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);

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

  // Live updates via Supabase Realtime
  const handleInsert = useCallback(
    (doc: DocumentItem) => {
      setDocuments((prev) => {
        if (prev.some((d) => d.id === doc.id)) return prev;
        return [doc, ...prev];
      });
    },
    [],
  );

  const handleUpdate = useCallback(
    (doc: DocumentItem) => {
      setDocuments((prev) =>
        prev.map((d) => (d.id === doc.id ? { ...d, ...doc } : d)),
      );
    },
    [],
  );

  useRealtimeDocuments({ onInsert: handleInsert, onUpdate: handleUpdate });

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center">
        <EmptyState />
        <div className="mt-8 w-full max-w-lg">
          <Dropzone onUploadComplete={loadDocuments} />
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">Library</h2>
      </div>
      <div className="mb-6">
        <Dropzone onUploadComplete={loadDocuments} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {documents.map((doc) => (
          <DocumentCard key={doc.id} doc={doc} />
        ))}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center">
      <div className="mx-auto rounded-full bg-muted p-6 mb-4 w-fit">
        <Upload className="h-10 w-10 text-muted-foreground" />
      </div>
      <h2 className="text-xl font-semibold">Welcome to My Brain</h2>
      <p className="mt-2 max-w-sm mx-auto text-muted-foreground">
        Upload your first document to get started. We&apos;ll automatically extract fields,
        build your knowledge graph, and enable search and chat across all your documents.
      </p>
      <p className="mt-3 text-xs text-muted-foreground">
        Supports PDF, images, DOCX, XLSX, PPTX, CSV, and TXT
      </p>
    </div>
  );
}

const PIPELINE_STAGES = [
  "uploaded",
  "extracting_text",
  "classified",
  "schema_built",
  "extracted",
  "verified",
  "integrated",
  "vectorized",
  "ready",
];

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

function DocumentCard({ doc }: { doc: DocumentItem }) {
  const router = useRouter();
  const isProcessing = !["ready", "failed", "uploaded"].includes(doc.status);
  const isReady = doc.status === "ready";
  const isFailed = doc.status === "failed";
  const currentIdx = PIPELINE_STAGES.indexOf(doc.status);
  const totalStages = PIPELINE_STAGES.length - 1; // exclude "ready" from progress
  const progress = isReady ? 100 : Math.max(0, (currentIdx / totalStages) * 100);

  return (
    <div
      className="rounded-lg border p-4 hover:bg-accent/50 transition-colors cursor-pointer group"
      onClick={() => router.push(`/document/${doc.id}`)}
    >
      <p className="font-medium text-sm truncate">{doc.original_filename}</p>

      {/* Pipeline progress bar */}
      {(isProcessing || isReady) && (
        <div className="mt-2 space-y-1">
          <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                isReady ? "bg-green-500" : "bg-blue-500"
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex items-center gap-1.5">
            {isProcessing && (
              <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
            )}
            {isReady && (
              <CheckCircle2 className="h-3 w-3 text-green-500" />
            )}
            <span className="text-xs text-muted-foreground">
              {STAGE_LABELS[doc.status] ?? doc.status}
            </span>
          </div>
        </div>
      )}

      {isFailed && (
        <div className="mt-2 flex items-center gap-1.5">
          <XCircle className="h-3 w-3 text-red-500" />
          <span className="text-xs text-red-600">Failed</span>
        </div>
      )}

      {doc.status === "uploaded" && (
        <div className="mt-2 flex items-center gap-1.5">
          <div className="h-3 w-3 rounded-full bg-yellow-400 animate-pulse" />
          <span className="text-xs text-muted-foreground">Queued</span>
        </div>
      )}

      <div className="mt-2 flex items-center gap-2">
        <span className="text-xs text-muted-foreground uppercase">{doc.file_type}</span>
        {doc.doc_type && (
          <span className="text-xs text-muted-foreground">
            {doc.doc_type.replace(/_/g, " ")}
          </span>
        )}
      </div>
    </div>
  );
}
