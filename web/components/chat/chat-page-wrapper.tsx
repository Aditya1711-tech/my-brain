"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Trash2, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatPanel } from "@/components/chat/chat-panel";

interface Thread {
  id: string;
  title: string | null;
  scope: string;
  document_id: string | null;
  updated_at: string;
}

export function ChatPageWrapper() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);

  const loadThreads = useCallback(async () => {
    try {
      const res = await fetch("/api/threads");
      if (res.ok) {
        const data = await res.json();
        setThreads(data);
      }
    } catch {
      // Ignore
    }
  }, []);

  useEffect(() => {
    loadThreads(); // eslint-disable-line react-hooks/set-state-in-effect -- initial data fetch
  }, [loadThreads]);

  const startNewThread = useCallback(() => {
    setActiveThreadId(null);
  }, []);

  const handleThreadCreated = useCallback(
    (threadId: string) => {
      setActiveThreadId(threadId);
      loadThreads();
    },
    [loadThreads],
  );

  const deleteThread = useCallback(
    async (threadId: string, e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        const res = await fetch(`/api/threads/${threadId}`, { method: "DELETE" });
        if (res.ok) {
          setThreads((prev) => prev.filter((t) => t.id !== threadId));
          if (activeThreadId === threadId) {
            setActiveThreadId(null);
          }
        }
      } catch {
        // Ignore
      }
    },
    [activeThreadId],
  );

  return (
    <div style={{ height: "100%", padding: "40px", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ flex: 1, display: "flex", gap: 16, minHeight: 0 }}>
      {/* Thread sidebar */}
      <div className="w-64 flex-shrink-0 flex flex-col border rounded-lg">
        <div className="p-3 border-b flex items-center justify-between">
          <h3 className="text-sm font-medium">Threads</h3>
          <Button variant="ghost" size="icon" onClick={startNewThread} title="New thread">
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {threads.length === 0 && (
            <p className="text-xs text-muted-foreground p-3">No conversations yet</p>
          )}
          {threads.map((thread) => (
            <button
              key={thread.id}
              onClick={() => setActiveThreadId(thread.id)}
              disabled={threadLoading}
              className={`w-full text-left px-3 py-2 text-sm border-b hover:bg-muted/50 flex items-center gap-2 group ${
                activeThreadId === thread.id ? "bg-muted" : ""
              } ${threadLoading ? "opacity-50 cursor-not-allowed" : ""}`}
            >
              <MessageSquare className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
              <span className="flex-1 truncate">
                {thread.title || "Untitled thread"}
              </span>
              <button
                onClick={(e) => deleteThread(thread.id, e)}
                className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-destructive"
                title="Delete thread"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </button>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="mb-2">
          <h2 className="text-xl font-semibold">Chat</h2>
          <p className="text-sm text-muted-foreground">
            Ask anything about your documents. Answers are grounded in your knowledge graph and document content.
          </p>
        </div>
        <div className="flex-1 rounded-lg border min-h-0">
          <ChatPanel
            key={activeThreadId ?? "new"}
            scope="all"
            threadId={activeThreadId}
            onThreadCreated={handleThreadCreated}
            onLoadingChange={setThreadLoading}
          />
        </div>
      </div>
      </div>
    </div>
  );
}
