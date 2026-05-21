"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { createClient } from "@/lib/supabase/client";
import { ALLOWED_MIME_TYPES, MAX_FILE_SIZE, MIME_TO_FILE_TYPE } from "@/lib/constants";
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

export function Dropzone({ onUploadComplete }: DropzoneProps) {
  const [files, setFiles] = useState<UploadFile[]>([]);

  const updateFile = useCallback(
    (index: number, update: Partial<UploadFile>) => {
      setFiles((prev) =>
        prev.map((f, i) => (i === index ? { ...f, ...update } : f)),
      );
    },
    [],
  );

  const uploadFile = useCallback(
    async (uploadFile: UploadFile, index: number) => {
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
        const res = await fetch("/api/documents", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            file_hash: fileHash,
            original_filename: file.name,
            mime_type: file.type,
            size_bytes: file.size,
            storage_path: storagePath,
          }),
        });

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.error ?? `Upload failed (${res.status})`);
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

      // Start uploading each file
      newFiles.forEach((f, i) => {
        uploadFile(f, startIndex + i);
      });

      // Notify parent when all done
      if (newFiles.length > 0) {
        Promise.allSettled(newFiles.map((f, i) => uploadFile(f, startIndex + i))).then(
          () => onUploadComplete?.(),
        );
      }
    },
    [files.length, uploadFile, onUploadComplete],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: Object.fromEntries(
      Array.from(ALLOWED_MIME_TYPES).map((mime) => [mime, []]),
    ),
    maxSize: MAX_FILE_SIZE,
  });

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-muted-foreground/50"
        }`}
      >
        <input {...getInputProps()} />
        <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
        <p className="text-sm font-medium">
          {isDragActive ? "Drop files here" : "Drag & drop files, or click to browse"}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          PDF, images, DOCX, XLSX, PPTX, CSV, TXT (max 50MB)
        </p>
      </div>

      {/* Upload progress */}
      {files.length > 0 && (
        <div className="space-y-2">
          {files.map((f, i) => (
            <div
              key={`${f.file.name}-${i}`}
              className="flex items-center gap-3 rounded-md border px-3 py-2"
            >
              <FileUp className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="flex-1 truncate text-sm">{f.file.name}</span>
              {f.status === "uploading" && (
                <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
              )}
              {f.status === "done" && (
                <CheckCircle2 className="h-4 w-4 text-green-500" />
              )}
              {f.status === "error" && (
                <XCircle className="h-4 w-4 text-red-500" />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
