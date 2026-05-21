"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Folder, Tag, Library, MessageSquare, GitBranch } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

interface FolderItem {
  id: string;
  name: string;
}

interface TagItem {
  id: string;
  name: string;
}

const NAV_ITEMS = [
  { href: "/", label: "Library", icon: Library },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/graph", label: "Graph", icon: GitBranch },
];

export function Sidebar() {
  const pathname = usePathname();
  const [folders, setFolders] = useState<FolderItem[]>([]);
  const [tags, setTags] = useState<TagItem[]>([]);

  useEffect(() => {
    async function load() {
      const supabase = createClient();

      const [foldersRes, tagsRes] = await Promise.all([
        supabase.from("folders").select("id, name").order("name"),
        supabase.from("tags").select("id, name").order("name"),
      ]);

      if (foldersRes.data) setFolders(foldersRes.data);
      if (tagsRes.data) setTags(tagsRes.data);
    }
    load();
  }, []);

  return (
    <aside className="w-56 shrink-0 border-r bg-muted/30 p-4 hidden md:block">
      {/* Nav links */}
      <nav className="space-y-1">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              pathname === item.href
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
            )}
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </Link>
        ))}
      </nav>

      {/* Folders */}
      {folders.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 px-3 text-xs font-semibold uppercase text-muted-foreground">
            Folders
          </h3>
          <div className="space-y-1">
            {folders.map((f) => (
              <div
                key={f.id}
                className="flex items-center gap-2 rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent/50 cursor-pointer"
              >
                <Folder className="h-3.5 w-3.5" />
                {f.name}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tags */}
      {tags.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 px-3 text-xs font-semibold uppercase text-muted-foreground">
            Tags
          </h3>
          <div className="flex flex-wrap gap-1 px-3">
            {tags.map((t) => (
              <span
                key={t.id}
                className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs cursor-pointer"
              >
                <Tag className="h-3 w-3" />
                {t.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}
