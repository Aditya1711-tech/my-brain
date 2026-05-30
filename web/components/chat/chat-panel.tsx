"use client";

import { useCallback, useRef, useState, type KeyboardEvent } from "react";
import { Send, Loader2, Database, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

interface Citation {
  type: "kg_fact" | "chunk" | "citation";
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
}

export function ChatPanel({
  documentId,
  scope = "document",
  threadId: initialThreadId,
  onThreadCreated,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(initialThreadId ?? null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  // Load thread history when threadId changes
  const loadHistory = useCallback(async (tid: string) => {
    try {
      const res = await fetch(`/api/threads/${tid}`);
      if (res.ok) {
        const history = await res.json();
        setMessages(
          history.map((m: { role: string; content: string; citations?: Citation[] }) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
            citations: m.citations ?? [],
          })),
        );
      }
    } catch {
      // Ignore — start fresh
    }
  }, []);

  // Allow parent to load a thread
  const switchThread = useCallback(
    (tid: string) => {
      setThreadId(tid);
      setMessages([]);
      loadHistory(tid);
    },
    [loadHistory],
  );

  // Expose switchThread to parent via ref callback
  // (or just use the prop pattern — parent passes threadId)
  // We watch initialThreadId changes
  const prevThreadRef = useRef(initialThreadId);
  if (initialThreadId !== prevThreadRef.current) {
    prevThreadRef.current = initialThreadId;
    if (initialThreadId) {
      switchThread(initialThreadId);
    } else {
      setThreadId(null);
      setMessages([]);
    }
  }

  const sendMessage = useCallback(async () => {
    if (!input.trim() || streaming) return;

    const question = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setStreaming(true);

    const citations: Citation[] = [];
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
        { role: "assistant", content: "", citations: [] },
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
              citations.push(event);
            } else if (event.type === "text_delta") {
              assistantText += event.text;
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === "assistant") {
                  updated[updated.length - 1] = {
                    ...last,
                    content: assistantText,
                    citations,
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

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-muted-foreground text-sm py-8">
            {scope === "document"
              ? "Ask anything about this document"
              : "Ask anything about your documents"}
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted"
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {msg.citations.map((c, ci) => (
                    <CitationBadge key={ci} citation={c} index={ci + 1} />
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {streaming && (
          <div className="flex justify-start">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t p-3 flex gap-2">
        <Input
          placeholder="Ask a question..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={streaming}
          className="flex-1"
        />
        <Button
          size="icon"
          onClick={sendMessage}
          disabled={streaming || !input.trim()}
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function CitationBadge({ citation, index }: { citation: Citation; index: number }) {
  const isKgFact = citation.type === "kg_fact";
  const label = isKgFact
    ? `F${index}`
    : `C${index}`;
  const title = isKgFact
    ? `KG Fact: ${citation.field_name ?? "fact"}`
    : citation.filename ?? `Chunk`;

  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-xs ${
        isKgFact
          ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
          : "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300"
      }`}
      title={title}
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
    </span>
  );
}
