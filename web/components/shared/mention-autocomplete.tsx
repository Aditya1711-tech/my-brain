"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Plus } from "lucide-react";

const DEBOUNCE_MS = 200;
const MAX_ENTITY_SUGGESTIONS = 5;
const MAX_TAG_SUGGESTIONS = 5;
const NEW_ENTITY_MIN_CHARS = 2;

interface EntitySuggestion {
  id: string;
  canonical_name: string;
}

interface ActiveToken {
  type: "@" | "#";
  query: string;
  tokenStart: number; // index of the @ or # sigil in the full text
}

export interface ResolvedMention {
  mention_text: string; // e.g. "@Sunita Sharma"
  entity_id: string;
}

interface MentionAutocompleteProps {
  value: string;
  onChange: (newValue: string) => void;
  onMentionResolved?: (mention: ResolvedMention) => void;
  rows?: number;
  placeholder?: string;
  maxLength?: number;
  autoFocus?: boolean;
  textareaStyle?: React.CSSProperties;
}

/**
 * Textarea with inline @mention and #tag autocomplete.
 *
 * @mention — queries entities (deleted_at IS NULL) debounced 200ms; shows up to 5
 *   existing-entity suggestions + "Create new entity: X" option (≥2 chars typed).
 *   On existing-entity pick: calls onMentionResolved and inserts @CanonicalName.
 *   On "Create new entity" pick: inserts @name as unresolved text; backend
 *   (ND-B-04) routes it through entity_resolver.resolve_and_persist() on save.
 *
 * #tag — lazy-loads all tags from documents.metadata.tags on first # press, then
 *   filters client-side; on pick inserts the full #tag.
 *
 * Keyboard: ↑/↓ navigate; Enter/Tab confirm; Escape dismiss.
 * Dismiss on click-outside.
 */
export function MentionAutocomplete({
  value,
  onChange,
  onMentionResolved,
  rows = 4,
  placeholder,
  maxLength,
  autoFocus,
  textareaStyle,
}: MentionAutocompleteProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const [activeToken, setActiveToken] = useState<ActiveToken | null>(null);
  const [entitySuggestions, setEntitySuggestions] = useState<EntitySuggestion[]>([]);
  const [allTags, setAllTags] = useState<string[]>([]);
  const [tagSuggestions, setTagSuggestions] = useState<string[]>([]);
  const [tagsLoaded, setTagsLoaded] = useState(false);
  const [highlighted, setHighlighted] = useState(0);

  // ── Token detection ──────────────────────────────────────────────────────

  const detectToken = useCallback(
    (text: string, cursorPos: number): ActiveToken | null => {
      const textBefore = text.slice(0, cursorPos);
      const lastAt = textBefore.lastIndexOf("@");
      const lastHash = textBefore.lastIndexOf("#");
      const triggerPos = Math.max(lastAt, lastHash);
      if (triggerPos === -1) return null;

      const triggerChar = textBefore[triggerPos] as "@" | "#";
      const afterTrigger = textBefore.slice(triggerPos + 1);

      // Sigil must be at start of string or preceded by whitespace
      if (triggerPos > 0 && !/[\s\n]/.test(textBefore[triggerPos - 1])) return null;

      // Token ends at any whitespace/newline (the user left the token context)
      if (/[\s\n]/.test(afterTrigger)) return null;

      // # tokens: only word chars allowed
      if (triggerChar === "#" && afterTrigger.length > 0 && /\W/.test(afterTrigger)) return null;

      return { type: triggerChar, query: afterTrigger, tokenStart: triggerPos };
    },
    [],
  );

  // ── Textarea event handlers ───────────────────────────────────────────────

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const text = e.target.value;
      if (maxLength !== undefined && text.length > maxLength) return;
      onChange(text);
      const cursor = e.target.selectionStart ?? text.length;
      const token = detectToken(text, cursor);
      setActiveToken(token);
      setHighlighted(0);
    },
    [onChange, maxLength, detectToken],
  );

  const handleKeyUp = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Re-detect on cursor movement (arrow keys, mouse click handled via click event)
      if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
        const cursor = textareaRef.current?.selectionStart ?? 0;
        setActiveToken(detectToken(value, cursor));
        setHighlighted(0);
      }
    },
    [value, detectToken],
  );

  // ── Dropdown counts ───────────────────────────────────────────────────────

  const showCreateNew =
    activeToken?.type === "@" && (activeToken.query.length ?? 0) >= NEW_ENTITY_MIN_CHARS;

  const totalItems =
    activeToken?.type === "@"
      ? entitySuggestions.length + (showCreateNew ? 1 : 0)
      : tagSuggestions.length;

  // ── Keyboard navigation ───────────────────────────────────────────────────

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (!activeToken || totalItems === 0) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlighted((h) => (h + 1) % totalItems);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlighted((h) => (h - 1 + totalItems) % totalItems);
      } else if (e.key === "Enter" || e.key === "Tab") {
        if (activeToken && totalItems > 0) {
          e.preventDefault();
          triggerHighlighted();
        }
      } else if (e.key === "Escape") {
        setActiveToken(null);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeToken, totalItems, highlighted],
  );

  // ── Insertion helpers ─────────────────────────────────────────────────────

  const insertToken = useCallback(
    (insertText: string) => {
      if (!activeToken) return;
      const before = value.slice(0, activeToken.tokenStart);
      const after = value.slice(activeToken.tokenStart + 1 + activeToken.query.length);
      const newValue = before + insertText + " " + after;
      onChange(newValue);
      setActiveToken(null);
      setEntitySuggestions([]);
      setTagSuggestions([]);
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (el) {
          const pos = before.length + insertText.length + 1; // +1 for trailing space
          el.setSelectionRange(pos, pos);
          el.focus();
        }
      });
    },
    [value, onChange, activeToken],
  );

  const selectEntity = useCallback(
    (entity: EntitySuggestion) => {
      insertToken(`@${entity.canonical_name}`);
      onMentionResolved?.({
        mention_text: `@${entity.canonical_name}`,
        entity_id: entity.id,
      });
    },
    [insertToken, onMentionResolved],
  );

  const createNewEntityMention = useCallback(
    (name: string) => {
      // Insert as unresolved text; the backend (ND-B-04 /note-reintegrate) will
      // route this through entity_resolver.resolve_and_persist() on save.
      insertToken(`@${name}`);
    },
    [insertToken],
  );

  const selectTag = useCallback(
    (tag: string) => {
      insertToken(`#${tag}`);
    },
    [insertToken],
  );

  const triggerHighlighted = useCallback(() => {
    if (!activeToken) return;
    if (activeToken.type === "@") {
      if (highlighted < entitySuggestions.length) {
        selectEntity(entitySuggestions[highlighted]);
      } else if (showCreateNew) {
        createNewEntityMention(activeToken.query);
      }
    } else {
      if (highlighted < tagSuggestions.length) {
        selectTag(tagSuggestions[highlighted]);
      }
    }
  }, [activeToken, highlighted, entitySuggestions, tagSuggestions, showCreateNew, selectEntity, createNewEntityMention, selectTag]);

  // ── Entity fetch (debounced) ──────────────────────────────────────────────

  useEffect(() => {
    if (!activeToken || activeToken.type !== "@" || activeToken.query.length === 0) {
      setEntitySuggestions([]);
      return;
    }
    const timer = setTimeout(async () => {
      const supabase = createClient();
      const { data } = await supabase
        .from("entities")
        .select("id, canonical_name")
        .is("deleted_at", null) // never suggest merged entities
        .ilike("canonical_name", `%${activeToken.query}%`)
        .limit(MAX_ENTITY_SUGGESTIONS);
      setEntitySuggestions(data ?? []);
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [activeToken?.query, activeToken?.type]);

  // ── Tag fetch (lazy, once per mount when # is first typed) ────────────────

  useEffect(() => {
    if (activeToken?.type !== "#" || tagsLoaded) return;
    setTagsLoaded(true);
    const supabase = createClient();
    supabase
      .from("documents")
      .select("metadata")
      .then(({ data }) => {
        const tags = [
          ...new Set(
            (data ?? []).flatMap(
              (d) => (d.metadata as { tags?: string[] } | null)?.tags ?? [],
            ),
          ),
        ].sort();
        setAllTags(tags);
      });
  }, [activeToken?.type, tagsLoaded]);

  useEffect(() => {
    if (activeToken?.type !== "#") { setTagSuggestions([]); return; }
    const q = activeToken.query.toLowerCase();
    setTagSuggestions(
      allTags.filter((t) => t.toLowerCase().includes(q)).slice(0, MAX_TAG_SUGGESTIONS),
    );
  }, [activeToken, allTags]);

  // ── Click-outside dismissal ───────────────────────────────────────────────

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        textareaRef.current !== e.target
      ) {
        setActiveToken(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Dropdown visibility ───────────────────────────────────────────────────

  const showDropdown =
    activeToken !== null &&
    (activeToken.type === "@"
      ? entitySuggestions.length > 0 || showCreateNew
      : tagSuggestions.length > 0);

  return (
    <div style={{ position: "relative" }}>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onKeyUp={handleKeyUp}
        rows={rows}
        placeholder={placeholder}
        autoFocus={autoFocus}
        style={textareaStyle}
        aria-autocomplete="list"
        aria-haspopup={showDropdown ? "listbox" : undefined}
      />

      {showDropdown && (
        <div
          ref={dropdownRef}
          role="listbox"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            zIndex: 50,
            marginTop: 2,
            borderRadius: 8,
            border: "1px solid var(--border-faint)",
            background: "var(--bg-elevated)",
            boxShadow: "var(--trove-shadow-md, 0 4px 16px rgba(0,0,0,0.15))",
            overflow: "hidden",
          }}
        >
          {activeToken.type === "@" && (
            <>
              {entitySuggestions.map((ent, i) => (
                <DropdownItem
                  key={ent.id}
                  highlighted={i === highlighted}
                  onMouseEnter={() => setHighlighted(i)}
                  onMouseDown={(e) => { e.preventDefault(); selectEntity(ent); }}
                  hasDivider={i < entitySuggestions.length - 1 || showCreateNew}
                >
                  <span style={{ fontWeight: 500 }}>{ent.canonical_name}</span>
                </DropdownItem>
              ))}
              {showCreateNew && (
                <DropdownItem
                  highlighted={highlighted === entitySuggestions.length}
                  onMouseEnter={() => setHighlighted(entitySuggestions.length)}
                  onMouseDown={(e) => { e.preventDefault(); createNewEntityMention(activeToken.query); }}
                  accent
                >
                  <Plus aria-hidden="true" size={12} style={{ flexShrink: 0 }} />
                  Create new entity:{" "}
                  <strong style={{ marginLeft: 3 }}>{activeToken.query}</strong>
                </DropdownItem>
              )}
            </>
          )}

          {activeToken.type === "#" &&
            tagSuggestions.map((tag, i) => (
              <DropdownItem
                key={tag}
                highlighted={i === highlighted}
                onMouseEnter={() => setHighlighted(i)}
                onMouseDown={(e) => { e.preventDefault(); selectTag(tag); }}
                hasDivider={i < tagSuggestions.length - 1}
              >
                <span style={{ color: "var(--fg-subtle)", marginRight: 1 }}>#</span>
                {tag}
              </DropdownItem>
            ))}
        </div>
      )}
    </div>
  );
}

// ── Small presentational helper ───────────────────────────────────────────────

interface DropdownItemProps {
  highlighted: boolean;
  onMouseEnter: () => void;
  onMouseDown: React.MouseEventHandler;
  hasDivider?: boolean;
  accent?: boolean;
  children: React.ReactNode;
}

function DropdownItem({
  highlighted,
  onMouseEnter,
  onMouseDown,
  hasDivider = false,
  accent = false,
  children,
}: DropdownItemProps) {
  return (
    <button
      role="option"
      aria-selected={highlighted}
      onMouseEnter={onMouseEnter}
      onMouseDown={onMouseDown}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        width: "100%",
        textAlign: "left",
        padding: "8px 12px",
        fontSize: 13,
        color: accent
          ? highlighted ? "var(--accent-ink)" : "var(--fg-subtle)"
          : highlighted ? "var(--fg-strong)" : "var(--fg)",
        background: highlighted
          ? accent ? "var(--accent-soft)" : "var(--bg-subtle)"
          : "transparent",
        border: "none",
        borderBottom: hasDivider ? "1px solid var(--border-faint)" : "none",
        cursor: "pointer",
        transition: "background 80ms",
      }}
    >
      {children}
    </button>
  );
}
