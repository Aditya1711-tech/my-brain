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
  const documentId = body.document_id;

  if (!documentId) {
    return NextResponse.json({ error: "Missing document_id" }, { status: 422 });
  }

  // Reset document status to 'uploaded' so pipeline re-runs
  const { error } = await supabase
    .from("documents")
    .update({ status: "uploaded", failure_reason: null })
    .eq("id", documentId)
    .eq("user_id", user.id);

  if (error) {
    return NextResponse.json({ error: "Failed to reset document" }, { status: 500 });
  }

  // Re-enqueue for processing
  const apiUrl = process.env.APP_API_URL ?? "http://localhost:8000";
  const apiKey = process.env.BACKEND_API_KEY;

  try {
    await fetch(`${apiUrl}/enqueue`, {
      method: "POST",
      headers: {
        "X-API-Key": apiKey ?? "",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ doc_id: documentId }),
    });
  } catch (err) {
    console.error("Re-enqueue failed:", err);
  }

  return NextResponse.json({ ok: true });
}
