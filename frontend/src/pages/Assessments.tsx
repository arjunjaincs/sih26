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
  Database,
  WifiOff
} from 'lucide-react';
import type { AssessmentSummarySchema } from '../types/api';
import { listAssessments, NetworkError } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { Button } from '../components/Button';
import { formatDatetime, formatDuration } from '../lib/format';
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
      {copied ? (
        <Check className="w-3 h-3 text-[var(--green)]" />
      ) : (
        <Copy className="w-3 h-3" />
      )}
    </button>
  );
}

/* ── Single row in the assessments table ── */
function AssessmentRow({ a }: { a: AssessmentSummarySchema }) {
  const hasFindings = a.findings_count > 0;
  const hasDuration = a.started_at && a.completed_at;

  return (
    <Link
      to={`/assessments/${a.assessment_id}/result`}
      className="flex items-center gap-4 px-5 py-4 border-b border-[var(--border)] last:border-0
        hover:bg-surface-2 transition-all duration-150 group focus-visible:outline-none focus-visible:bg-surface-2"
    >
      {/* Status indicator */}
      <div className="flex-shrink-0 w-24">
        <StatusBadge value={a.status} variant="status" />
      </div>

      {/* Title + ID */}
      <div className="flex-1 min-w-0 pr-2">
        <div className="flex items-center gap-2">
          <p className="text-sm font-semibold text-1 truncate group-hover:text-accent transition-colors">
            {a.title}
          </p>
          {a.software_version && (
            <span className="hidden lg:inline-block font-mono text-[10px] text-3 px-1.5 py-0.2 rounded bg-surface-2 border border-[var(--border)]">
              v{a.software_version}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 mt-0.5">
          <code className="text-[11px] font-mono text-3 tracking-tight">
            {a.assessment_id}
          </code>
          <CopyIdButton id={a.assessment_id} />
        </div>
      </div>

      {/* Findings & Evidence */}
      <div className="hidden sm:flex flex-col items-end gap-1 flex-shrink-0 w-32">
        <span
          className={cn(
            'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono font-medium',
            hasFindings
              ? 'bg-[var(--amber-bg)] text-[var(--amber)] border border-[var(--amber-border)]'
              : 'bg-[var(--green-bg)] text-[var(--green)] border border-[var(--green)]/20'
          )}
        >
          {hasFindings ? (
            <AlertTriangle className="w-3 h-3" />
          ) : (
            <CheckCircle2 className="w-3 h-3" />
          )}
          {a.findings_count} {a.findings_count === 1 ? 'finding' : 'findings'}
        </span>
        <span className="text-[11px] text-3 font-mono">
          {a.evidence_count} evidence items
        </span>
      </div>

      {/* Execution Timeline */}
      <div className="hidden md:flex flex-col items-end gap-0.5 flex-shrink-0 w-40 text-right">
        <span className="text-xs text-2 font-mono">
          {a.started_at ? formatDatetime(a.started_at) : formatDatetime(a.created_at)}
        </span>
        {hasDuration && (
          <span className="text-[11px] text-3 flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatDuration(a.started_at, a.completed_at)}
          </span>
        )}
      </div>

      {/* Arrow */}
      <div className="flex items-center gap-1 text-xs text-3 group-hover:text-accent transition-colors flex-shrink-0">
        <span className="hidden xl:inline text-[11px] font-medium">Inspect</span>
        <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
      </div>
    </Link>
  );
}

/* ── Page ── */
export function Assessments() {
  const [items, setItems] = useState<AssessmentSummarySchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isOffline, setIsOffline] = useState(false);
  const [search, setSearch] = useState('');

  function load() {
    setLoading(true);
    setError(null);
    setIsOffline(false);
    listAssessments()
      .then(res => {
        setItems(res.assessments);
        setLoading(false);
      })
      .catch(err => {
        setIsOffline(err instanceof NetworkError);
        setError(err.message);
        setLoading(false);
      });
  }

  useEffect(() => { load(); }, []);

  const filteredItems = items.filter(a => {
    if (!search.trim()) return true;
    const q = search.toLowerCase().trim();
    return (
      a.title.toLowerCase().includes(q) ||
      a.assessment_id.toLowerCase().includes(q) ||
      a.status.toLowerCase().includes(q)
    );
  });

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
      {/* ── Page Header ── */}
      <div className="border-b border-[var(--border)] pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-[11px] font-bold text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
              AUDIT LEDGER
            </span>
            <span className="text-xs text-3 font-mono">PERSISTED RUNS</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-1 tracking-tight">
            Assessment History
          </h1>
          <p className="mt-1 text-sm text-2 max-w-2xl leading-relaxed">
            Cryptographically linked historical records and assurance findings from all local runs.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="p-2 rounded-lg border border-[var(--border)] text-3 hover:text-1
              hover:bg-surface-2 transition-colors disabled:opacity-50 focus-visible:ring-1"
            title="Refresh Assessments"
            aria-label="Refresh Assessments"
          >
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin text-accent')} />
          </button>
          <Link to="/new">
            <Button leftIcon={<Plus className="w-4 h-4" />} size="sm">
              Launch Assessment
            </Button>
          </Link>
        </div>
      </div>

      {/* ── Search & Filter Bar ── */}
      {!loading && !error && items.length > 0 && (
        <div className="flex items-center justify-between gap-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-3" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter by title, ID, or status…"
              className="w-full h-8 pl-8 pr-3 rounded-lg border border-[var(--border)] bg-surface text-1 text-xs
                placeholder:text-3 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-colors"
            />
          </div>
          <span className="text-xs text-3 font-mono">
            Showing {filteredItems.length} of {items.length} records
          </span>
        </div>
      )}

      {/* ── Content ── */}
      {loading && (
        <div className="card overflow-hidden divide-y divide-[var(--border)]">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="px-5 py-4 flex items-center gap-4 animate-pulse">
              <div className="w-20 h-6 bg-surface-2 rounded" />
              <div className="flex-1 space-y-1.5">
                <div className="w-48 h-4 bg-surface-2 rounded" />
                <div className="w-32 h-3 bg-surface-2 rounded" />
              </div>
              <div className="w-24 h-5 bg-surface-2 rounded hidden sm:block" />
              <div className="w-28 h-4 bg-surface-2 rounded hidden md:block" />
            </div>
          ))}
        </div>
      )}

      {/* ── Offline / Error State ── */}
      {!loading && error && (
        <div className="card p-8 text-center space-y-4 border border-[var(--border)]">
          <div className="w-12 h-12 rounded-full bg-[var(--red-bg)] flex items-center justify-center mx-auto text-[var(--red)]">
            {isOffline ? <WifiOff className="w-6 h-6" /> : <AlertTriangle className="w-6 h-6" />}
          </div>
          <div className="space-y-1">
            <h2 className="text-base font-semibold text-1">
              {isOffline ? 'PRAMAAN Backend Offline' : 'Could Not Load Assessments'}
            </h2>
            <p className="text-xs text-3 max-w-md mx-auto">
              {isOffline
                ? 'Unable to connect to local FastAPI daemon at http://localhost:8000. Start the backend service and retry.'
                : error}
            </p>
          </div>
          <div className="pt-2">
            <Button size="sm" variant="secondary" onClick={load}>
              Retry Connection
            </Button>
          </div>
        </div>
      )}

      {/* ── Empty State ── */}
      {!loading && !error && items.length === 0 && (
        <div className="card p-12 text-center space-y-4 border border-dashed border-[var(--border)]">
          <div className="w-12 h-12 rounded-xl bg-[var(--accent-bg)] border border-accent/20 flex items-center justify-center mx-auto text-accent">
            <Database className="w-6 h-6" />
          </div>
          <div className="space-y-1.5">
            <h2 className="text-base font-semibold text-1">No Assessments Yet</h2>
            <p className="text-xs text-3 max-w-sm mx-auto leading-relaxed">
              Run your first offline CV model or dataset assurance assessment to generate verifiable cryptographic findings.
            </p>
          </div>
          <div className="pt-2">
            <Link to="/new">
              <Button size="sm" leftIcon={<Plus className="w-4 h-4" />}>
                Launch First Assessment
              </Button>
            </Link>
          </div>
        </div>
      )}

      {/* ── Filtered Empty State ── */}
      {!loading && !error && items.length > 0 && filteredItems.length === 0 && (
        <div className="card p-8 text-center space-y-2">
          <p className="text-sm font-medium text-1">No matching assessments</p>
          <p className="text-xs text-3">
            No records matched <code className="font-mono text-2">"{search}"</code>.
          </p>
          <button
            type="button"
            onClick={() => setSearch('')}
            className="text-xs text-accent hover:underline pt-1"
          >
            Clear filter
          </button>
        </div>
      )}

      {/* ── Assessments Table ── */}
      {!loading && !error && filteredItems.length > 0 && (
        <div className="card overflow-hidden border border-[var(--border)]">
          {/* Table header */}
          <div className="flex items-center gap-4 px-5 py-2.5 border-b border-[var(--border)] bg-surface-2/60 text-[10px] font-mono uppercase font-semibold text-3 tracking-wider">
            <span className="w-24">Status</span>
            <span className="flex-1">Assessment & ID</span>
            <span className="hidden sm:block text-right w-32">Findings / Evidence</span>
            <span className="hidden md:block text-right w-40">Timeline</span>
            <span className="w-10 text-right">Action</span>
          </div>

          {/* Rows */}
          <div className="divide-y divide-[var(--border)]">
            {filteredItems.map(a => (
              <AssessmentRow key={a.assessment_id} a={a} />
            ))}
          </div>

          {/* Footer summary */}
          <div className="px-5 py-2.5 border-t border-[var(--border)] bg-surface-2/40 flex items-center justify-between text-xs text-3 font-mono">
            <span>Append-only SQLite persistence</span>
            <span>{items.length} total assessments</span>
          </div>
        </div>
      )}
    </div>
  );
}
