"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Loader2, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";

const NOTE_MAX = 2000;

interface ResolvedMention {
  mention_text: string;
  entity_id: string;
  canonical_name: string;
}

interface NotesPanelProps {
  documentId: string;
  initialNote: string | null;
}

export function NotesPanel({ documentId, initialNote }: NotesPanelProps) {
  const [note, setNote] = useState(initialNote ?? "");
  const [resolvedMentions, setResolvedMentions] = useState<ResolvedMention[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

  // Load resolved @mention rows (written by ND-C-02 mention resolver)
  useEffect(() => {
    const supabase = createClient();
    supabase
      .from("note_entity_mentions")
      .select("mention_text, entity_id")
      .eq("document_id", documentId)
      .then(async ({ data: mentionRows }) => {
        if (!mentionRows || mentionRows.length === 0) return;
        const entityIds = mentionRows.map((r: { entity_id: string }) => r.entity_id);
        const { data: entityRows } = await supabase
          .from("entities")
          .select("id, canonical_name")
          .in("id", entityIds)
          .is("deleted_at", null); // never show merged entities

        if (entityRows) {
          const merged: ResolvedMention[] = mentionRows.map(
            (r: { mention_text: string; entity_id: string }) => ({
              mention_text: r.mention_text,
              entity_id: r.entity_id,
              canonical_name:
                entityRows.find((e: { id: string }) => e.id === r.entity_id)
                  ?.canonical_name ?? r.mention_text,
            }),
          );
          setResolvedMentions(merged);
        }
      });
  }, [documentId]);

  const handleEdit = () => {
    setEditText(note);
    setIsEditing(true);
    setSaveStatus("idle");
  };

  const handleCancel = () => {
    setIsEditing(false);
    setSaveStatus("idle");
  };

  const handleSave = async () => {
    setSaveStatus("saving");
    try {
      const res = await fetch(`/api/documents/${documentId}/note`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_note: editText }),
      });
      if (res.ok) {
        setNote(editText);
        setIsEditing(false);
        setSaveStatus("saved");
        setTimeout(() => setSaveStatus("idle"), 2000);
      } else {
        setSaveStatus("error");
      }
    } catch {
      setSaveStatus("error");
    }
  };

  return (
    <div
      style={{
        borderRadius: 10,
        border: "1px solid var(--border-faint)",
        background: "var(--bg-elevated)",
        boxShadow: "var(--trove-shadow-sm)",
        overflow: "hidden",
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--border-faint)",
          padding: "12px 16px",
        }}
      >
        <h3
          style={{
            fontFamily: "var(--trove-sans, sans-serif)",
            fontWeight: 600,
            fontSize: 13,
            color: "var(--fg-strong)",
            margin: 0,
          }}
        >
          Your note
        </h3>
        {!isEditing && (
          <button
            aria-label="Edit note"
            onClick={handleEdit}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              fontSize: 12,
              color: "var(--fg-subtle)",
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: "2px 6px",
              borderRadius: 5,
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.background = "var(--bg-subtle)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.background = "none";
            }}
          >
            <Pencil aria-hidden="true" size={12} />
            Edit
          </button>
        )}
        {saveStatus === "saved" && (
          <span style={{ fontSize: 12, color: "var(--status-ready-fg)" }}>
            Note saved
          </span>
        )}
      </div>

      {/* Body */}
      <div style={{ padding: "12px 16px" }}>
        {isEditing ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {/* ND-A-04 will add @mention autocomplete here */}
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value.slice(0, NOTE_MAX))}
              rows={4}
              placeholder={`Add context about this document…\nUse @Name to link to people, #tag to tag`}
              style={{
                width: "100%",
                resize: "vertical",
                borderRadius: 7,
                border: "1px solid var(--border-faint)",
                background: "var(--bg-subtle)",
                color: "var(--fg)",
                fontSize: 13,
                padding: "8px 10px",
                fontFamily: "inherit",
                outline: "none",
                boxSizing: "border-box",
              }}
              autoFocus
            />
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span
                style={{
                  fontSize: 11,
                  color:
                    editText.length > NOTE_MAX * 0.9
                      ? "var(--status-error-fg)"
                      : "var(--fg-muted)",
                }}
              >
                {editText.length}/{NOTE_MAX}
              </span>
              <div style={{ display: "flex", gap: 6 }}>
                <Button variant="ghost" size="sm" onClick={handleCancel}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={saveStatus === "saving"}
                >
                  {saveStatus === "saving" ? (
                    <>
                      <Loader2
                        aria-hidden="true"
                        size={12}
                        style={{ marginRight: 5, animation: "k-spin 1.2s linear infinite" }}
                      />
                      Saving…
                    </>
                  ) : (
                    "Save"
                  )}
                </Button>
              </div>
            </div>
            {saveStatus === "error" && (
              <p style={{ fontSize: 12, color: "var(--status-error-fg)", margin: 0 }}>
                Failed to save note. Please try again.
              </p>
            )}
            <p style={{ fontSize: 11, color: "var(--fg-muted)", margin: 0 }}>
              Saving updates the knowledge graph. Existing connections from this document are not removed.
            </p>
          </div>
        ) : note ? (
          <p
            style={{
              fontSize: 13,
              color: "var(--fg)",
              lineHeight: 1.6,
              margin: 0,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {renderNoteTokens(note, resolvedMentions)}
          </p>
        ) : (
          <p style={{ fontSize: 13, color: "var(--fg-muted)", margin: 0, fontStyle: "italic" }}>
            No note added. Click Edit to add context about this document.
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * Tokenize note text, rendering resolved @mentions as accent chips,
 * unresolved @text in muted colour, and #tags as small tag chips.
 * ND-A-04 will add autocomplete-driven resolution; this renderer already
 * handles resolved mentions via the `resolvedMentions` list.
 */
function renderNoteTokens(text: string, resolvedMentions: ResolvedMention[]) {
  // Split on @word or #word tokens (non-space sequences after @ / word chars after #)
  const parts = text.split(/(@\S+|#\w+)/g);

  return parts.map((part, i) => {
    if (part.startsWith("@")) {
      const resolved = resolvedMentions.find((m) => m.mention_text === part);
      if (resolved) {
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              background: "var(--accent-soft)",
              color: "var(--accent-ink)",
              borderRadius: 4,
              padding: "1px 6px",
              fontSize: 12,
              fontWeight: 500,
              margin: "0 1px",
            }}
          >
            {resolved.canonical_name}
          </span>
        );
      }
      // Unresolved — plain muted text
      return (
        <span key={i} style={{ color: "var(--fg-muted)" }}>
          {part}
        </span>
      );
    }

    if (part.startsWith("#")) {
      return (
        <span
          key={i}
          style={{
            display: "inline-block",
            background: "var(--bg-subtle)",
            color: "var(--fg-subtle)",
            border: "1px solid var(--border-faint)",
            borderRadius: 4,
            padding: "0px 5px",
            fontSize: 11,
            fontWeight: 500,
            margin: "0 1px",
          }}
        >
          {part}
        </span>
      );
    }

    return part;
  });
}
