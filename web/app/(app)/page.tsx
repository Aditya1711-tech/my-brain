import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { LibraryPage } from "@/components/library/library-page";

export default async function HomePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return <LibraryPage />;
}
