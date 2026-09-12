import { useState, useRef, useId } from 'react';
import { Upload, CheckCircle2, X, AlertCircle, Loader2, FileCheck, RefreshCw } from 'lucide-react';
import { uploadAsset } from '../api/client';
import type { UploadResponse } from '../types/api';
import { cn } from '../lib/cn';

interface FileUploadProps {
  id?: string;
  accept?: string;
  assetType: 'model' | 'dataset';
  label?: string;
  description?: string;
  helpText?: string;
  value?: UploadResponse | null;
  onChange?: (upload: UploadResponse | null) => void;
  currentUpload?: UploadResponse | null;
  onUploadSuccess?: (upload: UploadResponse | null) => void;
  onClear?: () => void;
  disabled?: boolean;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

export function FileUpload({
  id: customId,
  accept,
  assetType,
  label,
  description,
  helpText,
  value,
  onChange,
  currentUpload,
  onUploadSuccess,
  onClear,
  disabled = false,
}: FileUploadProps) {
  const generatedId = useId();
  const inputId = customId || generatedId;
  const inputRef = useRef<HTMLInputElement>(null);

  const effectiveValue = value !== undefined ? value : (currentUpload ?? null);
  const handleUpdate = (val: UploadResponse | null) => {
    onChange?.(val);
    onUploadSuccess?.(val);
    if (val === null) onClear?.();
  };

  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  async function handleFile(file: File) {
    if (!file || disabled) return;
    setUploadError(null);
    setIsUploading(true);

    try {
      const result = await uploadAsset(file, assetType);
      handleUpdate(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Upload failed. Please try again.';
      setUploadError(msg);
      handleUpdate(null);
    } finally {
      setIsUploading(false);
      if (inputRef.current) {
        inputRef.current.value = '';
      }
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    if (disabled || isUploading) return;

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    if (!disabled && !isUploading) {
      setIsDragging(true);
    }
  }

  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      inputRef.current?.click();
    }
  }

  return (
    <div className="space-y-1.5">
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={accept}
        disabled={disabled || isUploading}
        onChange={(e) => {
          if (e.target.files && e.target.files[0]) {
            handleFile(e.target.files[0]);
          }
        }}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
      />

      {/* Optional Label / Description header */}
      {(label || description) && (
        <div className="space-y-0.5 mb-1.5">
          {label && <p className="text-xs font-semibold text-1">{label}</p>}
          {description && <p className="text-[11px] text-3">{description}</p>}
        </div>
      )}

      {/* State 1: Uploading */}
      {isUploading && (
        <div className="flex items-center justify-between p-3.5 rounded-lg border border-accent/40 bg-surface-2/60">
          <div className="flex items-center gap-3">
            <Loader2 className="w-4 h-4 text-accent animate-spin flex-shrink-0" />
            <div>
              <p className="text-xs font-medium text-1">Uploading and validating asset…</p>
              <p className="text-[10px] text-3 font-mono mt-0.5">Calculating SHA-256 and enforcing security constraints</p>
            </div>
          </div>
        </div>
      )}

      {/* State 2: Uploaded successfully */}
      {!isUploading && effectiveValue && (
        <div className="flex items-center justify-between p-3 rounded-lg border border-[var(--border)] bg-surface-2/70 hover:border-[var(--border-strong)] transition-colors">
          <div className="flex items-center gap-3 min-w-0 pr-2">
            <div className="w-8 h-8 rounded bg-[var(--green-bg)] text-[var(--green)] flex items-center justify-center flex-shrink-0">
              <FileCheck className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-xs font-semibold text-1 truncate max-w-[240px] sm:max-w-md">
                  {effectiveValue.original_filename}
                </p>
                <span className="text-[10px] font-mono text-3 flex-shrink-0">
                  ({formatBytes(effectiveValue.size_bytes)})
                </span>
              </div>
              <div className="flex items-center gap-2 mt-0.5 text-[10px] font-mono text-3">
                <span className="flex items-center gap-1 text-[var(--green)]">
                  <CheckCircle2 className="w-2.5 h-2.5" />
                  SHA-256: {effectiveValue.sha256.slice(0, 12)}…
                </span>
                {effectiveValue.format && (
                  <span className="px-1.5 py-0.2 rounded bg-surface border border-[var(--border)] uppercase">
                    {effectiveValue.format}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0">
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="px-2 py-1 rounded border border-[var(--border)] text-[11px] font-medium text-2 hover:text-1 hover:bg-surface transition-colors flex items-center gap-1"
              title="Replace file"
            >
              <RefreshCw className="w-3 h-3" />
              <span className="hidden sm:inline">Replace</span>
            </button>
            <button
              type="button"
              onClick={() => {
                handleUpdate(null);
                setUploadError(null);
              }}
              className="p-1 rounded text-3 hover:text-[var(--red)] hover:bg-[var(--red-bg)] transition-colors"
              title="Remove file"
              aria-label="Remove uploaded file"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* State 3: Empty / Dropzone */}
      {!isUploading && !effectiveValue && (
        <div
          role="button"
          tabIndex={disabled ? -1 : 0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={handleKeyDown}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={cn(
            'flex flex-col items-center justify-center p-5 rounded-lg border-2 border-dashed transition-all duration-150 text-center cursor-pointer select-none',
            isDragging
              ? 'border-accent bg-accent-bg'
              : 'border-[var(--border)] bg-surface hover:border-[var(--border-strong)] hover:bg-surface-2/40',
            disabled && 'opacity-50 cursor-not-allowed pointer-events-none',
          )}
        >
          <div className="w-8 h-8 rounded-full bg-surface-2 border border-[var(--border)] flex items-center justify-center mb-2 text-3">
            <Upload className="w-3.5 h-3.5" />
          </div>
          <p className="text-xs text-1">
            <span className="font-semibold text-accent hover:underline">Click to browse</span> or drag and drop
          </p>
          {helpText && <p className="text-[11px] text-3 mt-1">{helpText}</p>}
        </div>
      )}

      {/* Error state */}
      {uploadError && (
        <div className="flex items-center gap-1.5 text-xs text-[var(--red)] pt-0.5">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          <span>{uploadError}</span>
        </div>
      )}
    </div>
  );
}
