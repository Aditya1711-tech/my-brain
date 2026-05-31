"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Send, Loader2, Database, FileText, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { DocumentViewerModal } from "@/components/shared/document-viewer-modal";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  streaming?: boolean;
}

interface Citation {
  type: "kg_fact" | "chunk" | "citation";
  label?: string;
  // KG fact fields
  entity_id?: string;
  field_name?: string;
  source_document_id?: string;
  // Chunk fields
  chunk_id?: string;
  document_id?: string;
  filename?: string;
  // Legacy
  index?: number;
  chunk_index?: number;
}

interface ChatPanelProps {
  documentId?: string;
  scope?: "document" | "all";
  threadId?: string | null;
  onThreadCreated?: (threadId: string) => void;
  onLoadingChange?: (loading: boolean) => void;
}

function labelCitations(citations: Citation[]): Citation[] {
  let fi = 0, ci = 0;
  return citations.map((c) =>
    c.type === "kg_fact"
      ? { ...c, label: `F${++fi}` }
      : { ...c, label: `C${++ci}` },
  );
}

function filterAndDedupeCitations(citations: Citation[], text: string): Citation[] {
  const labeled = labelCitations(citations);

  // Keep only citations whose label appears in the text
  const referenced = labeled.filter(
    (c) => c.label && text.includes(`[${c.label}]`),
  );

  // Deduplicate by document ID
  const seen = new Set<string>();
  return referenced.filter((c) => {
    const docId = c.type === "kg_fact" ? c.source_document_id : c.document_id;
    if (!docId) return true;
    if (seen.has(docId)) return false;
    seen.add(docId);
    return true;
  });
}

export function ChatPanel({
  documentId,
  scope = "document",
  threadId: initialThreadId,
  onThreadCreated,
  onLoadingChange,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(initialThreadId ?? null);
  const [viewerDocId, setViewerDocId] = useState<string | null>(null);
  const [viewerOpen, setViewerOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const loadHistory = useCallback(async (tid: string) => {
    setHistoryLoading(true);
    onLoadingChange?.(true);
    try {
      const res = await fetch(`/api/threads/${tid}`);
      if (res.ok) {
        const history = await res.json();
        setMessages(
          history.map((m: { role: string; content: string; citations?: Citation[] }) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
            citations: m.citations
              ? filterAndDedupeCitations(m.citations, m.content)
              : [],
          })),
        );
      }
    } catch {
      // Ignore — start fresh
    } finally {
      setHistoryLoading(false);
      onLoadingChange?.(false);
    }
  }, [onLoadingChange]);

  useEffect(() => {
    if (initialThreadId) {
      loadHistory(initialThreadId); // eslint-disable-line react-hooks/set-state-in-effect -- initial data fetch
    }
  }, [initialThreadId, loadHistory]);

  const sendMessage = useCallback(async () => {
    if (!input.trim() || streaming) return;

    const question = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setStreaming(true);

    const rawCitations: Citation[] = [];
    let assistantText = "";

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          thread_id: threadId,
          document_id: documentId ?? null,
          scope,
        }),
      });

      if (!res.ok || !res.body) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "Sorry, something went wrong." },
        ]);
        setStreaming(false);
        return;
      }

      // Capture thread ID from response header
      const newThreadId = res.headers.get("X-Thread-Id");
      if (newThreadId && !threadId) {
        setThreadId(newThreadId);
        onThreadCreated?.(newThreadId);
      }

      // Add empty assistant message to stream into
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "", citations: [], streaming: true },
      ]);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const json = line.slice(6);

          try {
            const event = JSON.parse(json);

            if (event.type === "citation" || event.type === "kg_fact" || event.type === "chunk") {
              rawCitations.push(event);
            } else if (event.type === "text_delta") {
              assistantText += event.text;
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === "assistant") {
                  updated[updated.length - 1] = {
                    ...last,
                    content: assistantText,
                    streaming: true,
                  };
                }
                return updated;
              });
              scrollToBottom();
            } else if (event.type === "error") {
              assistantText += `\n\nError: ${event.message}`;
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === "assistant") {
                  updated[updated.length - 1] = { ...last, content: assistantText };
                }
                return updated;
              });
            }
          } catch {
            // Skip malformed JSON
          }
        }
      }

      // Finalize: filter/dedupe citations and mark not streaming
      const finalCitations = filterAndDedupeCitations(rawCitations, assistantText);
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last?.role === "assistant") {
          updated[updated.length - 1] = {
            ...last,
            content: assistantText,
            citations: finalCitations,
            streaming: false,
          };
        }
        return updated;
      });
    } catch {
      setMessages((prev) => [
        ...prev.slice(0, -1),
        { role: "assistant", content: "Connection error. Please try again." },
      ]);
    } finally {
      setStreaming(false);
      scrollToBottom();
    }
  }, [input, streaming, threadId, documentId, scope, scrollToBottom, onThreadCreated]);

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const openViewer = useCallback((docId: string) => {
    setViewerDocId(docId);
    setViewerOpen(true);
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {historyLoading ? (
          <div className="flex h-full items-center justify-center" style={{ flexDirection: "column", gap: 10 }}>
            <Loader2 aria-hidden="true" className="h-5 w-5 animate-spin" style={{ color: "var(--fg-muted)" }} />
            <p style={{ fontSize: 12, color: "var(--fg-muted)", fontFamily: "var(--trove-sans, sans-serif)" }}>
              Loading conversation…
            </p>
          </div>
        ) : messages.length === 0 ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              gap: 12,
              padding: "24px",
              textAlign: "center",
            }}
          >
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 14,
                background: "var(--accent-soft)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--accent-ink)",
              }}
            >
              <MessageSquare aria-hidden="true" className="h-5 w-5" />
            </div>
            <p
              style={{
                fontFamily: "var(--trove-serif, Georgia, serif)",
                fontStyle: "italic",
                fontSize: 17,
                color: "var(--fg-muted)",
              }}
            >
              {scope === "document"
                ? "Ask anything about this document"
                : "Ask anything about your documents"}
            </p>
          </div>
        ) : null}
        {!historyLoading && messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            style={{ animation: "k-fade-in 180ms var(--trove-ease-out, ease-out) both" }}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted"
              }`}
            >
              {msg.role === "assistant" && !msg.streaming ? (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                    strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                    em: ({ children }) => <em className="italic">{children}</em>,
                    ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-0.5">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-0.5">{children}</ol>,
                    li: ({ children }) => <li>{children}</li>,
                    code: ({ children, className }) =>
                      className ? (
                        <code className="block bg-black/10 dark:bg-white/10 rounded px-2 py-1 text-xs font-mono my-1 whitespace-pre-wrap">{children}</code>
                      ) : (
                        <code className="bg-black/10 dark:bg-white/10 rounded px-1 text-xs font-mono">{children}</code>
                      ),
                    blockquote: ({ children }) => <blockquote className="border-l-2 border-current/30 pl-3 italic my-1">{children}</blockquote>,
                    h1: ({ children }) => <h1 className="font-semibold text-base mb-1">{children}</h1>,
                    h2: ({ children }) => <h2 className="font-semibold mb-1">{children}</h2>,
                    h3: ({ children }) => <h3 className="font-medium mb-1">{children}</h3>,
                  }}
                >
                  {msg.content}
                </ReactMarkdown>
              ) : (
                <p className="whitespace-pre-wrap">{msg.content}</p>
              )}
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {msg.citations.map((c, ci) => (
                    <CitationBadge
                      key={ci}
                      citation={c}
                      onClick={openViewer}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {streaming && (
          <div className="flex justify-start">
            <div
              className="bg-muted rounded-lg px-3 py-2.5"
              style={{ display: "flex", alignItems: "center", gap: 4 }}
              aria-label="Assistant is typing"
            >
              {[0, 1, 2].map((di) => (
                <span
                  key={di}
                  aria-hidden="true"
                  style={{
                    display: "inline-block",
                    width: 5,
                    height: 5,
                    borderRadius: 999,
                    background: "var(--fg-muted)",
                    animation: "k-typing-dot 1.2s ease infinite",
                    animationDelay: `${di * 0.2}s`,
                  }}
                />
              ))}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t p-3 flex flex-col gap-1.5">
        <div className="flex gap-2">
          <Input
            placeholder="Ask a question…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={streaming}
            className="flex-1"
            autoFocus
          />
          <Button
            size="icon"
            onClick={sendMessage}
            disabled={streaming || !input.trim()}
            aria-label="Send message"
          >
            <Send aria-hidden="true" className="h-4 w-4" />
          </Button>
        </div>
        {input.trim().length > 0 && !streaming && (
          <p
            style={{
              fontSize: 11,
              color: "var(--fg-subtle)",
              fontFamily: "var(--trove-sans, sans-serif)",
              textAlign: "right",
              paddingRight: 44,
              animation: "k-fade-in 120ms var(--trove-ease-out, ease-out) both",
            }}
          >
            ↵ to send
          </p>
        )}
      </div>

      {/* Document viewer */}
      {viewerDocId && (
        <DocumentViewerModal
          documentId={viewerDocId}
          open={viewerOpen}
          onClose={() => setViewerOpen(false)}
        />
      )}
    </div>
  );
}

function CitationBadge({
  citation,
  onClick,
}: {
  citation: Citation;
  onClick: (docId: string) => void;
}) {
  const isKgFact = citation.type === "kg_fact";
  const label = citation.label ?? (isKgFact ? "F?" : "C?");
  const title = isKgFact
    ? `KG Fact: ${citation.field_name ?? "fact"}`
    : citation.filename ?? "Chunk";

  const docId = isKgFact ? citation.source_document_id : citation.document_id;

  return (
    <button
      type="button"
      onClick={() => { if (docId) onClick(docId); }}
      disabled={!docId}
      title={title}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 3,
        borderRadius: 5,
        padding: "2px 6px",
        fontSize: 11,
        fontFamily: "var(--trove-mono, monospace)",
        cursor: docId ? "pointer" : "default",
        transition: "opacity var(--trove-dur-fast, 140ms)",
        background: isKgFact ? "var(--trove-teal-50)" : "var(--trove-amber-50)",
        color: isKgFact ? "var(--trove-teal-700)" : "var(--trove-amber-700)",
        border: `1px solid ${isKgFact ? "var(--trove-teal-100)" : "var(--trove-amber-200)"}`,
      }}
      onMouseEnter={(e) => { if (docId) (e.currentTarget as HTMLElement).style.opacity = "0.7"; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.opacity = "1"; }}
    >
      {isKgFact ? (
        <Database className="h-3 w-3" />
      ) : (
        <FileText className="h-3 w-3" />
      )}
      [{label}]
      {!isKgFact && citation.filename && (
        <span className="ml-0.5 truncate max-w-[80px]">{citation.filename}</span>
      )}
    </button>
  );
}
