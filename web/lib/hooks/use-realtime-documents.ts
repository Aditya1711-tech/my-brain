"use client";

import { useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import type { RealtimePostgresChangesPayload } from "@supabase/supabase-js";

interface DocumentPayload {
  id: string;
  status: string;
  doc_type: string | null;
  original_filename: string;
  file_type: string;
  created_at: string;
  [key: string]: unknown;
}

/**
 * Subscribe to Realtime changes on the documents table.
 * Calls onInsert/onUpdate when rows change.
 */
export function useRealtimeDocuments({
  onInsert,
  onUpdate,
}: {
  onInsert?: (doc: DocumentPayload) => void;
  onUpdate?: (doc: DocumentPayload) => void;
}) {
  useEffect(() => {
    const supabase = createClient();

    const channel = supabase
      .channel("documents-realtime")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "documents" },
        (payload: RealtimePostgresChangesPayload<DocumentPayload>) => {
          if (payload.new && "id" in payload.new) {
            onInsert?.(payload.new as DocumentPayload);
          }
        },
      )
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "documents" },
        (payload: RealtimePostgresChangesPayload<DocumentPayload>) => {
          if (payload.new && "id" in payload.new) {
            onUpdate?.(payload.new as DocumentPayload);
          }
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [onInsert, onUpdate]);
}
