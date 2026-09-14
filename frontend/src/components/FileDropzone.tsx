import { useId, useRef, useState } from "react";
import { safeHex, useBranding } from "../branding";
import { Icon } from "./icons";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

/** A click-to-browse + drag-and-drop file picker, replacing the bare native
 * `<input type="file">` used across KYC/document upload forms — same
 * underlying `<input>` (still fully keyboard/screen-reader accessible via
 * the visually-hidden input + a proper `<label>`), just styled as an actual
 * drop target instead of the browser's default file-chooser button. */
export function FileDropzone({
  label,
  accept,
  file,
  onChange,
  hint,
  error,
}: {
  label: string;
  accept: string;
  file: File | null;
  onChange: (file: File | null) => void;
  hint?: string;
  error?: string;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const branding = useBranding();
  const primary = safeHex(branding.primaryColor);

  function handleFiles(files: FileList | null) {
    onChange(files?.[0] ?? null);
  }

  function clear(e: React.MouseEvent) {
    e.stopPropagation();
    onChange(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div>
      <label htmlFor={inputId} className="block text-sm font-medium text-slate-700 dark:text-slate-300">
        {label}
      </label>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={0}
        aria-describedby={hint ? `${inputId}-hint` : undefined}
        style={dragActive && primary ? { borderColor: primary, backgroundColor: `${primary}0d` } : undefined}
        className={`mt-1.5 flex min-h-[92px] cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed px-4 py-5 text-center transition-colors ${
          dragActive
            ? primary
              ? ""
              : "border-indigo-400 bg-indigo-50/60 dark:border-indigo-500 dark:bg-indigo-500/10"
            : "border-slate-300 hover:border-slate-400 hover:bg-slate-50 dark:border-slate-700 dark:hover:border-slate-600 dark:hover:bg-slate-800/50"
        }`}
      >
        {file ? (
          <div className="flex items-center gap-2 text-sm">
            <Icon name="documentText" className="h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" />
            <span className="max-w-[16rem] truncate font-medium text-slate-800 dark:text-slate-100">{file.name}</span>
            <span className="shrink-0 text-xs text-slate-400 dark:text-slate-500">({formatBytes(file.size)})</span>
            <button
              type="button"
              onClick={clear}
              className="shrink-0 rounded-full p-0.5 text-slate-400 hover:bg-slate-200 hover:text-rose-600 dark:hover:bg-slate-700"
              aria-label="Remove file"
            >
              <Icon name="close" className="h-3.5 w-3.5" />
            </button>
          </div>
        ) : (
          <>
            <Icon name="archiveBox" className="h-5 w-5 text-slate-300 dark:text-slate-600" />
            <p className="text-sm text-slate-600 dark:text-slate-300">
              <span className="font-medium" style={primary ? { color: primary } : undefined}>
                <span className={primary ? "" : "text-indigo-600 dark:text-indigo-400"}>Browse</span>
              </span>{" "}
              or drag a file here
            </p>
            {hint ? (
              <p id={`${inputId}-hint`} className="text-xs text-slate-400 dark:text-slate-500">
                {hint}
              </p>
            ) : null}
          </>
        )}
      </div>
      {error ? <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">{error}</p> : null}
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={accept}
        onChange={(e) => handleFiles(e.target.files)}
        className="sr-only"
      />
    </div>
  );
}

const MAX_IMAGE_BYTES = 400 * 1024; // 400KB — kept small since it's stored inline as a data URL.

/** Company logo picker — mirrors the KYC document dropzone above, but reads
 * the chosen image as a base64 data: URL instead of uploading it anywhere.
 * `logo_url` is already a plain string column/field end to end (backend and
 * frontend), so a data: URL is a drop-in value for it — no new upload
 * endpoint or file storage needed for what's a small, purely cosmetic
 * asset (unlike KYC documents, §16, which must never be a client-supplied
 * URL — a logo has no isolation/authenticity requirement). */
export function ImageFileField({
  label,
  value,
  onChange,
  hint = "PNG or JPG, up to 400KB",
}: {
  label: string;
  value: string | undefined;
  onChange: (dataUrl: string) => void;
  hint?: string;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const branding = useBranding();
  const primary = safeHex(branding.primaryColor);

  function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Please choose an image file");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError(`Image is too large (${(file.size / 1024).toFixed(0)}KB) — please use one under 400KB`);
      return;
    }
    setError(null);
    const reader = new FileReader();
    reader.onload = () => onChange(String(reader.result));
    reader.readAsDataURL(file);
  }

  return (
    <div>
      <label htmlFor={inputId} className="block text-sm font-medium text-slate-700 dark:text-slate-300">
        {label}
      </label>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={0}
        style={dragActive && primary ? { borderColor: primary, backgroundColor: `${primary}0d` } : undefined}
        className={`mt-1.5 flex min-h-[92px] cursor-pointer items-center gap-3 rounded-lg border-2 border-dashed px-4 py-4 transition-colors ${
          dragActive
            ? primary
              ? ""
              : "border-indigo-400 bg-indigo-50/60 dark:border-indigo-500 dark:bg-indigo-500/10"
            : "border-slate-300 hover:border-slate-400 hover:bg-slate-50 dark:border-slate-700 dark:hover:border-slate-600 dark:hover:bg-slate-800/50"
        }`}
      >
        {value ? (
          <img src={value} alt="Logo preview" className="h-12 w-12 shrink-0 rounded-lg border border-slate-200 object-cover dark:border-slate-700" />
        ) : (
          <Icon name="buildingOffice" className="h-8 w-8 shrink-0 text-slate-300 dark:text-slate-600" />
        )}
        <div className="min-w-0 text-left">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            <span style={primary ? { color: primary } : undefined}>
              <span className={primary ? "" : "text-indigo-600 dark:text-indigo-400"}>{value ? "Change image" : "Browse"}</span>
            </span>{" "}
            {value ? "" : "or drag an image here"}
          </p>
          <p className="text-xs text-slate-400 dark:text-slate-500">{hint}</p>
        </div>
        {value ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onChange("");
              if (inputRef.current) inputRef.current.value = "";
            }}
            className="ml-auto shrink-0 rounded-full p-1 text-slate-400 hover:bg-slate-200 hover:text-rose-600 dark:hover:bg-slate-700"
            aria-label="Remove logo"
          >
            <Icon name="close" className="h-4 w-4" />
          </button>
        ) : null}
      </div>
      {error ? <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">{error}</p> : null}
      <input ref={inputRef} id={inputId} type="file" accept="image/*" onChange={(e) => handleFiles(e.target.files)} className="sr-only" />
    </div>
  );
}
