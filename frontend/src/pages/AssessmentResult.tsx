import { useLocation, useParams, Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { ArrowLeft, Download, Share2, ChevronRight } from 'lucide-react';
import type { AssessmentResultSchema, AssessmentSummarySchema } from '../types/api';
import { getAssessment } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { ErrorState } from '../components/ErrorState';
import { formatDatetime, formatPercent, formatDuration } from '../lib/format';

/* ────────────────────────────────────────────────────────────
   Metric panel — Risk / Confidence / Coverage
──────────────────────────────────────────────────────────── */
function MetricPanel({
  label,
  value,
  sub,
  variant,
  accent,
}: {
  label: string;
  value: string;
  sub: string;
  variant: 'risk' | 'confidence' | 'neutral';
  accent: string; // css color var
}) {
  return (
    <div className="card p-5 flex flex-col gap-3">
      <p className="label">{label}</p>
      <div className="flex items-end gap-3">
        <span
          className="text-3xl font-bold leading-none tracking-tight"
          style={{ color: `var(${accent})` }}
        >
          {value}
        </span>
        {variant === 'confidence' && (
          <span className="text-accent text-lg font-bold mb-0.5">↑</span>
        )}
      </div>
      <p className="text-xs text-3 leading-relaxed">{sub}</p>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   Detector result row
──────────────────────────────────────────────────────────── */
function DetectorRow({
  run,
  assessmentId,
}: {
  run: AssessmentResultSchema['detector_runs'][number];
  assessmentId: string;
}) {
  const hasFindings = (run.findings_count ?? 0) > 0;
  return (
    <tr className="border-b border-[var(--border)] last:border-0 hover:bg-surface-2 transition-colors group">
      <td className="py-3 px-5">
        <code className="text-[11px] font-mono font-semibold text-accent">{run.detector_id}</code>
      </td>
      <td className="py-3 pr-4">
        <span className="text-sm text-1">{run.detector_name}</span>
      </td>
      <td className="py-3 pr-4">
        {run.ran && run.risk_level ? (
          <StatusBadge value={run.risk_level} variant="risk" />
        ) : (
          <span className="text-xs text-3">Not applicable</span>
        )}
      </td>
      <td className="py-3 pr-4 text-sm text-2">
        {hasFindings
          ? `${run.findings_count} finding${run.findings_count === 1 ? '' : 's'}`
          : !run.applicable
            ? <span className="text-3 text-xs">no asset provided</span>
            : <span className="text-3 text-xs">—</span>}
      </td>
      <td className="py-3 pr-4 text-right">
        {hasFindings && (
          <Link
            to={`/assessments/${assessmentId}/findings`}
            className="inline-flex items-center gap-1 text-xs text-accent hover:underline opacity-0 group-hover:opacity-100 transition-opacity"
          >
            View details <ChevronRight className="w-3 h-3" />
          </Link>
        )}
      </td>
    </tr>
  );
}

/* ────────────────────────────────────────────────────────────
   Summary-only view  (direct URL / browser refresh)
   Shown when full AssessmentResultSchema is not in navigation state.
   Fetches AssessmentSummarySchema from the backend instead.
──────────────────────────────────────────────────────────── */
function SummaryView({ summary }: { summary: AssessmentSummarySchema }) {
  const id = summary.assessment_id;
  return (
    <div className="max-w-4xl mx-auto px-6 py-10 space-y-8">
      {/* Back */}
      <Link
        to="/assessments"
        className="flex items-center gap-1.5 text-xs text-3 hover:text-1 transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        Back to Assessments
      </Link>

      {/* Header */}
      <div>
        <p className="label text-accent mb-1">Assessment Record</p>
        <h1 className="text-2xl font-bold text-1">{summary.title}</h1>
        <div className="mt-2 flex items-center flex-wrap gap-x-4 gap-y-1 text-xs text-3">
          <span>
            ID: <code className="font-mono text-2">{summary.assessment_id}</code>
          </span>
          {summary.started_at && (
            <span>Date: {formatDatetime(summary.started_at)}</span>
          )}
          {summary.started_at && summary.completed_at && (
            <span>
              Duration: {formatDuration(summary.started_at, summary.completed_at)}
            </span>
          )}
          <StatusBadge value={summary.status} variant="status" />
        </div>
      </div>

      {/* Counts */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="card p-5 flex flex-col gap-2">
          <p className="label">Findings</p>
          <span className="text-3xl font-bold leading-none text-[var(--accent)]">
            {summary.findings_count}
          </span>
          <p className="text-xs text-3">Total findings recorded</p>
        </div>
        <div className="card p-5 flex flex-col gap-2">
          <p className="label">Evidence Items</p>
          <span className="text-3xl font-bold leading-none text-[var(--accent)]">
            {summary.evidence_count}
          </span>
          <p className="text-xs text-3">Total evidence items collected</p>
        </div>
      </div>

      <p className="text-xs text-3 px-1">
        Full detector run details are only available immediately after completing an assessment.
        Use the links below to inspect persisted findings, evidence, and audit trail.
      </p>

      {/* Sub-page links */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {[
          { label: 'Findings', to: `/assessments/${id}/findings` },
          { label: 'Evidence', to: `/assessments/${id}/evidence` },
          { label: 'Audit Trail', to: `/assessments/${id}/audit` },
        ].map(link => (
          <Link
            key={link.label}
            to={link.to}
            className="flex items-center justify-between px-4 py-2.5 rounded border border-[var(--border)]
              text-sm text-2 hover:bg-surface-2 hover:text-1 transition-colors group"
          >
            {link.label}
            <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent transition-colors" />
          </Link>
        ))}
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   Main page component
──────────────────────────────────────────────────────────── */
export function AssessmentResult() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();

  // Full result is passed via navigation state when coming from NewAssessment
  const resultFromNav: AssessmentResultSchema | null = location.state?.result ?? null;

  const [result] = useState<AssessmentResultSchema | null>(resultFromNav);
  const [summary, setSummary] = useState<AssessmentSummarySchema | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!resultFromNav);

  useEffect(() => {
    // If we have the full result from navigation state, skip the API fetch
    if (resultFromNav || !id) {
      setLoading(false);
      return;
    }
    setLoading(true);
    getAssessment(id)
      .then(s => {
        setSummary(s);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-10 space-y-6 animate-pulse">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-16 bg-surface-2 rounded" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-10">
        <ErrorState title="Could not load result" message={error} />
      </div>
    );
  }

  // Direct URL visit — show the persistent summary view
  if (!result && summary) return <SummaryView summary={summary} />;

  if (!result) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-10">
        <ErrorState
          title="No result data"
          message="Navigate to this page via a completed assessment, or open it from the Assessments history."
        />
      </div>
    );
  }

  /* ── Full result view (navigation state available) ── */

  const riskAccent =
    result.overall_risk === 'critical' ? '--risk-critical' :
    result.overall_risk === 'high' ? '--risk-high' :
    result.overall_risk === 'medium' ? '--risk-medium' :
    result.overall_risk === 'low' ? '--risk-low' :
    '--risk-none';

  const confAccent =
    result.overall_confidence === 'high' ? '--conf-high' :
    result.overall_confidence === 'moderate' ? '--conf-moderate' :
    '--conf-low';

  const hasStarted = !!result.started_at;
  const hasCompleted = !!result.completed_at;

  return (
    <div className="max-w-4xl mx-auto px-6 py-10 space-y-8">
      {/* Back + actions */}
      <div className="flex items-center justify-between gap-4">
        <Link to="/assessments" className="flex items-center gap-1.5 text-xs text-3 hover:text-1 transition-colors">
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Assessments
        </Link>
        <div className="flex items-center gap-2">
          <button className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-[var(--border)]
            text-xs text-2 hover:bg-surface-2 transition-colors">
            <Download className="w-3.5 h-3.5" />
            Download Report
          </button>
          <button className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-[var(--border)]
            text-xs text-2 hover:bg-surface-2 transition-colors">
            <Share2 className="w-3.5 h-3.5" />
            Share
          </button>
        </div>
      </div>

      {/* Header */}
      <div>
        <p className="label text-accent mb-1">Assessment Results</p>
        <h1 className="text-2xl font-bold text-1">{result.title}</h1>
        <div className="mt-2 flex items-center flex-wrap gap-x-4 gap-y-1 text-xs text-3">
          <span>ID: <code className="font-mono text-2">{result.assessment_id}</code></span>
          {hasStarted && <span>Date: {formatDatetime(result.started_at!)}</span>}
          {hasStarted && hasCompleted && (
            <span>Duration: {formatDuration(result.started_at, result.completed_at)}</span>
          )}
          <StatusBadge value={result.status} variant="status" />
        </div>
      </div>

      {/* Three measurement panels */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricPanel
          label="Overall Risk"
          value={result.overall_risk.toUpperCase()}
          sub={result.risk_qualitative ?? 'No concerns detected.'}
          variant="risk"
          accent={riskAccent}
        />
        <MetricPanel
          label="Confidence"
          value={result.overall_confidence.toUpperCase()}
          sub={result.confidence_qualifier ?? 'Results based on executed analysis.'}
          variant="confidence"
          accent={confAccent}
        />
        <MetricPanel
          label="Coverage"
          value={formatPercent(result.coverage_fraction)}
          sub={`${result.detectors_executed.length} of ${result.detectors_executed.length + result.detectors_skipped.length} detectors executed`}
          variant="neutral"
          accent="--accent"
        />
      </div>

      {/* Detector results table */}
      {result.detector_runs.length > 0 && (
        <div>
          <p className="label mb-3">Detector Results</p>
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] bg-surface-2">
                  <th className="py-2 px-5 text-left label text-3 font-semibold">ID</th>
                  <th className="py-2 pr-4 text-left label text-3 font-semibold">Detector</th>
                  <th className="py-2 pr-4 text-left label text-3 font-semibold">Risk</th>
                  <th className="py-2 pr-4 text-left label text-3 font-semibold">Findings</th>
                  <th className="py-2 pr-4 text-left" />
                </tr>
              </thead>
              <tbody className="px-2">
                {result.detector_runs.map(run => (
                  <DetectorRow key={run.detector_id} run={run} assessmentId={result.assessment_id} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Skipped detectors */}
      {result.detectors_skipped.length > 0 && (
        <div className="text-xs text-3 border-t border-[var(--border)] pt-4">
          <span className="label mr-2">Skipped:</span>
          {result.detectors_skipped.map(did => (
            <code key={did} className="font-mono text-2 mr-3">{did}</code>
          ))}
          <span className="text-3">(no applicable asset provided)</span>
        </div>
      )}

      {/* Coverage gaps */}
      {result.coverage_gaps.length > 0 && (
        <div className="p-4 rounded border border-[var(--amber-border)] bg-[var(--amber-bg)]">
          <p className="label text-amber mb-2">Coverage Gaps</p>
          <ul className="space-y-1">
            {result.coverage_gaps.map((g, i) => (
              <li key={i} className="text-xs text-2">{g.reason} — {g.impact}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Navigation links */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
        {[
          { label: 'Findings', to: `/assessments/${result.assessment_id}/findings` },
          { label: 'Evidence', to: `/assessments/${result.assessment_id}/evidence` },
          { label: 'Audit Trail', to: `/assessments/${result.assessment_id}/audit` },
        ].map(link => (
          <Link
            key={link.label}
            to={link.to}
            className="flex items-center justify-between px-4 py-2.5 rounded border border-[var(--border)]
              text-sm text-2 hover:bg-surface-2 hover:text-1 transition-colors group"
          >
            {link.label}
            <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent transition-colors" />
          </Link>
        ))}
      </div>

      {/* Limitations */}
      {result.limitations && result.limitations.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer label text-3 hover:text-2 transition-colors select-none">
            Limitations ({result.limitations.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {result.limitations.map((l, i) => (
              <li key={i} className="text-xs text-3 pl-3 border-l border-[var(--border)]">{l}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
