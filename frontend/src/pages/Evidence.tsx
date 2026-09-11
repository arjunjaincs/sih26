import { useParams, Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { Copy, Check } from 'lucide-react';
import type { EvidenceResponse, EvidenceSchema } from '../types/api';
import { getEvidence } from '../api/client';
import { ErrorState } from '../components/ErrorState';
import { cn } from '../lib/cn';

type EvidenceTab = 'structured' | 'raw';

function CopyBtn({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(value).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }); }}
      className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium
        text-3 border border-[var(--border)] hover:text-1 hover:border-[var(--border-strong)]
        transition-colors"
    >
      {copied ? <Check className="w-3 h-3 text-[var(--green)]" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

function KVRow({ k, v }: { k: string; v: unknown }) {
  const display = typeof v === 'string' ? v :
    typeof v === 'number' ? String(v) :
    v === null || v === undefined ? '—' :
    JSON.stringify(v, null, 2);

  const isHash = k.toLowerCase().includes('sha') || k.toLowerCase().includes('hash');
  const isLong = display.length > 80;

  return (
    <div className={cn(
      'flex gap-4 py-2 border-b border-[var(--border)] last:border-0',
      isLong ? 'flex-col' : 'items-start',
    )}>
      <div className={cn('flex-shrink-0', isLong ? '' : 'w-40')}>
        <p className="label leading-tight">{k.replace(/_/g, ' ')}</p>
      </div>
      {isHash ? (
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <code className="text-[11px] font-mono text-2 truncate">{display}</code>
          <CopyBtn value={display} />
        </div>
      ) : (
        <code className={cn('text-[11px] font-mono text-2 break-all', isLong && 'block')}>{display}</code>
      )}
    </div>
  );
}

function EvidenceCard({ ev }: { ev: EvidenceSchema }) {
  const [tab, setTab] = useState<EvidenceTab>('structured');
  const [open, setOpen] = useState(true);

  const payload = ev.data ?? {};
  const keys = Object.keys(payload);

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-4 px-4 py-3 bg-surface hover:bg-surface-2 transition-colors text-left"
      >
        <div className="flex-1 min-w-0 flex items-center gap-4 flex-wrap">
          <div>
            <p className="label mb-0.5">Evidence ID</p>
            <code className="text-[11px] font-mono text-accent">{ev.evidence_id}</code>
          </div>
          <div>
            <p className="label mb-0.5">Type</p>
            <code className="text-[11px] font-mono text-2">{ev.evidence_type}</code>
          </div>
          {ev.artifact_sha256 && (
            <div>
              <p className="label mb-0.5">SHA-256</p>
              <code className="text-[11px] font-mono text-2">
                {ev.artifact_sha256.slice(0, 12)}…
              </code>
            </div>
          )}
        </div>
        <svg className={cn('w-4 h-4 text-3 flex-shrink-0 transition-transform', open && 'rotate-180')}
          viewBox="0 0 16 16" fill="none">
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {open && (
        <div className="border-t border-[var(--border)] bg-surface">
          <div className="flex border-b border-[var(--border)] px-4">
            {(['structured', 'raw'] as EvidenceTab[]).map(t => (
              <button key={t} onClick={() => setTab(t)}
                className={cn(
                  'px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors',
                  tab === t ? 'border-accent text-accent' : 'border-transparent text-3 hover:text-1',
                )}>
                {t === 'structured' ? 'Structured View' : 'Raw JSON'}
              </button>
            ))}
          </div>

          <div className="px-4 py-3">
            {tab === 'structured' ? (
              keys.length === 0 ? (
                <p className="text-xs text-3">
                  {ev.description || 'No structured data available.'}
                </p>
              ) : (
                <div>{keys.map(k => <KVRow key={k} k={k} v={payload[k]} />)}</div>
              )
            ) : (
              <div className="relative">
                <pre className="text-[11px] font-mono text-2 overflow-x-auto leading-relaxed
                  bg-surface-2 rounded p-3 max-h-64">
                  {JSON.stringify(payload, null, 2)}
                </pre>
                <div className="absolute top-2 right-2">
                  <CopyBtn value={JSON.stringify(payload, null, 2)} />
                </div>
              </div>
            )}
          </div>

          {ev.artifact_sha256 && (
            <div className="px-4 pb-3 border-t border-[var(--border)] pt-2 flex items-center gap-3">
              <p className="label">SHA-256</p>
              <code className="text-[11px] font-mono text-2 flex-1 break-all">{ev.artifact_sha256}</code>
              <CopyBtn value={ev.artifact_sha256} />
            </div>
          )}

          <p className="px-4 pb-3 text-[10px] text-3 italic">
            Note: File paths and raw binary data are not included for security.
          </p>
        </div>
      )}
    </div>
  );
}

function EvidenceDetectorGroup({ detectorId, items }: { detectorId: string; items: EvidenceSchema[] }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="space-y-3">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 py-2 border-b border-[var(--border)] hover:border-accent transition-colors"
      >
        <code className="text-xs font-mono font-bold text-accent w-12 text-left">{detectorId}</code>
        <span className="text-sm font-medium text-1 flex-1 text-left">
          {detectorId === 'DI-01' ? 'Dataset Integrity' :
           detectorId === 'MI-01' ? 'Model Integrity Fingerprinting' :
           detectorId === 'PI-01' ? 'Provenance Integrity' : detectorId}
        </span>
        <span className="text-xs text-3">{items.length} evidence record{items.length !== 1 ? 's' : ''}</span>
        <svg className={cn('w-4 h-4 text-3 transition-transform', open && 'rotate-180')}
          viewBox="0 0 16 16" fill="none">
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
      {open && (
        <div className="space-y-3 pl-14">
          {items.map(ev => <EvidenceCard key={ev.evidence_id} ev={ev} />)}
        </div>
      )}
    </div>
  );
}

export function Evidence() {
  const { id } = useParams<{ id?: string }>();
  const [data, setData] = useState<EvidenceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [detectorFilter, setDetectorFilter] = useState('all');

  useEffect(() => {
    if (!id) { setLoading(false); return; }
    getEvidence(id)
      .then(d => { setData(d); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [id]);

  if (loading) return (
    <div className="max-w-4xl mx-auto px-6 py-10 space-y-4 animate-pulse">
      {[...Array(3)].map((_, i) => <div key={i} className="h-24 bg-surface-2 rounded" />)}
    </div>
  );
  if (error) return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <ErrorState title="Could not load evidence" message={error} />
    </div>
  );

  const all: EvidenceSchema[] = data?.evidence ?? [];
  const detectors = [...new Set(all.map(e => e.detector_id ?? 'Unknown'))];
  const filtered = detectorFilter === 'all' ? all : all.filter(e => e.detector_id === detectorFilter);
  const byDetector = detectors.reduce<Record<string, EvidenceSchema[]>>((acc, d) => {
    acc[d] = filtered.filter(e => (e.detector_id ?? 'Unknown') === d);
    return acc;
  }, {});

  return (
    <div className="max-w-4xl mx-auto px-6 py-10 space-y-6">
      {id && (
        <Link to={`/assessments/${id}/result`}
          className="flex items-center gap-1.5 text-xs text-3 hover:text-1 transition-colors">
          <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none">
            <path d="M10 3L5 8l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Back to Results
        </Link>
      )}

      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="label text-accent mb-1">PRAMAAN · Evidence</p>
          <h1 className="text-2xl font-bold text-1">Evidence</h1>
          <p className="mt-0.5 text-sm text-3">All measurement data collected during this assessment.</p>
        </div>
        {detectors.length > 1 && (
          <select value={detectorFilter} onChange={e => setDetectorFilter(e.target.value)}
            className="h-8 px-3 rounded border border-[var(--border)] bg-surface text-xs text-1 focus:outline-none focus:border-accent">
            <option value="all">All Detectors</option>
            {detectors.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        )}
      </div>

      {all.length === 0 ? (
        <div className="card p-10 text-center">
          <p className="text-sm text-3">No evidence records collected for this assessment.</p>
        </div>
      ) : (
        <div className="space-y-8">
          {Object.entries(byDetector).filter(([, items]) => items.length > 0).map(([det, items]) => (
            <EvidenceDetectorGroup key={det} detectorId={det} items={items} />
          ))}
        </div>
      )}
    </div>
  );
}
