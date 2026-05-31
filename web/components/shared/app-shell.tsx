"use client";

import { useRef, useState } from "react";
import { type User } from "@supabase/supabase-js";
import { Sidebar } from "@/components/shared/sidebar";

interface AppShellProps {
  user: User;
  children: React.ReactNode;
}

export function AppShell({ user, children }: AppShellProps) {
  const [dragActive, setDragActive] = useState(false);
  const [dragCount, setDragCount] = useState(0);
  const dragDepth = useRef(0);

  // Full-page drag-and-drop — the board intercepts it, overlays show here
  const onDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    const types = Array.from(e.dataTransfer?.types ?? []);
    if (types.includes("Files")) {
      dragDepth.current += 1;
      setDragCount(e.dataTransfer?.items?.length ?? 0);
      setDragActive(true);
    }
  };
  const onDragOver = (e: React.DragEvent) => { e.preventDefault(); };
  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    dragDepth.current -= 1;
    if (dragDepth.current <= 0) {
      dragDepth.current = 0;
      setDragActive(false);
    }
  };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    dragDepth.current = 0;
    setDragActive(false);
    // Files are picked up by the dropzone inside the library page
  };

  return (
    <div
      className="theme-dark"
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      style={{
        height: "100%",
        display: "flex",
        background: "var(--bg-canvas)",
        overflow: "hidden",
      }}
    >
      <Sidebar email={user.email ?? undefined} />

      <main
        style={{
          flex: 1,
          height: "100%",
          overflowY: "auto",
          position: "relative",
        }}
      >
        {children}
      </main>

      {/* Full-page drop overlay */}
      {dragActive && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 60,
            background: "color-mix(in srgb, var(--bg-sunken) 78%, transparent)",
            backdropFilter: "blur(8px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            animation: "k-overlay-in 140ms var(--trove-ease-out, ease-out)",
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              border: "2px dashed var(--accent)",
              borderRadius: 20,
              padding: "48px 64px",
              textAlign: "center",
              background: "var(--accent-soft)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 16,
            }}
          >
            {/* Upload icon */}
            <div
              style={{
                width: 64,
                height: 64,
                borderRadius: 18,
                background: "var(--bg-elevated)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--accent-ink)",
              }}
            >
              <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>
            <p
              style={{
                fontFamily: "var(--trove-serif, Georgia, serif)",
                fontStyle: "italic",
                fontSize: 30,
                color: "var(--fg-strong)",
                letterSpacing: "-0.01em",
              }}
            >
              Drop to add{dragCount > 0 ? ` ${dragCount} file${dragCount > 1 ? "s" : ""}` : " anything"}
            </p>
            <p
              style={{
                fontFamily: "var(--trove-sans, sans-serif)",
                fontSize: 13.5,
                color: "var(--fg-muted)",
              }}
            >
              PDF · images · DOCX · XLSX · PPTX · CSV · TXT · up to 50 MB
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
