import { useParams, Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { 
  ChevronDown, 
  ChevronUp, 
  CheckCircle2, 
  Copy, 
  Check, 
  FileText, 
  SlidersHorizontal,
  ArrowRight
} from 'lucide-react';
import type { FindingsResponse, FindingSchema } from '../types/api';
import { getFindings } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { ErrorState } from '../components/ErrorState';
import { AssessmentSubNav } from '../components/AssessmentSubNav';
import { formatDatetime } from '../lib/format';

/* ── Copy Button ── */
function CopyMiniBtn({ value, label }: { value: string; label?: string }) {
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
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono text-3 hover:text-1 hover:bg-surface-2 transition-colors border border-transparent hover:border-[var(--border)]"
      title={`Copy ${label ?? 'value'}`}
    >
      {copied ? <Check className="w-3 h-3 text-[var(--green)]" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied' : null}
    </button>
  );
}

/* ── Single finding card (expandable) ── */
function FindingCard({ 
  finding, 
  assessmentId 
}: { 
  finding: FindingSchema; 
  assessmentId?: string;
}) {
  const [open, setOpen] = useState(false);

  const severityAccent =
    finding.severity === 'critical' ? '--risk-critical' :
    finding.severity === 'high' ? '--risk-high' :
    finding.severity === 'medium' ? '--risk-medium' :
    finding.severity === 'low' ? '--risk-low' : '--text-3';

  return (
    <div className="border border-[var(--border)] rounded-xl overflow-hidden bg-surface transition-all duration-150 shadow-sm">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3.5 px-5 py-4 bg-surface hover:bg-surface-2/60 transition-colors text-left focus-visible:outline-none focus-visible:bg-surface-2"
      >
        {/* Severity indicator bar */}
        <div
          className="flex-shrink-0 w-1.5 h-10 rounded-full self-start mt-0.5"
          style={{ background: `var(${severityAccent})` }}
        />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <StatusBadge value={finding.severity} variant="severity" />
            <span className="font-mono text-[11px] font-bold text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
              {finding.detector_id}
            </span>
            <span className="text-[11px] text-3 font-mono">
              {finding.subcategory || finding.category}
            </span>
          </div>
          <p className="text-sm font-semibold text-1 leading-snug pr-4">
            {finding.title}
          </p>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0 text-3">
          <span className="text-xs hidden sm:inline text-3">
            {open ? 'Collapse' : 'Inspect'}
          </span>
          {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {open && (
        <div className="px-5 pb-5 pt-3 border-t border-[var(--border)] bg-surface-2/20 space-y-4">
          {/* Finding description */}
          <div>
            <p className="label text-3 mb-1">Finding Analysis</p>
            <p className="text-sm text-2 leading-relaxed bg-surface p-3 rounded-lg border border-[var(--border)]">
              {finding.description}
            </p>
          </div>

          {/* Technical Metadata Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-surface p-3.5 rounded-lg border border-[var(--border)] text-xs">
            <div>
              <p className="label text-3 mb-0.5">Finding ID</p>
              <div className="flex items-center gap-1.5">
                <code className="font-mono text-2 text-[11px]">{finding.finding_id}</code>
                <CopyMiniBtn value={finding.finding_id} label="Finding ID" />
              </div>
            </div>

            <div>
              <p className="label text-3 mb-0.5">Affected Asset</p>
              <div className="flex items-center gap-1.5">
                <code className="font-mono text-2 text-[11px] truncate max-w-[200px]">
                  {finding.asset_id || 'Global Assessment Scope'}
                </code>
                {finding.asset_id && <CopyMiniBtn value={finding.asset_id} label="Asset ID" />}
              </div>
            </div>

            <div>
              <p className="label text-3 mb-0.5">Detection Method</p>
              <span className="text-2 font-mono text-[11px]">
                {finding.detection_method || 'Deterministic Automated Rule'}
              </span>
            </div>

            <div>
              <p className="label text-3 mb-0.5">Logged At</p>
              <span className="text-2 font-mono text-[11px]">
                {finding.created_at ? formatDatetime(finding.created_at) : '—'}
              </span>
            </div>
          </div>

          {/* Recommended Disposition */}
          {finding.recommended_disposition && (
            <div className="p-3.5 rounded-lg border border-[var(--blue-border)] bg-[var(--blue-bg)]">
              <p className="label text-accent mb-1 font-semibold flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5" />
                Recommended Analyst Disposition
              </p>
              <p className="text-xs text-1 leading-relaxed">
                {finding.recommended_disposition}
              </p>
            </div>
          )}

          {/* Limitations */}
          {finding.limitations && finding.limitations.length > 0 && (
            <div className="space-y-1.5">
              <p className="label text-3">Assurance Limitations</p>
              <ul className="space-y-1">
                {finding.limitations.map((l, i) => (
                  <li key={i} className="text-[11px] text-3 flex items-start gap-1.5">
                    <span className="mt-1 flex-shrink-0 w-1 h-1 rounded-full bg-[var(--text-muted)]" />
                    <span>{l}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Inspect Evidence Shortcut */}
          {assessmentId && (
            <div className="pt-2 border-t border-[var(--border)] flex justify-end">
              <Link
                to={`/assessments/${assessmentId}/evidence`}
                className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline font-semibold"
              >
                <span>Inspect Supporting Evidence</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Detector Group ── */
function DetectorGroup({ 
  detectorId, 
  findings,
  assessmentId 
}: { 
  detectorId: string; 
  findings: FindingSchema[];
  assessmentId?: string;
}) {
  const [open, setOpen] = useState(true);

  const getTitle = (id: string) => {
    if (id === 'DI-01') return 'Dataset Integrity (DI-01)';
    if (id === 'MI-01') return 'Model Integrity Fingerprinting (MI-01)';
    if (id === 'PI-01') return 'Provenance & Signature Verification (PI-01)';
    if (id === 'AT-01') return 'Audit Trail Ledger (AT-01)';
    return id;
  };

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between py-2.5 px-3 rounded-lg border border-[var(--border)] bg-surface-2/40 hover:bg-surface-2 transition-colors"
      >
        <div className="flex items-center gap-3">
          <code className="text-xs font-mono font-bold text-accent px-1.5 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
            {detectorId}
          </code>
          <span className="text-sm font-semibold text-1">{getTitle(detectorId)}</span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-medium px-2 py-0.5 rounded-full bg-surface border border-[var(--border)] text-2">
            {findings.length} {findings.length === 1 ? 'finding' : 'findings'}
          </span>
          {open ? <ChevronUp className="w-4 h-4 text-3" /> : <ChevronDown className="w-4 h-4 text-3" />}
        </div>
      </button>

      {open && (
        <div className="space-y-3 pl-0 sm:pl-2">
          {findings.map(f => (
            <FindingCard key={f.finding_id} finding={f} assessmentId={assessmentId} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   Findings Page Component
──────────────────────────────────────────────────────────── */
export function Findings() {
  const { id } = useParams<{ id?: string }>();
  const [data, setData] = useState<FindingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [detectorFilter, setDetectorFilter] = useState('all');
  const [severityFilter, setSeverityFilter] = useState('all');

  useEffect(() => {
    if (!id) { setLoading(false); return; }
    getFindings(id)
      .then(d => { setData(d); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-8 space-y-4 animate-pulse">
        <div className="h-10 bg-surface-2 rounded w-1/3" />
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-24 bg-surface-2 rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-8">
        <ErrorState title="Could not load assessment findings" message={error} />
      </div>
    );
  }

  const allFindings = data?.findings ?? [];
  const detectors = [...new Set(allFindings.map(f => f.detector_id ?? 'Unknown'))];

  const filtered = allFindings.filter(f => {
    if (detectorFilter !== 'all' && f.detector_id !== detectorFilter) return false;
    if (severityFilter !== 'all' && f.severity !== severityFilter) return false;
    return true;
  });

  const byDetector = detectors.reduce<Record<string, FindingSchema[]>>((acc, det) => {
    acc[det] = filtered.filter(f => (f.detector_id ?? 'Unknown') === det);
    return acc;
  }, {});

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
      {/* Unified Sub-navigation */}
      {id && (
        <AssessmentSubNav 
          assessmentId={id} 
          findingsCount={allFindings.length} 
        />
      )}

      {/* Header */}
      <div className="border-b border-[var(--border)] pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-[11px] font-bold text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
              DEFECT REGISTRY
            </span>
            <span className="text-xs text-3 font-mono">ASSURANCE AUDIT</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-1 tracking-tight">
            Assessment Findings
          </h1>
          <p className="mt-1 text-sm text-2 max-w-2xl leading-relaxed">
            Cryptographic, structural, and behavioral defect records detected during analysis.
          </p>
        </div>

        {/* Filter Selectors */}
        {allFindings.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-1.5 text-xs text-3 font-mono mr-1">
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>Filters:</span>
            </div>

            {/* Detector Filter */}
            {detectors.length > 1 && (
              <select
                value={detectorFilter}
                onChange={e => setDetectorFilter(e.target.value)}
                className="h-8 px-2.5 rounded-lg border border-[var(--border)] bg-surface text-xs text-1 font-mono focus:outline-none focus:border-accent"
              >
                <option value="all">All Detectors ({allFindings.length})</option>
                {detectors.map(d => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            )}

            {/* Severity Filter */}
            <select
              value={severityFilter}
              onChange={e => setSeverityFilter(e.target.value)}
              className="h-8 px-2.5 rounded-lg border border-[var(--border)] bg-surface text-xs text-1 font-mono focus:outline-none focus:border-accent"
            >
              <option value="all">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="info">Info</option>
            </select>
          </div>
        )}
      </div>

      {/* Empty State — Clean */}
      {allFindings.length === 0 ? (
        <div className="card p-12 text-center space-y-3 border border-dashed border-[var(--border)]">
          <div className="w-12 h-12 rounded-full bg-[var(--green-bg)] text-[var(--green)] mx-auto flex items-center justify-center">
            <CheckCircle2 className="w-6 h-6" />
          </div>
          <h2 className="text-base font-semibold text-1">Zero Findings Recorded</h2>
          <p className="text-xs text-3 max-w-sm mx-auto leading-relaxed">
            No structural mutations, duplicate anomalies, decode errors, or provenance signature mismatches were identified.
          </p>
          {id && (
            <div className="pt-2">
              <Link
                to={`/assessments/${id}/evidence`}
                className="inline-flex items-center gap-1.5 text-xs text-accent font-semibold hover:underline"
              >
                <span>Inspect Verified Evidence Artifacts</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          )}
        </div>
      ) : filtered.length === 0 ? (
        <div className="card p-8 text-center space-y-2">
          <p className="text-sm font-medium text-1">No findings match the selected filters</p>
          <button
            type="button"
            onClick={() => { setDetectorFilter('all'); setSeverityFilter('all'); }}
            className="text-xs text-accent hover:underline"
          >
            Reset filters
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(byDetector)
            .filter(([, fs]) => fs.length > 0)
            .map(([det, fs]) => (
              <DetectorGroup 
                key={det} 
                detectorId={det} 
                findings={fs} 
                assessmentId={id} 
              />
            ))}
        </div>
      )}
    </div>
  );
}
