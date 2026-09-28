import { useParams, Link, useOutletContext } from 'react-router-dom';
import { useEffect, useState } from 'react';
import type { AssessmentWorkspaceContext } from '../layouts/AssessmentWorkspaceLayout';
import {
  Copy,
  Check,
  FileText,
  Code2,
  ChevronDown,
  ChevronUp,
  FileSearch,
  Hash,
  ArrowRight,
  Eye,
  Maximize2,
  X,
  ShieldAlert,
  Layers,
  Image as ImageIcon,
  ExternalLink,
} from 'lucide-react';
import type {
  EvidenceResponse,
  EvidenceSchema,
  EvidencePreviewResponse,
  EvidenceImagePreview
} from '../types/api';
import { getEvidence, getEvidencePreview, resolveApiUrl } from '../api/client';
import { ErrorState } from '../components/ErrorState';
import { AssessmentSubNav } from '../components/AssessmentSubNav';
import { cn } from '../lib/cn';

type EvidenceTab = 'preview' | 'structured' | 'raw';

function CopyBtn({ value, label }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={e => {
        e.stopPropagation();
        navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        });
      }}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono
        text-3 border border-[var(--border)] hover:text-1 hover:border-[var(--border-strong)]
        bg-surface-2/60 hover:bg-surface-2 transition-colors focus-visible:ring-1"
      title={`Copy ${label ?? 'value'}`}
    >
      {copied ? <Check className="w-3 h-3 text-[var(--green)]" /> : <Copy className="w-3 h-3" />}
      <span>{copied ? 'Copied' : 'Copy'}</span>
    </button>
  );
}

function TruncatedHash({ hash }: { hash: string }) {
  const short = hash.length > 20 ? `${hash.slice(0, 10)}…${hash.slice(-8)}` : hash;
  return (
    <div className="flex items-center gap-2">
      <code className="text-xs font-mono text-2 px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)]" title={hash}>
        {short}
      </code>
      <CopyBtn value={hash} label="Hash" />
    </div>
  );
}

function KVRow({ k, v }: { k: string; v: unknown }) {
  const isHash = k.toLowerCase().includes('sha') || k.toLowerCase().includes('hash') || k.toLowerCase().includes('fingerprint');

  if (isHash && typeof v === 'string') {
    return (
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 py-2.5 border-b border-[var(--border)] last:border-0">
        <span className="text-xs font-mono text-3 uppercase">{k.replace(/_/g, ' ')}</span>
        <TruncatedHash hash={v} />
      </div>
    );
  }

  const isObjectOrArray = typeof v === 'object' && v !== null;
  const display = isObjectOrArray ? JSON.stringify(v, null, 2) : String(v ?? '—');
  const isLong = display.length > 60 || isObjectOrArray;

  return (
    <div className={cn(
      'py-2.5 border-b border-[var(--border)] last:border-0 flex gap-3',
      isLong ? 'flex-col' : 'flex-col sm:flex-row sm:items-center justify-between'
    )}>
      <span className="text-xs font-mono text-3 uppercase flex-shrink-0">
        {k.replace(/_/g, ' ')}
      </span>
      {isObjectOrArray ? (
        <pre className="text-[11px] font-mono text-2 bg-surface-2/60 p-2.5 rounded border border-[var(--border)] overflow-x-auto leading-relaxed max-h-48">
          {display}
        </pre>
      ) : (
        <code className="text-xs font-mono text-1 break-all">
          {display}
        </code>
      )}
    </div>
  );
}

/* ── Lightbox Image Modal ── */
function ImageLightboxModal({
  image,
  onClose,
}: {
  image: EvidenceImagePreview;
  onClose: () => void;
}) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        className="relative max-w-4xl w-full bg-surface border border-[var(--border)] rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border)] bg-surface-2/60">
          <div className="flex items-center gap-3 min-w-0">
            <ImageIcon className="w-4 h-4 text-accent flex-shrink-0" />
            <span className="font-mono text-xs font-bold text-1 truncate max-w-md">
              {image.file_name}
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-accent/10 border border-accent/20 text-accent font-semibold hidden sm:inline">
              High-Resolution Image Inspector
            </span>
            {image.width && image.height && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface border border-[var(--border)] text-3">
                {image.width} × {image.height} px
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-3 hover:text-1 hover:bg-surface-2 transition-colors"
            title="Close viewer (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Image Viewport */}
        <div className="p-6 bg-surface-2/30 flex items-center justify-center overflow-auto max-h-[70vh]">
          <img
            src={resolveApiUrl(image.preview_url)}
            alt={image.file_name}
            className="max-h-[60vh] max-w-full object-contain rounded-lg border border-[var(--border)] shadow-md bg-black/40"
          />
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3 border-t border-[var(--border)] bg-surface flex flex-wrap items-center justify-between gap-3 text-xs">
          {image.caption && (
            <p className="text-2 font-mono text-[11px]">{image.caption}</p>
          )}
          {image.sha256 && (
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-[10px] text-3 uppercase font-mono">SHA-256</span>
              <code className="text-[11px] font-mono text-2 px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
                {image.sha256}
              </code>
              <CopyBtn value={image.sha256} label="SHA-256" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Image Thumbnail Card ── */
function ImageThumbnailCard({
  image,
  onInspect,
}: {
  image: EvidenceImagePreview;
  onInspect: (img: EvidenceImagePreview) => void;
}) {
  const [loadError, setLoadError] = useState(false);

  return (
    <div className="group border border-[var(--border)] rounded-xl overflow-hidden bg-surface-2/40 hover:border-accent/40 transition-all duration-150 flex flex-col shadow-sm">
      {/* Thumbnail image area */}
      <div
        role="button"
        tabIndex={0}
        title="Inspect full resolution image"
        className="relative aspect-square w-full bg-black/30 flex items-center justify-center overflow-hidden cursor-pointer focus-visible:ring-2 focus-visible:ring-accent"
        onClick={() => onInspect(image)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onInspect(image);
          }
        }}
      >
        {!loadError ? (
          <img
            src={resolveApiUrl(image.preview_url)}
            alt={image.file_name}
            loading="lazy"
            onError={() => setLoadError(true)}
            className="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
          />
        ) : (
          <div className="p-4 text-center text-3 space-y-1">
            <ImageIcon className="w-6 h-6 mx-auto opacity-50" />
            <span className="text-[10px] font-mono block">Preview Unavailable</span>
          </div>
        )}

        {/* Hover zoom overlay */}
        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity duration-150 flex items-center justify-center gap-2 text-white">
          <span className="text-xs font-medium inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-black/60 backdrop-blur-sm border border-white/20">
            <Maximize2 className="w-3.5 h-3.5" />
            <span>Inspect</span>
          </span>
        </div>
      </div>

      {/* Details bar */}
      <div className="p-3 border-t border-[var(--border)] bg-surface flex flex-col gap-1.5 text-xs">
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-[11px] font-bold text-1 truncate" title={image.file_name}>
            {image.file_name}
          </span>
          <CopyBtn value={image.file_name} label="File Name" />
        </div>

        <div className="flex items-center justify-between gap-2 text-[10px] font-mono text-3">
          <span>{image.width && image.height ? `${image.width}×${image.height}px` : 'Image file'}</span>
          {image.size_bytes ? (
            <span>{Math.round(image.size_bytes / 1024)} KB</span>
          ) : null}
        </div>

        {image.caption && (
          <span className="text-[10px] text-accent font-mono bg-[var(--accent-bg)] px-1.5 py-0.5 rounded border border-accent/20 truncate">
            {image.caption}
          </span>
        )}
      </div>
    </div>
  );
}

/* ── Evidence Card ── */
export function EvidenceCard({
  ev,
  assessmentId
}: {
  ev: EvidenceSchema;
  assessmentId?: string;
}) {
  const [tab, setTab] = useState<EvidenceTab>('preview');
  const [open, setOpen] = useState(true);
  const [preview, setPreview] = useState<EvidencePreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [lightboxImage, setLightboxImage] = useState<EvidenceImagePreview | null>(null);

  const payload = (ev.data as Record<string, unknown>) ?? {};
  const keys = Object.keys(payload);

  // Fetch preview metadata when assessmentId and evidence_id are present
  useEffect(() => {
    if (!assessmentId || !ev.evidence_id) return;
    let isMounted = true;
    setPreviewLoading(true);

    getEvidencePreview(assessmentId, ev.evidence_id)
      .then(res => {
        if (!isMounted) return;
        setPreview(res);
        setPreviewLoading(false);
      })
      .catch(err => {
        if (!isMounted) return;
        setPreviewError(err instanceof Error ? err.message : 'Preview unavailable');
        setPreviewLoading(false);
      });

    return () => { isMounted = false; };
  }, [assessmentId, ev.evidence_id]);

  const hasImages = preview && preview.images && preview.images.length > 0;
  const isUnsupported = preview?.preview_type === 'unsupported';

  return (
    <div className="border border-[var(--border)] rounded-xl overflow-hidden bg-surface shadow-sm transition-all duration-150 hover:border-[var(--border-strong,var(--border))]">
      {/* Card Header Accordion */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen(o => !o)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setOpen(o => !o);
          }
        }}
        className="w-full flex items-center justify-between gap-4 px-5 py-4 bg-surface hover:bg-surface-2/60 transition-colors text-left cursor-pointer select-none focus-visible:outline-none focus-visible:bg-surface-2"
      >
        <div className="flex items-center gap-4 flex-wrap flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Hash className="w-4 h-4 text-accent flex-shrink-0" />
            <div>
              <p className="text-[10px] font-mono uppercase text-3 font-semibold">Evidence Record</p>
              <div className="flex items-center gap-1.5">
                <code className="text-xs font-mono font-bold text-accent">{ev.evidence_id}</code>
                <CopyBtn value={ev.evidence_id} label="Evidence ID" />
              </div>
            </div>
          </div>

          <div className="border-l border-[var(--border)] pl-4">
            <p className="text-[10px] font-mono uppercase text-3 font-semibold">Artifact Type</p>
            <span className="text-xs font-mono text-1 font-semibold px-2 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
              {ev.evidence_type}
            </span>
          </div>

          <div className="border-l border-[var(--border)] pl-4 hidden md:block">
            <p className="text-[10px] font-mono uppercase text-3 font-semibold">Detector</p>
            <span className="text-xs font-mono text-accent font-bold">
              {ev.detector_id}
            </span>
          </div>

          {ev.finding_id && assessmentId && (
            <div className="border-l border-[var(--border)] pl-4 hidden sm:block">
              <p className="text-[10px] font-mono uppercase text-3 font-semibold">Linked Finding</p>
              <Link
                to={`/assessments/${assessmentId}/findings?q=${encodeURIComponent(ev.finding_id)}`}
                onClick={e => e.stopPropagation()}
                className="inline-flex items-center gap-1 text-xs font-mono text-accent hover:underline font-semibold"
                title="Inspect linked finding in defect registry"
              >
                <span>{ev.finding_id}</span>
                <ExternalLink className="w-3 h-3" />
              </Link>
            </div>
          )}

          {ev.artifact_sha256 && (
            <div className="border-l border-[var(--border)] pl-4 hidden lg:block">
              <p className="text-[10px] font-mono uppercase text-3 font-semibold">SHA-256 Digest</p>
              <code className="text-xs font-mono text-2">
                {ev.artifact_sha256.slice(0, 10)}…{ev.artifact_sha256.slice(-6)}
              </code>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 text-3 flex-shrink-0">
          <span className="text-xs hidden sm:inline text-3">
            {open ? 'Collapse' : 'Inspect'}
          </span>
          {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </div>

      {/* Body: Tabs (Preview, Structured, Raw JSON) */}
      {open && (
        <div className="border-t border-[var(--border)] bg-surface">
          {/* Sub-tabs header */}
          <div className="flex items-center justify-between border-b border-[var(--border)] px-5 bg-surface-2/40 flex-wrap gap-2">
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setTab('preview')}
                className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors',
                  tab === 'preview'
                    ? 'border-accent text-accent font-semibold'
                    : 'border-transparent text-3 hover:text-1'
                )}
              >
                <Eye className="w-3.5 h-3.5" />
                <span>Artifact Preview</span>
                {hasImages && (
                  <span className="ml-1 text-[10px] font-mono px-1.5 py-0.2 rounded-full bg-[var(--accent-bg)] text-accent border border-accent/20">
                    {preview.images.length}
                  </span>
                )}
              </button>

              <button
                type="button"
                onClick={() => setTab('structured')}
                className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors',
                  tab === 'structured'
                    ? 'border-accent text-accent font-semibold'
                    : 'border-transparent text-3 hover:text-1'
                )}
              >
                <FileText className="w-3.5 h-3.5" />
                <span>Structured Inspector</span>
              </button>

              <button
                type="button"
                onClick={() => setTab('raw')}
                className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors',
                  tab === 'raw'
                    ? 'border-accent text-accent font-semibold'
                    : 'border-transparent text-3 hover:text-1'
                )}
              >
                <Code2 className="w-3.5 h-3.5" />
                <span>Raw JSON</span>
              </button>
            </div>

            {/* Copy payload button */}
            <CopyBtn value={JSON.stringify(payload, null, 2)} label="Raw JSON" />
          </div>

          {/* Tab Content */}
          <div className="p-5">
            {/* 1. Artifact Preview Tab */}
            {tab === 'preview' && (
              <div className="space-y-4">
                {previewLoading ? (
                  <div className="p-8 text-center space-y-3 bg-surface-2/20 rounded-xl border border-[var(--border)] animate-pulse">
                    <div className="w-8 h-8 rounded-full bg-surface-2 mx-auto" />
                    <p className="text-xs font-mono text-3">Resolving artifact preview telemetry...</p>
                  </div>
                ) : previewError ? (
                  <div className="p-4 rounded-xl border border-[var(--border)] bg-surface-2/40 text-xs font-mono text-3 space-y-1">
                    <p className="font-semibold text-1">Preview telemetry unavailable</p>
                    <p>{previewError}</p>
                  </div>
                ) : isUnsupported ? (
                  /* Unsupported / Binary State */
                  <div className="p-6 rounded-xl border border-[var(--amber-border,var(--border))] bg-[var(--amber-bg,var(--surface-2))] space-y-3">
                    <div className="flex items-center gap-2.5 text-[var(--amber,#f59e0b)] font-semibold text-sm">
                      <ShieldAlert className="w-5 h-5 flex-shrink-0" />
                      <span>Binary Artifact — Direct Preview Unavailable</span>
                    </div>
                    <p className="text-xs text-2 leading-relaxed">
                      {preview?.unsupported_reason || 'This evidence artifact is a binary file (e.g. serialized tensor weights, ONNX graph, or archive). Inline visual rendering is suppressed for security and performance.'}
                    </p>
                    <div className="pt-2 flex flex-wrap items-center gap-3">
                      {preview?.artifact_sha256 && (
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-mono text-3">SHA-256:</span>
                          <TruncatedHash hash={preview.artifact_sha256} />
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={() => setTab('structured')}
                        className="inline-flex items-center gap-1 text-xs font-mono text-accent hover:underline font-semibold ml-auto"
                      >
                        <span>View Structural Breakdown</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ) : hasImages ? (
                  /* Visual Gallery Preview */
                  <div className="space-y-4">
                    <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] pb-3">
                      <div className="flex items-center gap-2">
                        <ImageIcon className="w-4 h-4 text-accent" />
                        <span className="text-xs font-mono font-bold text-1">
                          {preview.title}
                        </span>
                        <span className="text-[11px] font-mono text-3">
                          ({preview.images.length} verified sample{preview.images.length === 1 ? '' : 's'})
                        </span>
                      </div>
                      <span className="text-[10px] font-mono text-3 uppercase">
                        Click image to expand
                      </span>
                    </div>

                    {/* Image grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                      {preview.images.map((img, idx) => (
                        <ImageThumbnailCard
                          key={`${img.sample_id || idx}-${img.file_name}`}
                          image={img}
                          onInspect={setLightboxImage}
                        />
                      ))}
                    </div>
                  </div>
                ) : preview?.preview_type === 'structured_text' || preview?.preview_type === 'json' ? (
                  /* Text / JSON Preview */
                  <div className="space-y-3">
                    <div className="flex items-center justify-between border-b border-[var(--border)] pb-2">
                      <span className="text-xs font-mono font-bold text-1">
                        {preview.title}
                      </span>
                      {preview.truncated && (
                        <span className="text-[10px] font-mono text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
                          Bounded Preview (Truncated to 64KB)
                        </span>
                      )}
                    </div>
                    <pre className="text-xs font-mono text-2 p-4 rounded-xl bg-surface-2 border border-[var(--border)] overflow-x-auto leading-relaxed max-h-96">
                      {preview.text_content || JSON.stringify(preview.structured_content, null, 2)}
                    </pre>
                  </div>
                ) : (
                  /* Structured Telemetry Preview (Default) */
                  <div className="space-y-4">
                    <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
                      <div className="flex items-center gap-2">
                        <Layers className="w-4 h-4 text-accent" />
                        <span className="text-xs font-mono font-bold text-1">
                          {preview?.title || 'Telemetry & Measurement Preview'}
                        </span>
                      </div>
                      <span className="text-[10px] font-mono text-3">
                        {keys.length} recorded parameters
                      </span>
                    </div>

                    <div className="space-y-1 divide-y divide-[var(--border)]">
                      {keys.map(k => (
                        <KVRow key={k} k={k} v={payload[k]} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 2. Structured Inspector Tab */}
            {tab === 'structured' && (
              keys.length === 0 ? (
                <p className="text-xs text-3 italic">
                  {ev.description || 'No structured key-value payload recorded for this artifact.'}
                </p>
              ) : (
                <div className="space-y-0.5 divide-y divide-[var(--border)]">
                  {keys.map(k => (
                    <KVRow key={k} k={k} v={payload[k]} />
                  ))}
                </div>
              )
            )}

            {/* 3. Raw JSON Tab */}
            {tab === 'raw' && (
              <div className="relative">
                <pre className="text-xs font-mono text-2 overflow-x-auto leading-relaxed bg-surface-2/80 rounded-lg p-4 border border-[var(--border)] max-h-80">
                  {JSON.stringify(payload, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Lightbox Modal */}
      {lightboxImage && (
        <ImageLightboxModal
          image={lightboxImage}
          onClose={() => setLightboxImage(null)}
        />
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   Evidence Page Component
──────────────────────────────────────────────────────────── */
export function Evidence() {
  const { id } = useParams<{ id?: string }>();
  const outletCtx = useOutletContext<AssessmentWorkspaceContext | undefined>();
  const [data, setData] = useState<EvidenceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) { setLoading(false); return; }
    getEvidence(id)
      .then(d => { setData(d); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [id]);

  if (loading) {
    return (
      <div className={outletCtx ? "space-y-4 animate-pulse" : "max-w-5xl mx-auto px-6 py-8 space-y-4 animate-pulse"}>
        <div className="h-10 bg-surface-2 rounded w-1/3" />
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-28 bg-surface-2 rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className={outletCtx ? "" : "max-w-5xl mx-auto px-6 py-8"}>
        <ErrorState title="Could not load assessment evidence" message={error} />
      </div>
    );
  }

  const items = data?.evidence ?? [];

  return (
    <div className={outletCtx ? "space-y-6" : "max-w-5xl mx-auto px-6 py-8 space-y-6"}>
      {/* Sub-navigation only if accessed outside master workspace */}
      {!outletCtx && id && (
        <AssessmentSubNav
          assessmentId={id}
          evidenceCount={items.length}
        />
      )}

      {/* Header */}
      <div className="border-b border-[var(--border)] pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-[11px] font-bold text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
              CRYPTOGRAPHIC PROVENANCE
            </span>
            <span className="text-xs text-3 font-mono">ARTIFACT STORE</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-1 tracking-tight">
            Evidence Artifacts
          </h1>
          <p className="mt-1 text-sm text-2 max-w-2xl leading-relaxed">
            Content-addressed cryptographic hashes, structural AST fingerprints, visual sample clusters, and audit telemetry.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono text-3">
          <span className="px-2.5 py-1 rounded bg-surface-2 border border-[var(--border)]">
            {items.length} artifact{items.length === 1 ? '' : 's'} recorded
          </span>
        </div>
      </div>

      {/* Empty State */}
      {items.length === 0 ? (
        <div className="card p-12 text-center space-y-3 border border-dashed border-[var(--border)]">
          <div className="w-12 h-12 rounded-xl bg-surface-2 text-3 mx-auto flex items-center justify-center">
            <FileSearch className="w-6 h-6" />
          </div>
          <h2 className="text-base font-semibold text-1">No Evidence Artifacts Stored</h2>
          <p className="text-xs text-3 max-w-sm mx-auto leading-relaxed">
            Evidence artifacts are collected automatically when detectors execute on valid model or dataset files.
          </p>
          {id && (
            <div className="pt-2">
              <Link
                to={`/assessments/${id}/result`}
                className="inline-flex items-center gap-1.5 text-xs text-accent font-semibold hover:underline"
              >
                <span>Return to Assessment Overview</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {items.map(ev => (
            <EvidenceCard key={ev.evidence_id} ev={ev} assessmentId={id} />
          ))}
        </div>
      )}
    </div>
  );
}
