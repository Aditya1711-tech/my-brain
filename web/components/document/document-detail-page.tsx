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
import { DocumentViewerModal } from "@/components/shared/document-viewer-modal";
import { Button } from "@/components/ui/button";
import { useRealtimeDocuments } from "@/lib/hooks/use-realtime-documents";
import { ChatPanel } from "@/components/chat/chat-panel";
import { useIsMobile } from "@/lib/hooks/use-is-mobile";

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
  const isMobile = useIsMobile();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [fields, setFields] = useState<ExtractedField[]>([]);
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [savedField, setSavedField] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [viewerOpen, setViewerOpen] = useState(false);

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
    loadDocument(); // eslint-disable-line react-hooks/set-state-in-effect -- initial data fetch
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
    setSavedField(fieldId);
    setTimeout(() => setSavedField(null), 1200);
  };

  if (loading) {
    return (
      <div
        className="flex h-full items-center justify-center"
        aria-busy="true"
        aria-label="Loading document"
      >
        <Loader2 aria-hidden="true" className="h-6 w-6 animate-spin" style={{ color: "var(--fg-muted)" }} />
        <span className="sr-only">Loading document…</span>
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
  const hPad = isMobile ? "16px" : "40px";

  return (
    <div className="space-y-6" style={{ padding: `${isMobile ? "16px" : "40px"} ${hPad} ${isMobile ? "var(--mobile-content-pb, 96px)" : "80px"}` }}>
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => router.push("/")}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back
        </Button>
      </div>

      <div className={`flex ${isMobile ? "flex-col gap-3" : "items-start justify-between"}`}>
        <div className="space-y-1 min-w-0">
          <h1 className={`${isMobile ? "text-lg" : "text-2xl"} font-semibold flex items-center gap-2`}>
            <FileText className="h-5 w-5 shrink-0" />
            <span className="truncate">{doc.original_filename}</span>
          </h1>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
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
        <div className={`flex items-center gap-2 ${isMobile ? "self-start" : ""}`}>
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

      {doc.status === "failed" && (
        <div
          style={{
            borderRadius: 10,
            border: "1px solid var(--status-error-dot)",
            background: "var(--status-error-bg)",
            padding: 16,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <div style={{ fontSize: 14, color: "var(--status-error-fg)" }}>
              <strong>Processing failed:</strong> {doc.failure_reason ?? "Unknown error"}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  await fetch(`/api/documents/retry`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ document_id: documentId }),
                  });
                  loadDocument();
                } catch {
                  // Toast error handled by the API
                }
              }}
              style={{ flexShrink: 0 }}
            >
              Retry
            </Button>
          </div>
        </div>
      )}

      {doc.summary && (
        <div style={{ borderRadius: 10, border: "1px solid var(--border-faint)", background: "var(--bg-elevated)", padding: 16, boxShadow: "var(--trove-shadow-sm)" }}>
          <h3 style={{ fontFamily: "var(--trove-sans, sans-serif)", fontWeight: 600, fontSize: 13, color: "var(--fg-strong)", marginBottom: 6 }}>Summary</h3>
          <p style={{ fontSize: 14, color: "var(--fg-muted)", lineHeight: 1.6, fontFamily: "var(--trove-sans, sans-serif)" }}>{doc.summary}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Extracted Fields */}
        <div className="lg:col-span-2 space-y-6">
          {/* Extracted Fields */}
          {fields.length > 0 && (
            <div style={{ borderRadius: 10, border: "1px solid var(--border-faint)", background: "var(--bg-elevated)", boxShadow: "var(--trove-shadow-sm)" }}>
              <div style={{ borderBottom: "1px solid var(--border-faint)", padding: "12px 16px" }}>
                <h3 style={{ fontFamily: "var(--trove-sans, sans-serif)", fontWeight: 600, fontSize: 13, color: "var(--fg-strong)" }}>Extracted Fields</h3>
              </div>
              <div className="divide-y">
                {fields.map((field) => (
                  <div
                    key={field.id}
                    className="flex items-center gap-3 p-3"
                    style={{
                      transition: "background 600ms ease",
                      background: savedField === field.id ? "var(--status-ready-bg)" : "transparent",
                    }}
                  >
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
            <div style={{ borderRadius: 10, border: "1px solid var(--border-faint)", background: "var(--bg-elevated)", boxShadow: "var(--trove-shadow-sm)" }}>
              <div style={{ borderBottom: "1px solid var(--border-faint)", padding: "12px 16px" }}>
                <h3 style={{ fontFamily: "var(--trove-sans, sans-serif)", fontWeight: 600, fontSize: 13, color: "var(--fg-strong)" }}>Related Entities</h3>
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
          <div style={{ borderRadius: 10, border: "1px solid var(--border-faint)", background: "var(--bg-elevated)", boxShadow: "var(--trove-shadow-sm)" }}>
            <div style={{ borderBottom: "1px solid var(--border-faint)", padding: "12px 16px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h3 style={{ fontFamily: "var(--trove-sans, sans-serif)", fontWeight: 600, fontSize: 13, color: "var(--fg-strong)" }}>Pipeline</h3>
              {doc.status !== "failed" && (
                <span className="text-xs text-muted-foreground">
                  {doc.status === "ready"
                    ? "Complete"
                    : `${events.filter((e) => e.status === "success").length}/${PIPELINE_STAGES.length} stages`}
                </span>
              )}
            </div>
            <div className="p-4">
              {/* Progress bar */}
              {doc.status !== "failed" && (
                <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden mb-4">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ease-out ${
                      doc.status === "ready" ? "bg-green-500" : "bg-blue-500"
                    }`}
                    style={{
                      width: `${doc.status === "ready" ? 100 : Math.max(5, (events.filter((e) => e.status === "success").length / PIPELINE_STAGES.length) * 100)}%`,
                    }}
                  />
                </div>
              )}
              <div className="space-y-1">
                {PIPELINE_STAGES.map((stage, idx) => {
                  const event = events.find((e) => e.stage === stage.key);
                  const stageStatusIndex = STATUS_ORDER.indexOf(stage.status);
                  const isComplete = event?.status === "success";
                  const isFailed = event?.status === "failure";
                  const isActive =
                    !isComplete && !isFailed && currentStatusIndex >= stageStatusIndex - 1 && currentStatusIndex < stageStatusIndex;

                  return (
                    <div key={stage.key} className="flex items-center gap-3 py-1.5">
                      <div className="relative flex flex-col items-center">
                        {isComplete ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0 transition-colors duration-300" />
                        ) : isFailed ? (
                          <XCircle className="h-4 w-4 text-red-500 shrink-0" />
                        ) : isActive ? (
                          <Loader2 className="h-4 w-4 text-blue-500 animate-spin shrink-0" />
                        ) : (
                          <Circle className="h-4 w-4 text-muted-foreground/30 shrink-0" />
                        )}
                        {/* Connecting line */}
                        {idx < PIPELINE_STAGES.length - 1 && (
                          <div
                            className={`absolute top-5 w-0.5 h-3 ${
                              isComplete ? "bg-green-300" : "bg-muted"
                            }`}
                          />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p
                          className={`text-sm transition-colors duration-300 ${
                            isComplete
                              ? "text-foreground"
                              : isActive
                                ? "text-blue-600 font-medium"
                                : "text-muted-foreground"
                          }`}
                        >
                          {stage.label}
                        </p>
                      </div>
                      {event?.duration_ms != null && (
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {event.duration_ms < 1000
                            ? `${event.duration_ms}ms`
                            : `${(event.duration_ms / 1000).toFixed(1)}s`}
                        </span>
                      )}
                    </div>
                  );
                })}
                {doc.status === "ready" && (
                  <div className="flex items-center gap-3 py-1.5">
                    <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                    <p className="text-sm font-medium text-green-700">Ready</p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* File Info */}
          <div style={{ borderRadius: 10, border: "1px solid var(--border-faint)", background: "var(--bg-elevated)", boxShadow: "var(--trove-shadow-sm)" }}>
            <div style={{ borderBottom: "1px solid var(--border-faint)", padding: "12px 16px" }}>
              <h3 style={{ fontFamily: "var(--trove-sans, sans-serif)", fontWeight: 600, fontSize: 13, color: "var(--fg-strong)" }}>File Info</h3>
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
          <button
            onClick={() => setViewerOpen(true)}
            className="flex items-center justify-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm font-medium hover:bg-muted transition-colors w-full"
          >
            <ExternalLink className="h-4 w-4" />
            Open File
          </button>
          <DocumentViewerModal
            documentId={doc.id}
            open={viewerOpen}
            onClose={() => setViewerOpen(false)}
          />

          {/* View Trace in Langfuse */}
          {process.env.NEXT_PUBLIC_LANGFUSE_URL && (
            <a
              href={`${process.env.NEXT_PUBLIC_LANGFUSE_URL}/trace/${documentId}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm font-medium hover:bg-muted transition-colors w-full"
            >
              <ExternalLink className="h-4 w-4" />
              View Trace
            </a>
          )}
        </div>
      </div>

      {/* Chat Side Panel */}
      {chatOpen && (
        <ChatSidePanel
          documentId={documentId}
          onClose={() => setChatOpen(false)}
        />
      )}
    </div>
  );
}

function ChatSidePanel({ documentId, onClose }: { documentId: string; onClose: () => void }) {
  const isMobile = useIsMobile();

  // Escape key handler
  useEffect(() => {
    const handler = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      style={{
        position: "fixed",
        top: isMobile ? "auto" : 0,
        bottom: isMobile ? 0 : "auto",
        right: 0,
        left: isMobile ? 0 : "auto",
        width: isMobile ? "100%" : 384,
        height: isMobile ? "70vh" : "100%",
        borderLeft: isMobile ? "none" : "1px solid var(--border-faint)",
        borderTop: isMobile ? "1px solid var(--border-faint)" : "none",
        borderRadius: isMobile ? "18px 18px 0 0" : 0,
        background: "var(--bg-elevated)",
        zIndex: 30,
        display: "flex",
        flexDirection: "column",
        animation: isMobile
          ? "k-sheet-in 240ms var(--trove-ease-out, ease-out) both"
          : "k-slide-in-right 240ms var(--trove-ease-out, ease-out) both",
        boxShadow: "var(--trove-shadow-lg)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--border-faint)",
          padding: "12px 14px",
        }}
      >
        <h3 style={{ fontFamily: "var(--trove-sans, sans-serif)", fontSize: 13, fontWeight: 600, color: "var(--fg-strong)" }}>
          Chat with this document
        </h3>
        <button
          aria-label="Close chat panel"
          onClick={onClose}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--bg-subtle)"; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "none"; }}
          style={{
            width: 28, height: 28, borderRadius: 7, border: 0,
            background: "none", cursor: "pointer", display: "flex",
            alignItems: "center", justifyContent: "center",
            color: "var(--fg-muted)",
            transition: "background var(--trove-dur-fast, 140ms)",
          }}
        >
          <XCircle aria-hidden="true" className="h-4 w-4" />
        </button>
      </div>
      <div style={{ flex: 1, overflow: "hidden" }}>
        <ChatPanel documentId={documentId} scope="document" />
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const LABEL_MAP: Record<string, string> = {
    uploaded: "Queued",
    ready: "Ready",
    failed: "Failed",
    extracting_text: "Extracting",
    classified: "Classified",
    schema_built: "Building schema",
    extracted: "Extracted",
    verified: "Verified",
    integrated: "Integrating",
    vectorized: "Vectorized",
  };
  const styles: Record<string, { bg: string; color: string }> = {
    uploaded:  { bg: "var(--trove-stone-100)",  color: "var(--trove-stone-600)" },
    ready:     { bg: "var(--status-ready-bg)",  color: "var(--status-ready-fg)" },
    failed:    { bg: "var(--status-error-bg)",  color: "var(--status-error-fg)" },
  };
  const s = styles[status] ?? { bg: "var(--status-processing-bg)", color: "var(--status-processing-fg)" };
  const label = LABEL_MAP[status] ?? status;

  return (
    <span
      style={{
        borderRadius: 999,
        padding: "3px 12px",
        fontSize: 13,
        fontWeight: 500,
        fontFamily: "var(--trove-sans, sans-serif)",
        background: s.bg,
        color: s.color,
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}

function ConfidencePill({ confidence }: { confidence: number | null }) {
  if (confidence == null) return null;

  const pct = Math.round(confidence * 100);
  let bg = "var(--status-ready-bg)";
  let color = "var(--status-ready-fg)";
  if (confidence < 0.5) { bg = "var(--status-error-bg)"; color = "var(--status-error-fg)"; }
  else if (confidence < 0.7) { bg = "var(--status-processing-bg)"; color = "var(--status-processing-fg)"; }

  return (
    <span
      style={{
        borderRadius: 999,
        padding: "2px 8px",
        fontSize: 11,
        fontWeight: 600,
        fontFamily: "var(--trove-mono, monospace)",
        background: bg,
        color: color,
        whiteSpace: "nowrap",
      }}
    >
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
