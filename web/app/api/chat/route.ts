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

  const body = await req.json();

  const apiUrl = process.env.APP_API_URL ?? "http://localhost:8000";
  const apiKey = process.env.BACKEND_API_KEY;

  const res = await fetch(`${apiUrl}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey ?? "",
    },
    body: JSON.stringify({
      question: body.question,
      user_id: user.id,
      document_id: body.document_id ?? null,
      scope: body.scope ?? "document",
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    console.error("Chat API error:", text);
    return NextResponse.json({ error: "Chat failed" }, { status: 502 });
  }

  // Stream SSE through to the client
  return new Response(res.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
