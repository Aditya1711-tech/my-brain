"use client";

import { useCallback, useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Upload } from "lucide-react";
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
    loadDocuments();
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
      <h2 className="text-xl font-semibold">Your library is empty</h2>
      <p className="mt-2 max-w-sm mx-auto text-muted-foreground">
        Drop files below or click to browse. We support PDF, images, DOCX, XLSX, PPTX, CSV, and TXT.
      </p>
    </div>
  );
}

function DocumentCard({ doc }: { doc: DocumentItem }) {
  const statusColors: Record<string, string> = {
    uploaded: "bg-yellow-100 text-yellow-800",
    extracting_text: "bg-blue-100 text-blue-800",
    classified: "bg-blue-100 text-blue-800",
    schema_built: "bg-blue-100 text-blue-800",
    extracted: "bg-blue-100 text-blue-800",
    verified: "bg-blue-100 text-blue-800",
    integrated: "bg-blue-100 text-blue-800",
    vectorized: "bg-blue-100 text-blue-800",
    ready: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };

  return (
    <div className="rounded-lg border p-4 hover:bg-accent/50 transition-colors cursor-pointer">
      <p className="font-medium text-sm truncate">{doc.original_filename}</p>
      <div className="mt-2 flex items-center gap-2">
        <span className="text-xs text-muted-foreground uppercase">{doc.file_type}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[doc.status] ?? "bg-gray-100 text-gray-800"}`}
        >
          {doc.status}
        </span>
      </div>
      {doc.doc_type && (
        <p className="mt-1 text-xs text-muted-foreground">{doc.doc_type.replace(/_/g, " ")}</p>
      )}
    </div>
  );
}
