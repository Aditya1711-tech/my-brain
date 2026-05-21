"use client";

import { useCallback, useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  FileText,
  ExternalLink,
  CheckCircle2,
  Circle,
  XCircle,
  Loader2,
  Pencil,
  MessageSquare,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRealtimeDocuments } from "@/lib/hooks/use-realtime-documents";
import { ChatPanel } from "@/components/chat/chat-panel";

interface DocumentDetail {
  id: string;
  original_filename: string;
  file_type: string;
  mime_type: string;
  size_bytes: number;
  storage_path: string;
  status: string;
  doc_type: string | null;
  domain: string | null;
  country: string | null;
  language: string | null;
  is_scanned: boolean | null;
  is_handwritten: boolean | null;
  summary: string | null;
  created_at: string;
  updated_at: string;
  failure_reason: string | null;
}

interface ExtractedField {
  id: string;
  field_name: string;
  field_value: string | null;
  field_type: string;
  confidence: number | null;
  needs_retry: boolean;
  reasoning: string | null;
  is_entity_ref: boolean;
}

interface PipelineEvent {
  id: string;
  stage: string;
  status: string;
  duration_ms: number | null;
  created_at: string;
}

interface Entity {
  entity_id: string;
  role: string;
  canonical_name: string;
  entity_type: string;
}

const PIPELINE_STAGES = [
  { key: "text_extraction", label: "Text Extraction", status: "extracting_text" },
  { key: "classification", label: "Classification", status: "classified" },
  { key: "schema_building", label: "Schema Building", status: "schema_built" },
  { key: "extraction", label: "Field Extraction", status: "extracted" },
  { key: "verification", label: "Verification", status: "verified" },
  { key: "integration", label: "Knowledge Integration", status: "integrated" },
  { key: "vectorization", label: "Vectorization", status: "vectorized" },
];

const STATUS_ORDER = [
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

export function DocumentDetailPage({ documentId }: { documentId: string }) {
  const router = useRouter();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [fields, setFields] = useState<ExtractedField[]>([]);
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [chatOpen, setChatOpen] = useState(false);

  const loadDocument = useCallback(async () => {
    const supabase = createClient();

    const { data: docData } = await supabase
      .from("documents")
      .select("*")
      .eq("id", documentId)
      .single();

    if (docData) setDoc(docData);

    const { data: fieldsData } = await supabase
      .from("extracted_fields")
      .select("id, field_name, field_value, field_type, confidence, needs_retry, reasoning, is_entity_ref")
      .eq("document_id", documentId)
      .order("field_name");

    if (fieldsData) setFields(fieldsData);

    const { data: eventsData } = await supabase
      .from("document_pipeline_events")
      .select("id, stage, status, duration_ms, created_at")
      .eq("document_id", documentId)
      .order("created_at", { ascending: true });

    if (eventsData) setEvents(eventsData);

    // Load related entities via document_entities junction
    const { data: entityLinks } = await supabase
      .from("document_entities")
      .select("entity_id, role")
      .eq("document_id", documentId);

    if (entityLinks && entityLinks.length > 0) {
      const entityIds = entityLinks.map((l) => l.entity_id);
      const { data: entitiesData } = await supabase
        .from("entities")
        .select("id, canonical_name, entity_type")
        .in("id", entityIds);

      if (entitiesData) {
        const merged = entityLinks.map((link) => {
          const ent = entitiesData.find((e) => e.id === link.entity_id);
          return {
            entity_id: link.entity_id,
            role: link.role,
            canonical_name: ent?.canonical_name ?? "Unknown",
            entity_type: ent?.entity_type ?? "other",
          };
        });
        setEntities(merged);
      }
    }

    setLoading(false);
  }, [documentId]);

  useEffect(() => {
    loadDocument();
  }, [loadDocument]);

  // Realtime updates for this document
  const handleUpdate = useCallback(
    (updated: { id: string; status?: string }) => {
      if (updated.id === documentId) {
        loadDocument();
      }
    },
    [documentId, loadDocument],
  );

  useRealtimeDocuments({ onUpdate: handleUpdate });

  const handleSaveField = async (fieldId: string) => {
    const supabase = createClient();
    await supabase
      .from("extracted_fields")
      .update({ field_value: editValue })
      .eq("id", fieldId);

    setFields((prev) =>
      prev.map((f) => (f.id === fieldId ? { ...f, field_value: editValue } : f)),
    );
    setEditingField(null);
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">Document not found</p>
        <Button variant="outline" onClick={() => router.push("/")}>
          Back to Library
        </Button>
      </div>
    );
  }

  const currentStatusIndex = STATUS_ORDER.indexOf(doc.status);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => router.push("/")}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back
        </Button>
      </div>

      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <FileText className="h-6 w-6" />
            {doc.original_filename}
          </h1>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span className="uppercase">{doc.file_type}</span>
            <span>{formatBytes(doc.size_bytes)}</span>
            {doc.doc_type && (
              <span className="rounded-full bg-accent px-2 py-0.5 text-xs">
                {doc.doc_type.replace(/_/g, " ")}
              </span>
            )}
            {doc.domain && <span>{doc.domain}</span>}
            {doc.country && <span>{doc.country}</span>}
            {doc.language && <span>{doc.language}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setChatOpen(!chatOpen)}
          >
            <MessageSquare className="h-4 w-4 mr-1" />
            Chat
          </Button>
          <StatusBadge status={doc.status} />
        </div>
      </div>

      {doc.failure_reason && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <strong>Error:</strong> {doc.failure_reason}
        </div>
      )}

      {doc.summary && (
        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-medium mb-1">Summary</h3>
          <p className="text-sm text-muted-foreground">{doc.summary}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Extracted Fields */}
        <div className="lg:col-span-2 space-y-6">
          {/* Extracted Fields */}
          {fields.length > 0 && (
            <div className="rounded-lg border">
              <div className="border-b p-4">
                <h3 className="font-medium">Extracted Fields</h3>
              </div>
              <div className="divide-y">
                {fields.map((field) => (
                  <div key={field.id} className="flex items-center gap-3 p-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">
                          {field.field_name.replace(/_/g, " ")}
                        </span>
                        <span className="text-xs text-muted-foreground uppercase">
                          {field.field_type}
                        </span>
                        {field.is_entity_ref && (
                          <span className="text-xs bg-purple-100 text-purple-700 rounded px-1">
                            entity
                          </span>
                        )}
                      </div>
                      {editingField === field.id ? (
                        <div className="flex items-center gap-2 mt-1">
                          <input
                            type="text"
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            className="flex-1 rounded border px-2 py-1 text-sm"
                            autoFocus
                          />
                          <Button size="sm" onClick={() => handleSaveField(field.id)}>
                            Save
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setEditingField(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground truncate">
                          {field.field_value ?? <span className="italic">null</span>}
                        </p>
                      )}
                      {field.reasoning && (
                        <p className="text-xs text-muted-foreground mt-0.5 italic">
                          {field.reasoning}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <ConfidencePill confidence={field.confidence} />
                      {editingField !== field.id && (
                        <button
                          className="text-muted-foreground hover:text-foreground"
                          onClick={() => {
                            setEditingField(field.id);
                            setEditValue(field.field_value ?? "");
                          }}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Related Entities */}
          {entities.length > 0 && (
            <div className="rounded-lg border">
              <div className="border-b p-4">
                <h3 className="font-medium">Related Entities</h3>
              </div>
              <div className="divide-y">
                {entities.map((entity) => (
                  <div
                    key={`${entity.entity_id}-${entity.role}`}
                    className="flex items-center justify-between p-3"
                  >
                    <div>
                      <span className="text-sm font-medium">
                        {entity.canonical_name}
                      </span>
                      <span className="ml-2 text-xs text-muted-foreground">
                        {entity.entity_type}
                      </span>
                    </div>
                    <span className="text-xs rounded-full bg-accent px-2 py-0.5">
                      {entity.role}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: Pipeline Timeline + File Info */}
        <div className="space-y-6">
          {/* Pipeline Timeline */}
          <div className="rounded-lg border">
            <div className="border-b p-4">
              <h3 className="font-medium">Pipeline</h3>
            </div>
            <div className="p-4 space-y-3">
              {PIPELINE_STAGES.map((stage) => {
                const event = events.find((e) => e.stage === stage.key);
                const stageStatusIndex = STATUS_ORDER.indexOf(stage.status);
                const isComplete = event?.status === "success";
                const isFailed = event?.status === "failure";
                const isActive =
                  !isComplete && !isFailed && currentStatusIndex >= stageStatusIndex - 1 && currentStatusIndex < stageStatusIndex;

                return (
                  <div key={stage.key} className="flex items-center gap-3">
                    {isComplete ? (
                      <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                    ) : isFailed ? (
                      <XCircle className="h-4 w-4 text-red-500 shrink-0" />
                    ) : isActive ? (
                      <Loader2 className="h-4 w-4 text-blue-500 animate-spin shrink-0" />
                    ) : (
                      <Circle className="h-4 w-4 text-muted-foreground/30 shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p
                        className={`text-sm ${isComplete ? "text-foreground" : isActive ? "text-blue-600 font-medium" : "text-muted-foreground"}`}
                      >
                        {stage.label}
                      </p>
                    </div>
                    {event?.duration_ms != null && (
                      <span className="text-xs text-muted-foreground">
                        {event.duration_ms < 1000
                          ? `${event.duration_ms}ms`
                          : `${(event.duration_ms / 1000).toFixed(1)}s`}
                      </span>
                    )}
                  </div>
                );
              })}
              {doc.status === "ready" && (
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                  <p className="text-sm font-medium text-green-700">Ready</p>
                </div>
              )}
            </div>
          </div>

          {/* File Info */}
          <div className="rounded-lg border">
            <div className="border-b p-4">
              <h3 className="font-medium">File Info</h3>
            </div>
            <div className="p-4 space-y-2 text-sm">
              <InfoRow label="Type" value={doc.mime_type} />
              <InfoRow label="Size" value={formatBytes(doc.size_bytes)} />
              <InfoRow
                label="Uploaded"
                value={new Date(doc.created_at).toLocaleString()}
              />
              {doc.is_scanned != null && (
                <InfoRow label="Scanned" value={doc.is_scanned ? "Yes" : "No"} />
              )}
              {doc.is_handwritten != null && (
                <InfoRow
                  label="Handwritten"
                  value={doc.is_handwritten ? "Yes" : "No"}
                />
              )}
            </div>
          </div>

          {/* Open File */}
          <a
            href={`${process.env.NEXT_PUBLIC_SUPABASE_URL}/storage/v1/object/authenticated/${doc.storage_path}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm font-medium hover:bg-muted transition-colors w-full"
          >
            <ExternalLink className="h-4 w-4" />
            Open File
          </a>
        </div>
      </div>

      {/* Chat Side Panel */}
      {chatOpen && (
        <div className="fixed top-14 right-0 w-96 h-[calc(100vh-3.5rem)] border-l bg-background z-30 flex flex-col">
          <div className="flex items-center justify-between border-b p-3">
            <h3 className="font-medium text-sm">Chat with this document</h3>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setChatOpen(false)}
            >
              <XCircle className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex-1 overflow-hidden">
            <ChatPanel documentId={documentId} scope="document" />
          </div>
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
    <span className={`rounded-full px-3 py-1 text-sm font-medium ${color}`}>
      {status}
    </span>
  );
}

function ConfidencePill({ confidence }: { confidence: number | null }) {
  if (confidence == null) return null;

  const pct = Math.round(confidence * 100);
  let color = "bg-green-100 text-green-700";
  if (confidence < 0.5) color = "bg-red-100 text-red-700";
  else if (confidence < 0.7) color = "bg-yellow-100 text-yellow-700";
  else if (confidence < 0.9) color = "bg-blue-100 text-blue-700";

  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {pct}%
    </span>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
