"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { createClient } from "@/lib/supabase/client";
import { ALLOWED_MIME_TYPES, MAX_FILE_SIZE } from "@/lib/constants";
import { computeFileHash } from "@/lib/utils/file";
import { Upload, FileUp, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { toast } from "sonner";

interface UploadFile {
  file: File;
  status: "pending" | "uploading" | "done" | "error";
  progress: number;
  error?: string;
}

interface DropzoneProps {
  onUploadComplete?: () => void;
}

const NOTE_MAX = 2000;

export function Dropzone({ onUploadComplete }: DropzoneProps) {
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [userNote, setUserNote] = useState("");

  const updateFile = useCallback(
    (index: number, update: Partial<UploadFile>) => {
      setFiles((prev) =>
        prev.map((f, i) => (i === index ? { ...f, ...update } : f)),
      );
    },
    [],
  );

  const uploadFile = useCallback(
    async (uploadFile: UploadFile, index: number, note?: string) => {
      const { file } = uploadFile;
      updateFile(index, { status: "uploading", progress: 10 });

      try {
        // 1. Compute hash
        const fileHash = await computeFileHash(file);
        updateFile(index, { progress: 30 });

        // 2. Get current user
        const supabase = createClient();
        const {
          data: { user },
        } = await supabase.auth.getUser();
        if (!user) throw new Error("Not authenticated");

        // 3. Upload to Supabase Storage
        const storagePath = `${user.id}/${fileHash}/${file.name}`;
        const { error: uploadError } = await supabase.storage
          .from("user-uploads")
          .upload(storagePath, file, { upsert: false });

        if (uploadError && !uploadError.message.includes("already exists")) {
          throw new Error(uploadError.message);
        }
        updateFile(index, { progress: 70 });

        // 4. Call BFF to create document record + enqueue
        const body: Record<string, unknown> = {
          file_hash: fileHash,
          original_filename: file.name,
          mime_type: file.type,
          size_bytes: file.size,
          storage_path: storagePath,
        };
        if (note) body.user_note = note;

        const res = await fetch("/api/documents", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        if (!res.ok) {
          const resBody = await res.json().catch(() => ({}));
          throw new Error(resBody.error ?? `Upload failed (${res.status})`);
        }

        updateFile(index, { status: "done", progress: 100 });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Upload failed";
        updateFile(index, { status: "error", error: message });
        toast.error(`Failed to upload ${file.name}: ${message}`);
      }
    },
    [updateFile],
  );

  const onDrop = useCallback(
    (accepted: File[]) => {
      const newFiles: UploadFile[] = accepted
        .filter((f) => {
          if (!ALLOWED_MIME_TYPES.has(f.type)) {
            toast.error(`Unsupported file type: ${f.name}`);
            return false;
          }
          if (f.size > MAX_FILE_SIZE) {
            toast.error(`File too large: ${f.name} (max 50MB)`);
            return false;
          }
          return true;
        })
        .map((file) => ({ file, status: "pending" as const, progress: 0 }));

      const startIndex = files.length;
      setFiles((prev) => [...prev, ...newFiles]);

      // Capture note at drop time so all files in this batch share the same note
      const noteForBatch = userNote.trim() || undefined;

      // Start uploading each file
      newFiles.forEach((f, i) => {
        uploadFile(f, startIndex + i, noteForBatch);
      });

      // Notify parent when all done
      if (newFiles.length > 0) {
        Promise.allSettled(newFiles.map((f, i) => uploadFile(f, startIndex + i, noteForBatch))).then(
          () => onUploadComplete?.(),
        );
      }
    },
    [files.length, uploadFile, onUploadComplete, userNote],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: Object.fromEntries(
      Array.from(ALLOWED_MIME_TYPES).map((mime) => [mime, []]),
    ),
    maxSize: MAX_FILE_SIZE,
  });

  return (
    <div className="space-y-3">
      <div
        {...getRootProps()}
        className="flex cursor-pointer flex-col items-center justify-center rounded-[10px] border-2 border-dashed p-8 transition-colors"
        style={{
          borderColor: isDragActive ? "var(--accent)" : "var(--border-strong)",
          background: isDragActive ? "var(--accent-soft)" : "transparent",
        }}
      >
        <input {...getInputProps()} />
        <Upload
          className="mb-3 h-7 w-7"
          style={{ color: isDragActive ? "var(--accent-ink)" : "var(--fg-subtle)" }}
        />
        <p className="text-sm font-medium" style={{ color: "var(--fg-strong)" }}>
          {isDragActive ? "Drop to add to your trove" : "Drag files here, or click to browse"}
        </p>
        <p className="mt-1 text-xs" style={{ color: "var(--fg-subtle)" }}>
          PDF · images · DOCX · XLSX · PPTX · CSV · TXT · max 50 MB
        </p>
      </div>

      {/* Notes textarea */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <label
            htmlFor="upload-note"
            style={{ fontSize: 12, fontWeight: 500, color: "var(--fg-subtle)" }}
          >
            Add a note <span style={{ fontWeight: 400 }}>(optional)</span>
          </label>
          <span
            style={{
              fontSize: 11,
              color: userNote.length > NOTE_MAX * 0.9 ? "var(--status-error-fg)" : "var(--fg-muted)",
            }}
          >
            {userNote.length}/{NOTE_MAX}
          </span>
        </div>
        <textarea
          id="upload-note"
          value={userNote}
          onChange={(e) => setUserNote(e.target.value.slice(0, NOTE_MAX))}
          rows={3}
          placeholder={`e.g. "This is my mother's passport"\nUse @Name to link to people, #tag to tag`}
          style={{
            width: "100%",
            resize: "vertical",
            borderRadius: 8,
            border: "1px solid var(--border-faint)",
            background: "var(--bg-elevated)",
            color: "var(--fg)",
            fontSize: 13,
            padding: "8px 10px",
            fontFamily: "inherit",
            outline: "none",
            boxSizing: "border-box",
          }}
        />
        <p style={{ fontSize: 11, color: "var(--fg-muted)", margin: 0 }}>
          The note helps the system understand context. Saving a note updates the knowledge graph.
        </p>
      </div>

      {/* Upload progress */}
      {files.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {files.map((f, i) => (
            <div
              key={`${f.file.name}-${i}`}
              style={{
                borderRadius: 8,
                border: "1px solid var(--border-faint)",
                background: "var(--bg-elevated)",
                overflow: "hidden",
                animation: "k-fade-in 200ms var(--trove-ease-out, ease-out) both",
                animationDelay: `${i * 50}ms`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "8px 12px",
                }}
              >
                <FileUp aria-hidden="true" size={14} style={{ flexShrink: 0, color: "var(--fg-subtle)" }} />
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 13, color: "var(--fg)" }}>
                  {f.file.name}
                </span>
                {f.status === "uploading" && (
                  <Loader2 aria-hidden="true" size={14} style={{ color: "var(--accent)", animation: "k-spin 1.2s linear infinite", flexShrink: 0 }} />
                )}
                {f.status === "done" && (
                  <CheckCircle2
                    aria-hidden="true"
                    size={14}
                    style={{
                      color: "var(--status-ready-dot)",
                      flexShrink: 0,
                      animation: "k-pulse 0.6s var(--trove-ease-out, ease-out) 1",
                    }}
                  />
                )}
                {f.status === "error" && (
                  <XCircle aria-hidden="true" size={14} style={{ color: "var(--status-error-dot)", flexShrink: 0 }} />
                )}
              </div>
              {/* Progress bar */}
              {f.status === "uploading" && (
                <div style={{ height: 2, background: "var(--bg-subtle)", width: "100%" }}>
                  <div
                    style={{
                      height: "100%",
                      background: "var(--accent)",
                      width: `${f.progress}%`,
                      transition: "width 300ms var(--trove-ease-out, ease-out)",
                    }}
                  />
                </div>
              )}
              {f.status === "done" && (
                <div style={{ height: 2, background: "var(--status-ready-dot)", width: "100%" }} />
              )}
              {f.status === "error" && f.error && (
                <p style={{ fontSize: 11, color: "var(--status-error-fg)", padding: "2px 12px 6px", fontFamily: "var(--trove-sans, sans-serif)" }}>
                  {f.error}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
