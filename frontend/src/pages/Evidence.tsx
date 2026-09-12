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
  ArrowRight
} from 'lucide-react';
import type { EvidenceResponse, EvidenceSchema } from '../types/api';
import { getEvidence } from '../api/client';
import { ErrorState } from '../components/ErrorState';
import { AssessmentSubNav } from '../components/AssessmentSubNav';
import { cn } from '../lib/cn';

type EvidenceTab = 'structured' | 'raw';

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

function EvidenceCard({ ev }: { ev: EvidenceSchema }) {
  const [tab, setTab] = useState<EvidenceTab>('structured');
  const [open, setOpen] = useState(true);

  const payload = (ev.data as Record<string, unknown>) ?? {};
  const keys = Object.keys(payload);

  return (
    <div className="border border-[var(--border)] rounded-xl overflow-hidden bg-surface shadow-sm transition-all duration-150">
      {/* Card Header Accordion */}
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between gap-4 px-5 py-4 bg-surface hover:bg-surface-2/60 transition-colors text-left focus-visible:outline-none focus-visible:bg-surface-2"
      >
        <div className="flex items-center gap-4 flex-wrap flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Hash className="w-4 h-4 text-accent flex-shrink-0" />
            <div>
              <p className="text-[10px] font-mono uppercase text-3 font-semibold">Evidence Record</p>
              <code className="text-xs font-mono font-bold text-accent">{ev.evidence_id}</code>
            </div>
          </div>

          <div className="border-l border-[var(--border)] pl-4">
            <p className="text-[10px] font-mono uppercase text-3 font-semibold">Artifact Type</p>
            <span className="text-xs font-mono text-1 font-medium">{ev.evidence_type}</span>
          </div>

          {ev.artifact_sha256 && (
            <div className="border-l border-[var(--border)] pl-4 hidden sm:block">
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
      </button>

      {/* Body: Structured vs Raw View */}
      {open && (
        <div className="border-t border-[var(--border)] bg-surface">
          {/* Sub-tabs */}
          <div className="flex items-center justify-between border-b border-[var(--border)] px-5 bg-surface-2/40">
            <div className="flex gap-2">
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

          <div className="p-5">
            {tab === 'structured' ? (
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
            ) : (
              <div className="relative">
                <pre className="text-xs font-mono text-2 overflow-x-auto leading-relaxed bg-surface-2/80 rounded-lg p-4 border border-[var(--border)] max-h-80">
                  {JSON.stringify(payload, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
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
            Content-addressed cryptographic hashes, structural AST fingerprints, and cluster telemetry.
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
            <EvidenceCard key={ev.evidence_id} ev={ev} />
          ))}
        </div>
      )}
    </div>
  );
}
