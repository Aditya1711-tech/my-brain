import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const supabase = await createClient();

  const { data, error } = await supabase.storage
    .from("user-uploads")
    .createSignedUrl(`thumbnails/${id}.jpg`, 3600);

  if (error || !data) {
    return new NextResponse(null, { status: 404 });
  }

  return NextResponse.redirect(data.signedUrl, { status: 307 });
}
