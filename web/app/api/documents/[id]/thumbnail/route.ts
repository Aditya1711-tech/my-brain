import { createClient } from "@/lib/supabase/server";
import { createClient as createAdminClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

// Service-role client — used only after ownership is verified via RLS
const adminSupabase = createAdminClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!,
);

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  // Verify the caller owns this document (RLS enforces user_id filter)
  const supabase = await createClient();
  const { data: doc } = await supabase
    .from("documents")
    .select("id")
    .eq("id", id)
    .single();

  if (!doc) {
    return new NextResponse(null, { status: 404 });
  }

  // Now safe to sign — ownership confirmed
  const { data, error } = await adminSupabase.storage
    .from("user-uploads")
    .createSignedUrl(`thumbnails/${id}.jpg`, 3600);

  if (error || !data) {
    return new NextResponse(null, { status: 404 });
  }

  return NextResponse.redirect(data.signedUrl, { status: 307 });
}
