import { createClient } from "@/lib/supabase/server";
import { ALLOWED_MIME_TYPES, MAX_FILE_SIZE, MIME_TO_FILE_TYPE } from "@/lib/constants";
import { NextResponse } from "next/server";
import { z } from "zod/v4";

const DocumentCreateSchema = z.object({
  file_hash: z.string().min(1),
  original_filename: z.string().min(1),
  mime_type: z.string().min(1),
  size_bytes: z.number().int().positive(),
  storage_path: z.string().min(1),
  folder_id: z.string().uuid().optional(),
  user_note: z.string().optional(),
});

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: z.infer<typeof DocumentCreateSchema>;
  try {
    body = DocumentCreateSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 422 });
  }

  // Validate MIME type
  if (!ALLOWED_MIME_TYPES.has(body.mime_type)) {
    return NextResponse.json({ error: "Unsupported file type" }, { status: 422 });
  }

  // Validate file size
  if (body.size_bytes > MAX_FILE_SIZE) {
    return NextResponse.json({ error: "File too large (max 50MB)" }, { status: 422 });
  }

  const file_type = MIME_TO_FILE_TYPE[body.mime_type];

  // Check for duplicate hash
  const { data: existing } = await supabase
    .from("documents")
    .select("id")
    .eq("user_id", user.id)
    .eq("file_hash", body.file_hash)
    .is("deleted_at", null)
    .maybeSingle();

  if (existing) {
    return NextResponse.json(
      { error: "File already uploaded", doc_id: existing.id },
      { status: 409 },
    );
  }

  // Insert document row
  const { data: doc, error: insertError } = await supabase
    .from("documents")
    .insert({
      user_id: user.id,
      file_hash: body.file_hash,
      original_filename: body.original_filename,
      mime_type: body.mime_type,
      file_type,
      size_bytes: body.size_bytes,
      storage_path: body.storage_path,
      folder_id: body.folder_id ?? null,
      user_note: body.user_note ?? null,
    })
    .select("id")
    .single();

  if (insertError) {
    console.error("Document insert error:", insertError.message);
    return NextResponse.json({ error: "Failed to create document" }, { status: 500 });
  }

  // Enqueue for processing via FastAPI
  const apiUrl = process.env.APP_API_URL ?? "http://localhost:8000";
  const apiKey = process.env.BACKEND_API_KEY;

  try {
    const enqueueRes = await fetch(`${apiUrl}/enqueue?doc_id=${doc.id}`, {
      method: "POST",
      headers: { "X-API-Key": apiKey ?? "" },
    });

    if (!enqueueRes.ok) {
      console.error("Enqueue failed:", await enqueueRes.text());
      // Document is created but not enqueued — can retry later
    }
  } catch (err) {
    console.error("Enqueue fetch error:", err);
  }

  return NextResponse.json({ doc_id: doc.id });
}
