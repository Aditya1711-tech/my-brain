"use client";

import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import {
  Library, MessageSquare, GitBranch, LayoutGrid,
  Settings, LogOut,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface SidebarProps {
  email?: string;
}

const NAV_ITEMS = [
  { href: "/",          label: "Library",      icon: Library },
  { href: "/chat",      label: "Chat",         icon: MessageSquare },
  { href: "/graph",     label: "Connections",  icon: GitBranch },
  { href: "/spaces",    label: "Spaces",       icon: LayoutGrid },
];


function RailButton({
  label, active, onClick, children,
}: {
  label: string;
  active?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      aria-label={label}
      onClick={onClick}
      title={label}
      style={{
        width: 38,
        height: 38,
        borderRadius: 10,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        background: "transparent",
        color: active ? "var(--fg-strong)" : "var(--fg-subtle)",
        transition: "color var(--trove-dur-fast, 140ms), background var(--trove-dur-fast, 140ms)",
        border: 0,
        cursor: "pointer",
      }}
      onMouseEnter={(e) => {
        if (!active) {
          (e.currentTarget as HTMLElement).style.background = "var(--bg-subtle)";
          (e.currentTarget as HTMLElement).style.color = "var(--fg)";
        }
      }}
      onMouseLeave={(e) => {
        if (!active) {
          (e.currentTarget as HTMLElement).style.background = "transparent";
          (e.currentTarget as HTMLElement).style.color = "var(--fg-subtle)";
        }
      }}
    >
      {active && (
        <span
          style={{
            position: "absolute",
            left: -10,
            top: "50%",
            transform: "translateY(-50%)",
            width: 3,
            height: 18,
            borderRadius: 999,
            background: "var(--accent)",
          }}
        />
      )}
      {children}
    </button>
  );
}

export function Sidebar({ email }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  const initials = email ? email.slice(0, 2).toUpperCase() : "??";

  return (
    <aside
      style={{
        width: 76,
        flexShrink: 0,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "20px 0 18px",
        position: "relative",
        zIndex: 5,
        borderRight: "1px solid var(--border-faint)",
      }}
    >
      {/* Constellation mark */}
      <button
        onClick={() => router.push("/")}
        aria-label="Trove home"
        style={{ marginBottom: 18, border: 0, background: "none", cursor: "pointer" }}
      >
        <svg viewBox="0 0 64 64" width="34" height="34" aria-hidden="true">
          <rect x="4" y="4" width="56" height="56" rx="16" fill="#1B4D52" />
          <g stroke="#5FB6BB" strokeWidth="1.4" strokeLinecap="round">
            <line x1="32" y1="32" x2="32" y2="14" />
            <line x1="32" y1="32" x2="47" y2="41" />
            <line x1="32" y1="32" x2="18" y2="43" />
          </g>
          <circle cx="32" cy="32" r="6.8" fill="none" stroke="#EBF5F5" strokeWidth="2.2" />
          <circle cx="32" cy="32" r="1.4" fill="#EBF5F5" />
          <rect x="28.7" y="10.7" width="6.6" height="6.6" rx="1.2" fill="#EBF5F5" />
          <circle cx="47" cy="41" r="3.2" fill="#EBF5F5" />
          <circle cx="18" cy="43" r="2.8" fill="#EBF5F5" />
        </svg>
      </button>

      {/* Vertical wordmark */}
      <div
        style={{
          writingMode: "vertical-rl",
          transform: "rotate(180deg)",
          fontFamily: "var(--trove-serif, Georgia, serif)",
          fontStyle: "italic",
          fontWeight: 500,
          fontSize: 20,
          letterSpacing: "0.02em",
          color: "var(--fg-muted)",
          marginBottom: 22,
          userSelect: "none",
        }}
      >
        Trove
      </div>

      {/* Primary nav */}
      <nav style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "center" }}>
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <RailButton
              key={item.href}
              label={item.label}
              active={active}
              onClick={() => router.push(item.href)}
            >
              <item.icon
                size={20}
                strokeWidth={active ? 1.9 : 1.6}
              />
            </RailButton>
          );
        })}
      </nav>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Bottom utility */}
      <nav style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "center" }}>
        {/* User avatar / sign-out */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              aria-label="Account"
              title={email ?? "Account"}
              style={{
                width: 32,
                height: 32,
                borderRadius: 999,
                background: "var(--bg-subtle)",
                border: "1px solid var(--border-strong)",
                color: "var(--fg-muted)",
                fontFamily: "var(--trove-mono, monospace)",
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: "0.02em",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                marginTop: 4,
              }}
            >
              {initials}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="right" align="end">
            <DropdownMenuItem disabled>
              <Settings className="mr-2 h-4 w-4" />
              Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleSignOut}>
              <LogOut className="mr-2 h-4 w-4" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </nav>
    </aside>
  );
}
