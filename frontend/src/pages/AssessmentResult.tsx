import { useLocation, useParams, Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { ArrowRight, Clock } from 'lucide-react';
import type { AssessmentResultSchema } from '../types/api';
import { getAssessment } from '../api/client';
import { Panel } from '../components/Panel';
import { StatusBadge } from '../components/StatusBadge';
import { MetricBlock } from '../components/MetricBlock';
import { CoverageGapCard } from '../components/CoverageGapCard';
import { ErrorState } from '../components/ErrorState';
import { formatDatetime, formatDuration, formatPercent } from '../lib/format';

export function AssessmentResult() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const resultFromNav: AssessmentResultSchema | null = location.state?.result ?? null;
  const resultState = useState<AssessmentResultSchema | null>(resultFromNav);
  const result = resultState[0];
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!resultFromNav);

  useEffect(() => {
    if (resultFromNav || !id) return;
    setLoading(true);
    // No direct GET for full result — fetch the summary then navigate user to sub-routes
    getAssessment(id)
      .then(() => setLoading(false))
      .catch((err) => { setError(err.message); setLoading(false); });
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-8">
        <div className="space-y-4 animate-pulse">
          <div className="h-10 rounded-lg bg-[var(--surface-2)] w-1/2" />
          <div className="h-28 rounded-lg bg-[var(--surface-2)]" />
          <div className="h-40 rounded-lg bg-[var(--surface-2)]" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-8">
        <Panel><ErrorState message={error} /></Panel>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-8">
        <Panel>
          <div className="py-8 text-center text-sm text-[var(--text-muted)]">
            No result data available. Please run a new assessment.
          </div>
        </Panel>
      </div>
    );
  }


  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">
            {result.title}
          </h1>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            <StatusBadge value={result.status} variant="status" />
            <span className="text-xs text-[var(--text-muted)] font-mono">{result.assessment_id}</span>
          </div>
        </div>
        <div className="text-right text-xs text-[var(--text-muted)] flex-shrink-0 space-y-0.5">
          <div className="flex items-center gap-1.5 justify-end">
            <Clock className="w-3.5 h-3.5" />
            <span>{formatDatetime(result.started_at)}</span>
          </div>
          <div>Duration: {formatDuration(result.started_at, result.completed_at)}</div>
        </div>
      </div>

      {/* Error banner */}
      {result.error && (
        <div className="rounded-lg border border-[var(--risk-critical)] bg-[var(--risk-critical-bg)] px-4 py-3">
          <p className="text-xs font-semibold text-[var(--risk-critical)] mb-0.5">Assessment Error</p>
          <p className="text-xs text-[var(--text-secondary)]">{result.error}</p>
        </div>
      )}

      {/* Risk / Confidence / Coverage — the trinity, never collapsed */}
      <Panel title="Assurance Summary">
        <div className="mb-3 text-xs text-[var(--text-muted)] bg-[var(--surface-1)] rounded p-2.5 border border-[var(--border)]">
          Risk, Confidence, and Coverage are distinct properties.
          Absence of findings with incomplete coverage does not establish safety.
        </div>
        <div className="grid grid-cols-3 gap-4">
          <MetricBlock
            label="Risk"
            value={<StatusBadge value={result.overall_risk} variant="risk" className="text-sm" />}
            description={result.risk_qualitative}
          />
          <MetricBlock
            label="Confidence"
            value={<StatusBadge value={result.overall_confidence} variant="confidence" className="text-sm" />}
            description={result.confidence_qualifier}
          />
          <MetricBlock
            label="Coverage"
            value={formatPercent(result.coverage_fraction)}
            description={`${result.detectors_executed.length} detector(s) executed`}
          />
        </div>
        {result.overall_confidence === 'low' && (
          <p className="mt-3 text-xs text-[var(--risk-medium)] font-medium">
            ⚠ Low confidence does not mean the asset is safe — it means insufficient evidence was gathered.
          </p>
        )}
      </Panel>

      {/* Navigation to sub-pages */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Findings', count: result.findings_count, to: `/assessments/${result.assessment_id}/findings` },
          { label: 'Evidence', count: result.evidence_count, to: `/assessments/${result.assessment_id}/evidence` },
          { label: 'Audit Trail', count: null, to: `/assessments/${result.assessment_id}/audit`,
            extra: result.audit_chain_valid !== null && (
              <span className={`text-[10px] font-semibold ${result.audit_chain_valid ? 'text-[var(--risk-none)]' : 'text-[var(--risk-critical)]'}`}>
                {result.audit_chain_valid ? 'CHAIN VALID' : 'CHAIN INVALID'}
              </span>
            )
          },
        ].map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className="flex flex-col gap-1 p-4 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] hover:border-[var(--accent)] hover:bg-[var(--accent-light)] transition-colors duration-150 group"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-[var(--text-secondary)] group-hover:text-[var(--accent)]">
                {item.label}
              </span>
              <ArrowRight className="w-3.5 h-3.5 text-[var(--text-muted)] group-hover:text-[var(--accent)]" />
            </div>
            {item.count !== null && (
              <span className="text-2xl font-bold text-[var(--text-primary)]">{item.count}</span>
            )}
            {item.extra}
          </Link>
        ))}
      </div>

      {/* Detector runs */}
      <Panel title="Detector Runs" description="Per-detector execution summary">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--border)]">
                {['Detector', 'Asset', 'Status', 'Risk', 'Confidence', 'Findings'].map((h) => (
                  <th key={h} className="text-left py-2 px-2 text-[var(--text-muted)] font-semibold uppercase tracking-wide text-[10px]">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.detector_runs.map((run, i) => (
                <tr key={i} className="border-b border-[var(--border-subtle)] hover:bg-[var(--surface-1)]">
                  <td className="py-2 px-2 font-mono text-[var(--accent)]">{run.detector_id}</td>
                  <td className="py-2 px-2 text-[var(--text-muted)] max-w-[120px] truncate" title={run.asset_id}>
                    {run.asset_id}
                  </td>
                  <td className="py-2 px-2"><StatusBadge value={run.status} variant="status" /></td>
                  <td className="py-2 px-2"><StatusBadge value={run.risk_level} variant="risk" /></td>
                  <td className="py-2 px-2"><StatusBadge value={run.confidence_level} variant="confidence" /></td>
                  <td className="py-2 px-2 text-[var(--text-primary)] font-semibold">{run.findings_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Coverage gaps */}
      {result.coverage_gaps.length > 0 && (
        <Panel title="Coverage Gaps" description="These properties could not be assessed with the current inputs and environment.">
          <div className="space-y-3">
            {result.coverage_gaps.map((gap) => (
              <CoverageGapCard key={gap.detector_id} gap={gap} />
            ))}
          </div>
        </Panel>
      )}

      {/* Limitations */}
      {result.limitations.length > 0 && (
        <Panel title="Known Limitations">
          <ul className="space-y-1.5">
            {result.limitations.map((l, i) => (
              <li key={i} className="text-xs text-[var(--text-secondary)] pl-3 border-l-2 border-[var(--border)]">
                {l}
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {/* Assets analyzed */}
      <Panel title="Assets Analyzed">
        <div className="flex flex-wrap gap-2">
          {result.assets_analyzed.length > 0 ? result.assets_analyzed.map((a) => (
            <code key={a} className="text-[10px] font-mono px-2 py-1 rounded bg-[var(--surface-2)] text-[var(--text-secondary)]">
              {a}
            </code>
          )) : (
            <span className="text-xs text-[var(--text-muted)]">No assets recorded.</span>
          )}
        </div>
      </Panel>
    </div>
  );
}
