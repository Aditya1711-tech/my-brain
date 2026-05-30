import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    return NextResponse.json({ error: "No session" }, { status: 401 });
  }

  const body = await req.json();

  const apiUrl = process.env.APP_API_URL ?? "http://localhost:8000";

  const res = await fetch(`${apiUrl}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({
      question: body.question,
      thread_id: body.thread_id ?? null,
      document_id: body.document_id ?? null,
      scope: body.scope ?? "all",
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    console.error("Chat API error:", text);
    return NextResponse.json({ error: "Chat failed" }, { status: 502 });
  }

  // Stream SSE through to the client, including X-Thread-Id header
  const threadId = res.headers.get("X-Thread-Id");
  const headers: Record<string, string> = {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
  };
  if (threadId) {
    headers["X-Thread-Id"] = threadId;
  }

  return new Response(res.body, { headers });
}
