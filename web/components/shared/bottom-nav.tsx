"use client";

import { usePathname, useRouter } from "next/navigation";
import { Library, Search, MessageSquare, GitBranch } from "lucide-react";

const NAV_ITEMS = [
  { href: "/",       label: "Library",     icon: Library },
  { href: "/search", label: "Search",      icon: Search },
  { href: "/chat",   label: "Chat",        icon: MessageSquare },
  { href: "/graph",  label: "Graph",       icon: GitBranch },
];

export function BottomNav() {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <nav
      className="trove-bottom-nav"
      style={{
        position: "fixed",
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: 50,
        height: "calc(60px + env(safe-area-inset-bottom, 0px))",
        paddingBottom: "env(safe-area-inset-bottom, 0px)",
        background: "var(--bg-elevated)",
        borderTop: "1px solid var(--border-faint)",
        display: "none", // toggled to flex by CSS media query in globals.css
        alignItems: "stretch",
        backdropFilter: "blur(12px) saturate(120%)",
      }}
    >
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href ||
          (item.href !== "/" && pathname.startsWith(item.href));
        return (
          <button
            key={item.href}
            onClick={() => router.push(item.href)}
            aria-label={item.label}
            aria-current={active ? "page" : undefined}
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 3,
              background: "transparent",
              border: 0,
              cursor: "pointer",
              color: active ? "var(--accent)" : "var(--fg-subtle)",
              position: "relative",
              transition: "color 140ms ease",
              minHeight: 44,
              WebkitTapHighlightColor: "transparent",
            }}
          >
            {active && (
              <span
                aria-hidden="true"
                style={{
                  position: "absolute",
                  top: 0,
                  left: "50%",
                  transform: "translateX(-50%)",
                  width: 24,
                  height: 2,
                  borderRadius: 999,
                  background: "var(--accent)",
                }}
              />
            )}
            <item.icon
              size={22}
              strokeWidth={active ? 2.0 : 1.6}
            />
            <span
              style={{
                fontFamily: "var(--trove-sans, sans-serif)",
                fontSize: 10,
                fontWeight: active ? 600 : 400,
                letterSpacing: "0.01em",
              }}
            >
              {item.label}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
