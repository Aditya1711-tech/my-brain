import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

const apiUrl = process.env.APP_API_URL ?? "http://localhost:8000";
const apiKey = process.env.BACKEND_API_KEY ?? "";

export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const res = await fetch(
    `${apiUrl}/threads?user_id=${encodeURIComponent(user.id)}`,
    { headers: { "X-API-Key": apiKey } },
  );

  if (!res.ok) {
    return NextResponse.json({ error: "Failed to list threads" }, { status: 502 });
  }

  const threads = await res.json();
  return NextResponse.json(threads);
}
