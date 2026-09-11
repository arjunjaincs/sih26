import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, ChevronRight, RefreshCw } from 'lucide-react';
import type { AssessmentSummarySchema } from '../types/api';
import { listAssessments } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { ErrorState } from '../components/ErrorState';
import { Button } from '../components/Button';
import { formatDatetime } from '../lib/format';

/* ── Single row in the assessments table ── */
function AssessmentRow({ a }: { a: AssessmentSummarySchema }) {
  return (
    <Link
      to={`/assessments/${a.assessment_id}/result`}
      className="flex items-center gap-4 px-5 py-3.5 border-b border-[var(--border)] last:border-0
        hover:bg-surface-2 transition-colors group"
    >
      {/* Status dot */}
      <StatusBadge value={a.status} variant="status" />

      {/* Title + ID */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-1 truncate">{a.title}</p>
        <code className="text-[11px] font-mono text-3">{a.assessment_id}</code>
      </div>

      {/* Findings badge */}
      <div className="hidden sm:flex flex-col items-end gap-0.5">
        <span className="text-xs text-2 font-medium">
          {a.findings_count} {a.findings_count === 1 ? 'finding' : 'findings'}
        </span>
        <span className="text-[11px] text-3">{a.evidence_count} evidence</span>
      </div>

      {/* Date */}
      {a.started_at && (
        <span className="hidden md:block text-xs text-3 flex-shrink-0 w-36 text-right">
          {formatDatetime(a.started_at)}
        </span>
      )}

      {/* Arrow */}
      <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent transition-colors flex-shrink-0" />
    </Link>
  );
}

/* ── Page ── */
export function Assessments() {
  const [items, setItems] = useState<AssessmentSummarySchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    listAssessments()
      .then(res => {
        setItems(res.assessments);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">
            Assessments
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            History of assurance assessments run on this workstation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            disabled={loading}
            className="p-2 rounded border border-[var(--border)] text-3 hover:text-1
              hover:bg-surface-2 transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <Link to="/new">
            <Button leftIcon={<Plus className="w-4 h-4" />} size="sm">
              New Assessment
            </Button>
          </Link>
        </div>
      </div>

      {/* Content */}
      {loading && (
        <div className="space-y-3 animate-pulse">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-14 bg-surface-2 rounded" />
          ))}
        </div>
      )}

      {!loading && error && (
        <ErrorState
          title="Could not load assessments"
          message={error}
        />
      )}

      {!loading && !error && items.length === 0 && (
        <div className="card p-10 text-center space-y-4">
          <p className="text-sm font-medium text-1">No assessments yet</p>
          <p className="text-xs text-3">
            Run your first assessment to see results here.
          </p>
          <Link to="/new">
            <Button size="sm" leftIcon={<Plus className="w-4 h-4" />}>
              Run Assessment
            </Button>
          </Link>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="card overflow-hidden">
          {/* Table header */}
          <div className="flex items-center gap-4 px-5 py-2 border-b border-[var(--border)] bg-surface-2">
            <span className="label text-3 w-20">Status</span>
            <span className="label text-3 flex-1">Assessment</span>
            <span className="hidden sm:block label text-3 text-right w-28">Findings</span>
            <span className="hidden md:block label text-3 w-36 text-right">Date</span>
            <span className="w-4" />
          </div>
          {items.map(a => (
            <AssessmentRow key={a.assessment_id} a={a} />
          ))}
          <div className="px-5 py-2 border-t border-[var(--border)] bg-surface-2 text-right">
            <span className="text-xs text-3">{items.length} total</span>
          </div>
        </div>
      )}
    </div>
  );
}
