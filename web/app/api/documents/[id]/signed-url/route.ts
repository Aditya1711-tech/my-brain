import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const supabase = await createClient();

  const { data: doc } = await supabase
    .from("documents")
    .select("storage_path, mime_type, original_filename")
    .eq("id", id)
    .single();

  if (!doc) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const { data: signed, error } = await supabase.storage
    .from("user-uploads")
    .createSignedUrl(doc.storage_path, 3600);

  if (error || !signed) {
    return NextResponse.json({ error: "Failed to create signed URL" }, { status: 500 });
  }

  return NextResponse.json({
    url: signed.signedUrl,
    mime_type: doc.mime_type,
    filename: doc.original_filename,
  });
}
