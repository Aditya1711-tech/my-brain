"use client";

import { type User } from "@supabase/supabase-js";
import { Brain, Search } from "lucide-react";
import Link from "next/link";
import { Input } from "@/components/ui/input";
import { UserMenu } from "@/components/shared/user-menu";
import { Sidebar } from "@/components/shared/sidebar";

interface AppShellProps {
  user: User;
  children: React.ReactNode;
}

export function AppShell({ user, children }: AppShellProps) {
  return (
    <div className="flex h-screen flex-col">
      {/* Top bar */}
      <header className="flex h-14 shrink-0 items-center gap-4 border-b px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <Brain className="h-5 w-5" />
          <span>My Brain</span>
        </Link>

        <div className="relative ml-4 flex-1 max-w-md">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search documents..."
            className="pl-9"
          />
        </div>

        <div className="ml-auto">
          <UserMenu email={user.email ?? ""} />
        </div>
      </header>

      {/* Body: sidebar + main */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
