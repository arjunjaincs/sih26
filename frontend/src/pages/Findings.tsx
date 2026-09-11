import { useParams, Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { ArrowLeft, ChevronDown, ChevronUp } from 'lucide-react';
import type { FindingsResponse, FindingSchema } from '../types/api';
import { getFindings } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { ErrorState } from '../components/ErrorState';
import { formatDatetime } from '../lib/format';

/* ── Single finding card (expandable) ── */
function FindingCard({ finding }: { finding: FindingSchema }) {
  const [open, setOpen] = useState(false);

  const severityAccent =
    finding.severity === 'critical' ? '--risk-critical' :
    finding.severity === 'high' ? '--risk-high' :
    finding.severity === 'medium' ? '--risk-medium' :
    finding.severity === 'low' ? '--risk-low' : '--text-3';

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-surface hover:bg-surface-2 transition-colors text-left"
      >
        {/* Severity indicator */}
        <div
          className="flex-shrink-0 w-1 h-8 rounded-full self-start mt-0.5"
          style={{ background: `var(${severityAccent})` }}
        />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge value={finding.severity} variant="severity" />
            <StatusBadge value={finding.category} variant="category" />
          </div>
          <p className="mt-1 text-sm font-medium text-1 leading-snug truncate pr-4">
            {finding.title}
          </p>
        </div>

        <div className="flex-shrink-0 text-3">
          {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 border-t border-[var(--border)] bg-surface space-y-4">
          <p className="text-sm text-2 leading-relaxed">{finding.description}</p>

          <div className="grid grid-cols-2 gap-x-8 gap-y-2">
            {[
              ['Finding ID',  <code key="id" className="font-mono text-2 text-xs">{finding.finding_id}</code>],
              ['Detector',    <code key="det" className="font-mono text-accent text-xs">{finding.detector_id ?? '—'}</code>],
              ['Category',    <span key="cat" className="text-xs text-2">{finding.subcategory ?? finding.category}</span>],
              ['Timestamp',   <span key="ts" className="text-xs text-2">{finding.created_at ? formatDatetime(finding.created_at) : '—'}</span>],
              ['Method',      <span key="m" className="text-xs text-2">{finding.detection_method ?? '—'}</span>],
            ].map(([label, val]) => (
              <div key={String(label)}>
                <p className="label mb-0.5">{label}</p>
                {val}
              </div>
            ))}
          </div>

          {finding.recommended_disposition && (
            <div className="pt-2 border-t border-[var(--border)]">
              <p className="label mb-1">Recommended Disposition</p>
              <p className="text-sm text-2">{finding.recommended_disposition}</p>
            </div>
          )}

          {finding.limitations && finding.limitations.length > 0 && (
            <div className="pt-2 border-t border-[var(--border)]">
              <p className="label mb-1">Limitations</p>
              <ul className="space-y-0.5">
                {finding.limitations.map((l, i) => (
                  <li key={i} className="text-xs text-3 flex items-start gap-1.5">
                    <span className="mt-1 flex-shrink-0 w-1 h-1 rounded-full bg-text4 inline-block" />
                    {l}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Detector group ── */
function DetectorGroup({ detectorId, findings }: { detectorId: string; findings: FindingSchema[] }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="space-y-2">
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
        <span className="text-xs text-3">
          {findings.length} finding{findings.length !== 1 ? 's' : ''}
        </span>
        <span className="ml-1 flex-shrink-0 w-5 h-5 rounded-full bg-[var(--accent-bg)] text-accent
          text-[10px] font-bold flex items-center justify-center">
          {findings.length}
        </span>
        {open ? <ChevronUp className="w-4 h-4 text-3" /> : <ChevronDown className="w-4 h-4 text-3" />}
      </button>

      {open && (
        <div className="space-y-2 pl-14">
          {findings.map(f => <FindingCard key={f.finding_id} finding={f} />)}
        </div>
      )}
    </div>
  );
}

export function Findings() {
  const { id } = useParams<{ id?: string }>();
  const [data, setData] = useState<FindingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [detectorFilter, setDetectorFilter] = useState('all');

  useEffect(() => {
    if (!id) { setLoading(false); return; }
    getFindings(id)
      .then(d => { setData(d); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [id]);

  if (loading) return (
    <div className="max-w-4xl mx-auto px-6 py-10 space-y-4 animate-pulse">
      {[...Array(3)].map((_, i) => <div key={i} className="h-20 bg-surface-2 rounded" />)}
    </div>
  );
  if (error) return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <ErrorState title="Could not load findings" message={error} />
    </div>
  );

  const allFindings = data?.findings ?? [];
  const detectors = [...new Set(allFindings.map(f => f.detector_id ?? 'Unknown'))];
  const filtered = detectorFilter === 'all'
    ? allFindings
    : allFindings.filter(f => f.detector_id === detectorFilter);

  const byDetector = detectors.reduce<Record<string, FindingSchema[]>>((acc, det) => {
    acc[det] = filtered.filter(f => (f.detector_id ?? 'Unknown') === det);
    return acc;
  }, {});

  return (
    <div className="max-w-4xl mx-auto px-6 py-10 space-y-6">
      {/* Header */}
      {id && (
        <Link to={`/assessments/${id}/result`}
          className="flex items-center gap-1.5 text-xs text-3 hover:text-1 transition-colors">
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Results
        </Link>
      )}

      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="label text-accent mb-1">PRAMAAN · Findings</p>
          <h1 className="text-2xl font-bold text-1">Findings</h1>
          <p className="mt-0.5 text-sm text-3">
            Detailed findings from all executed detectors.
          </p>
        </div>

        {/* Detector filter */}
        {detectors.length > 1 && (
          <select
            value={detectorFilter}
            onChange={e => setDetectorFilter(e.target.value)}
            className="h-8 px-3 rounded border border-[var(--border)] bg-surface text-xs text-1
              focus:outline-none focus:border-accent"
          >
            <option value="all">All Detectors</option>
            {detectors.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        )}
      </div>

      {allFindings.length === 0 ? (
        <div className="card p-10 text-center space-y-2">
          <div className="w-10 h-10 rounded-full bg-[var(--risk-none-bg)] mx-auto flex items-center justify-center">
            <svg className="w-5 h-5 text-[var(--risk-none)]" viewBox="0 0 20 20" fill="none">
              <path d="M5 10l4 4 6-7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <p className="text-sm font-medium text-1">No findings recorded</p>
          <p className="text-xs text-3">No integrity concerns were detected in this assessment.</p>
        </div>
      ) : (
        <div className="space-y-8">
          {Object.entries(byDetector).filter(([, fs]) => fs.length > 0).map(([det, fs]) => (
            <DetectorGroup key={det} detectorId={det} findings={fs} />
          ))}
        </div>
      )}
    </div>
  );
}
