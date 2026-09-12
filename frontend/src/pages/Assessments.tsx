import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { 
  Plus, 
  ChevronRight, 
  RefreshCw, 
  Search, 
  Clock, 
  Copy, 
  Check, 
  AlertTriangle, 
  CheckCircle2, 
  WifiOff
} from 'lucide-react';
import type { AssessmentSummarySchema } from '../types/api';
import { listAssessments, NetworkError } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { ReportDownloadButton } from '../components/ReportDownloadButton';
import { Button } from '../components/Button';
import { formatDatetime, formatDuration, formatPercent } from '../lib/format';
import { cn } from '../lib/cn';

/* ── Copy Assessment ID Button ── */
function CopyIdButton({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    navigator.clipboard.writeText(id).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    });
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="p-1 rounded text-3 hover:text-1 hover:bg-surface-2 transition-colors focus-visible:ring-1"
      title="Copy Assessment ID"
      aria-label="Copy Assessment ID"
    >
      {copied ? <Check className="w-3 h-3 text-[var(--green)]" /> : <Copy className="w-3 h-3" />}
    </button>
  );
}

/* ── Single row in the assessments table ── */
function AssessmentRow({ a }: { a: AssessmentSummarySchema }) {
  const hasFindings = a.findings_count > 0;
  const hasDuration = a.started_at && a.completed_at;

  const normRisk = a.overall_risk?.toLowerCase() || 'none';
  const riskAccent =
    normRisk === 'critical' ? '--risk-critical' :
    normRisk === 'high' ? '--risk-high' :
    normRisk === 'medium' ? '--risk-medium' :
    normRisk === 'low' ? '--risk-low' :
    '--risk-none';

  return (
    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 p-4 sm:px-5 sm:py-4 border-b border-[var(--border)] last:border-0 hover:bg-surface-2/60 transition-all duration-150 group">
      {/* Left block: Status + Title & ID */}
      <div className="flex items-start sm:items-center gap-3.5 flex-1 min-w-0">
        <div className="flex-shrink-0 pt-0.5 sm:pt-0">
          <StatusBadge value={a.status} variant="status" />
        </div>

        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2">
            <Link
              to={`/assessments/${a.assessment_id}/result`}
              className="text-sm font-bold text-1 hover:text-accent truncate transition-colors"
            >
              {a.title}
            </Link>
            {a.software_version && (
              <span className="hidden sm:inline-block font-mono text-[10px] text-3 px-1.5 py-0.2 rounded bg-surface-2 border border-[var(--border)]">
                v{a.software_version}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 text-xs text-3">
            <code className="text-[11px] font-mono text-3 tracking-tight">{a.assessment_id}</code>
            <CopyIdButton id={a.assessment_id} />
            <span className="text-3">·</span>
            <span className="font-mono text-[11px]">
              {a.started_at ? formatDatetime(a.started_at) : formatDatetime(a.created_at)}
            </span>
            {hasDuration && (
              <>
                <span className="text-3">·</span>
                <span className="text-[11px] text-3 flex items-center gap-1 font-mono">
                  <Clock className="w-3 h-3" />
                  {formatDuration(a.started_at, a.completed_at)}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Middle block: Assurance Badges (Risk / Coverage / Findings) */}
      <div className="flex items-center flex-wrap gap-2 sm:gap-3 flex-shrink-0">
        {/* Risk Badge */}
        {a.overall_risk && (
          <div
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border font-mono text-xs font-bold"
            style={{
              borderColor: `var(${riskAccent})`,
              backgroundColor: `color-mix(in srgb, var(${riskAccent}) 12%, transparent)`,
              color: `var(${riskAccent})`,
            }}
          >
            <span className="text-[10px] opacity-75 font-normal">RISK:</span>
            <span>{a.overall_risk.toUpperCase()}</span>
          </div>
        )}

        {/* Coverage Badge */}
        {a.coverage_fraction !== undefined && a.coverage_fraction !== null && (
          <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-accent/30 bg-[var(--accent-bg)] text-accent font-mono text-xs font-bold">
            <span className="text-[10px] opacity-75 font-normal">COV:</span>
            <span>{formatPercent(a.coverage_fraction)}</span>
          </div>
        )}

        {/* Findings Count */}
        <div
          className={cn(
            'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-mono font-medium',
            hasFindings
              ? 'bg-[var(--amber-bg)] text-[var(--amber)] border border-[var(--amber-border)]'
              : 'bg-[var(--green-bg)] text-[var(--green)] border border-[var(--green)]/20'
          )}
        >
          {hasFindings ? <AlertTriangle className="w-3 h-3" /> : <CheckCircle2 className="w-3 h-3" />}
          <span>{a.findings_count} findings</span>
        </div>
      </div>

      {/* Right block: Action buttons */}
      <div className="flex items-center gap-2 flex-shrink-0 self-end lg:self-auto">
        <ReportDownloadButton
          assessmentId={a.assessment_id}
          size="sm"
          variant="outline"
          className="h-8"
        />

        <Link
          to={`/assessments/${a.assessment_id}/result`}
          className="inline-flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border)] bg-surface hover:bg-surface-2 text-xs font-semibold text-1 hover:border-accent/40 transition-colors h-8"
        >
          <span>Inspect</span>
          <ChevronRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  );
}

/* ── Assessments Page Component ── */
export function Assessments() {
  const [items, setItems] = useState<AssessmentSummarySchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [, setError] = useState<string | null>(null);
  const [isOffline, setIsOffline] = useState(false);
  const [search, setSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  function load() {
    setLoading(true);
    setError(null);
    setIsOffline(false);
    listAssessments()
      .then((res) => {
        setItems(res.assessments);
        setLoading(false);
      })
      .catch((err) => {
        setIsOffline(err instanceof NetworkError);
        setError(err.message);
        setLoading(false);
      });
  }

  useEffect(() => {
    load();
  }, []);

  const filteredItems = items.filter((a) => {
    // Text search
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      const matchText =
        a.title.toLowerCase().includes(q) ||
        a.assessment_id.toLowerCase().includes(q) ||
        a.status.toLowerCase().includes(q);
      if (!matchText) return false;
    }

    // Risk filter
    if (riskFilter !== 'all') {
      const r = a.overall_risk?.toLowerCase() || 'none';
      if (r !== riskFilter) return false;
    }

    // Status filter
    if (statusFilter !== 'all') {
      if (a.status.toLowerCase() !== statusFilter) return false;
    }

    return true;
  });

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-6">
      {/* ── Page Header ── */}
      <div className="border-b border-[var(--border)] pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-[11px] font-bold text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
              AUDIT LEDGER
            </span>
            <span className="text-xs text-3 font-mono">PERSISTED ASSURANCE RUNS</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-1 tracking-tight">Assessment History</h1>
          <p className="text-xs text-3 mt-1">
            Complete cryptographic audit trail of all evaluations executed in this environment.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button variant="secondary" size="sm" onClick={load} disabled={loading} className="gap-1.5">
            <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
            <span>Refresh</span>
          </Button>
          <Link
            to="/new"
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-accent text-white text-xs sm:text-sm font-semibold hover:bg-[var(--accent-2)] transition-colors shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Assessment</span>
          </Link>
        </div>
      </div>

      {/* ── Search & Filter Bar ── */}
      <div className="card p-3 border border-[var(--border)] bg-surface rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-3 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by title, ID, or status…"
            className="w-full h-9 pl-9 pr-3 rounded-lg border border-[var(--border)] bg-surface-2/40 text-1 text-xs placeholder:text-3 focus:outline-none focus:border-accent"
          />
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <select
            value={riskFilter}
            onChange={(e) => setRiskFilter(e.target.value)}
            className="h-9 px-2.5 rounded-lg border border-[var(--border)] bg-surface-2/40 text-1 text-xs focus:outline-none focus:border-accent"
          >
            <option value="all">All Risk Levels</option>
            <option value="critical">Critical Risk</option>
            <option value="high">High Risk</option>
            <option value="medium">Medium Risk</option>
            <option value="low">Low Risk</option>
            <option value="none">Zero Risk</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="h-9 px-2.5 rounded-lg border border-[var(--border)] bg-surface-2/40 text-1 text-xs focus:outline-none focus:border-accent"
          >
            <option value="all">All States</option>
            <option value="complete">Complete</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </div>

      {/* ── Table / Cards Container ── */}
      <div className="card border border-[var(--border)] bg-surface rounded-xl overflow-hidden shadow-sm">
        {loading ? (
          <div className="divide-y divide-[var(--border)]">
            {[1, 2, 3].map((i) => (
              <div key={i} className="p-4 flex items-center justify-between gap-4 animate-pulse">
                <div className="space-y-2 flex-1">
                  <div className="h-4 w-1/3 bg-surface-2 rounded" />
                  <div className="h-3 w-1/2 bg-surface-2/60 rounded" />
                </div>
                <div className="h-8 w-24 bg-surface-2 rounded" />
              </div>
            ))}
          </div>
        ) : isOffline ? (
          <div className="p-12 text-center space-y-3">
            <WifiOff className="w-8 h-8 text-3 mx-auto" />
            <p className="text-sm font-bold text-1">Could not connect to local PRAMAAN engine</p>
            <p className="text-xs text-3 max-w-sm mx-auto">
              Please ensure the local air-gapped backend server is running on port 8000.
            </p>
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <div className="w-10 h-10 rounded-full bg-surface-2 border border-[var(--border)] flex items-center justify-center mx-auto text-3">
              <Search className="w-4 h-4" />
            </div>
            <p className="text-sm font-bold text-1">No matching assessments</p>
            <p className="text-xs text-3">
              {search || riskFilter !== 'all' || statusFilter !== 'all'
                ? 'Try clearing your search query or filters.'
                : 'No assessments have been executed in this environment yet.'}
            </p>
            <Link
              to="/new"
              className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline font-semibold pt-1"
            >
              <span>Run your first assessment</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-[var(--border)]">
            {filteredItems.map((a) => (
              <AssessmentRow key={a.assessment_id} a={a} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
