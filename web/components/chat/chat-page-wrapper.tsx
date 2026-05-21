"use client";

import { ChatPanel } from "@/components/chat/chat-panel";

export function ChatPageWrapper() {
  return (
    <div className="h-[calc(100vh-3.5rem-3rem)]">
      <div className="mb-4">
        <h2 className="text-xl font-semibold">Chat</h2>
        <p className="text-sm text-muted-foreground">
          Ask anything about your documents. Answers are grounded in your knowledge graph and document content.
        </p>
      </div>
      <div className="h-[calc(100%-4rem)] rounded-lg border">
        <ChatPanel scope="all" />
      </div>
    </div>
  );
}
