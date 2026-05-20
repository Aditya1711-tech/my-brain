import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

export default async function HomePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return (
    <div>
      <h2 className="text-2xl font-bold">Welcome</h2>
      <p className="mt-2 text-muted-foreground">
        Hello {user.email} — your document library will appear here.
      </p>
    </div>
  );
}
