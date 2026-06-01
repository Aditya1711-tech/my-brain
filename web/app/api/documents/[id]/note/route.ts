import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import { z } from "zod/v4";

const NoteUpdateSchema = z.object({
  user_note: z.string().max(2000),
});

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: z.infer<typeof NoteUpdateSchema>;
  try {
    body = NoteUpdateSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 422 });
  }

  // Update note; reset indexed_at so the background job re-processes it.
  // The documents_tsv_trigger fires automatically and refreshes full_text_tsv.
  const { error: updateError } = await supabase
    .from("documents")
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    .update({ user_note: body.user_note, user_note_indexed_at: null } as any)
    .eq("id", id)
    .eq("user_id", user.id); // ownership check — RLS also enforces this

  if (updateError) {
    console.error("Note update error:", updateError.message);
    return NextResponse.json({ error: "Failed to save note" }, { status: 500 });
  }

  // Kick off targeted note re-integration (non-blocking — same pattern as /enqueue).
  // ND-B-04 implements the full endpoint; this call is a no-op until then.
  const apiUrl = process.env.APP_API_URL ?? "http://localhost:8000";
  const apiKey = process.env.BACKEND_API_KEY;

  try {
    const reintRes = await fetch(`${apiUrl}/note-reintegrate`, {
      method: "POST",
      headers: {
        "X-API-Key": apiKey ?? "",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ doc_id: id }),
    });

    if (!reintRes.ok) {
      console.error("note-reintegrate failed:", await reintRes.text());
      // Non-fatal: note is saved; background job will pick it up via user_note_indexed_at IS NULL
    }
  } catch (err) {
    console.error("note-reintegrate fetch error:", err);
  }

  return NextResponse.json({ ok: true });
}
