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

  const res = await fetch(`${apiUrl}/search`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey ?? "",
    },
    body: JSON.stringify({
      term: body.term ?? null,
      chips: body.chips ?? [],
      user_id: user.id,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    console.error("Search API error:", text);
    return NextResponse.json({ error: "Search failed" }, { status: 502 });
  }

  const data = await res.json();
  return NextResponse.json(data);
}
