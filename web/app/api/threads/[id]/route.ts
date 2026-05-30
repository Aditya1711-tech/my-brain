import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

const apiUrl = process.env.APP_API_URL ?? "http://localhost:8000";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
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

  const { id } = await params;
  const res = await fetch(`${apiUrl}/threads/${id}/messages`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });

  if (!res.ok) {
    return NextResponse.json(
      { error: "Thread not found" },
      { status: res.status },
    );
  }

  const messages = await res.json();
  return NextResponse.json(messages);
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
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

  const { id } = await params;
  const res = await fetch(`${apiUrl}/threads/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${session.access_token}` },
  });

  if (!res.ok) {
    return NextResponse.json(
      { error: "Delete failed" },
      { status: res.status },
    );
  }

  return NextResponse.json({ deleted: true });
}
