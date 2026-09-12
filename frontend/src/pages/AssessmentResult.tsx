import { useEffect, useState } from 'react';
import { useParams, useLocation, useOutletContext, Link } from 'react-router-dom';
import { 
  AlertTriangle, 
  ChevronRight, 
  Info,
  Sparkles,
} from 'lucide-react';
import type { AssessmentResultSchema } from '../types/api';
import { getAssessment } from '../api/client';
import { MetricTriad } from '../components/MetricTriad';
import { DetectorMatrix } from '../components/DetectorMatrix';
import { AssessmentHeader } from '../components/AssessmentHeader';
import { AssessmentSubNav } from '../components/AssessmentSubNav';
import { ErrorState } from '../components/ErrorState';
import type { AssessmentWorkspaceContext } from '../layouts/AssessmentWorkspaceLayout';

export function AssessmentResult() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const outletCtx = useOutletContext<AssessmentWorkspaceContext | undefined>();

  const initialResult =
    outletCtx?.result ||
    (location.state as { result?: AssessmentResultSchema })?.result ||
    null;

  const [result, setResult] = useState<AssessmentResultSchema | null>(initialResult);
  const [loading, setLoading] = useState<boolean>(!initialResult);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (outletCtx?.result) {
      setResult(outletCtx.result);
      setLoading(false);
      return;
    }

    if (!result && id) {
      setLoading(true);
      getAssessment(id)
        .then((data) => {
          setResult(data);
          setError(null);
        })
        .catch((err) => {
          console.error('Failed to load assessment result:', err);
          setError(err instanceof Error ? err.message : 'Failed to load assessment result.');
        })
        .finally(() => setLoading(false));
    }
  }, [id, outletCtx?.result]);

  if (loading && !result) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="h-36 rounded-xl bg-surface-2 animate-pulse" />
          <div className="h-36 rounded-xl bg-surface-2 animate-pulse" />
          <div className="h-36 rounded-xl bg-surface-2 animate-pulse" />
        </div>
        <div className="h-64 rounded-xl bg-surface-2 animate-pulse" />
      </div>
    );
  }

  if (error && !result) {
    return (
      <ErrorState
        title="Could not load assessment"
        message={error}
        action={{ label: 'Back to Assessments', to: '/assessments' }}
      />
    );
  }

  if (!result) return null;

  const hasCoverageGaps = result.coverage_gaps && result.coverage_gaps.length > 0;
  const hasLimitations = result.limitations && result.limitations.length > 0;

  return (
    <div className={outletCtx ? "space-y-8" : "max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-6"}>
      {/* If rendered outside master AssessmentWorkspaceLayout (e.g. standalone test route), render Header & SubNav */}
      {!outletCtx && (
        <>
          <AssessmentHeader
            assessmentId={result.assessment_id}
            title={result.title}
            status={result.status}
            startedAt={result.started_at}
            completedAt={result.completed_at}
            overallRisk={result.overall_risk}
            overallConfidence={result.overall_confidence}
            coverageFraction={result.coverage_fraction}
            softwareVersion={result.software_version}
          />
          <AssessmentSubNav
            assessmentId={result.assessment_id}
            findingsCount={result.findings_count}
            evidenceCount={result.evidence_count}
            chainValid={result.audit_chain_valid}
            coverageGapsCount={result.coverage_gaps?.length ?? 0}
          />
        </>
      )}

      {/* ── Metric Triad: RISK, CONFIDENCE, COVERAGE (Decoupled & Independent) ── */}
      <section aria-label="Assurance Metrics">
        <MetricTriad
          overallRisk={result.overall_risk}
          riskQualitative={result.risk_qualitative}
          overallConfidence={result.overall_confidence}
          confidenceQualifier={result.confidence_qualifier}
          coverageFraction={result.coverage_fraction}
          detectorsExecutedCount={result.detectors_executed?.length ?? 0}
          totalDetectorsCount={(result.detectors_executed?.length ?? 0) + (result.detectors_skipped?.length ?? 0)}
        />
      </section>

      {/* ── Copilot Consultation Bar ── */}
      <section aria-label="Analyst Copilot Consultation" className="p-4 border border-purple-800/40 bg-purple-950/20 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-purple-500/15 border border-purple-500/30 text-purple-300 shrink-0">
            <Sparkles className="w-5 h-5" />
          </div>
          <div className="space-y-0.5">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-slate-200">
                PRAMAAN Analyst Copilot
              </h3>
              <span className="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold tracking-wide uppercase bg-purple-500/20 border border-purple-500/30 text-purple-300">
                CLOUD AI
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Consult Copilot to explain risk classifications, identify top investigation priorities, or evaluate coverage gaps.
            </p>
          </div>
        </div>

        <button
          onClick={() => outletCtx?.openCopilot?.('assessment')}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold text-white bg-purple-600 hover:bg-purple-500 transition-colors shrink-0 shadow-sm"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>Consult Copilot</span>
        </button>
      </section>

      {/* ── Operational Ledger & Quick Navigation ── */}
      <section aria-label="Operational Ledger" className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Link
          to={`/assessments/${result.assessment_id}/findings`}
          className="card p-4 flex items-center justify-between hover:border-accent/50 transition-all duration-150 group"
        >
          <div className="space-y-0.5">
            <p className="text-[11px] font-mono font-semibold text-3 uppercase tracking-wider">Persisted Findings</p>
            <p className="text-sm font-bold text-1 group-hover:text-accent transition-colors">
              Inspect Findings ({result.findings_count})
            </p>
          </div>
          <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
        </Link>

        <Link
          to={`/assessments/${result.assessment_id}/evidence`}
          className="card p-4 flex items-center justify-between hover:border-accent/50 transition-all duration-150 group"
        >
          <div className="space-y-0.5">
            <p className="text-[11px] font-mono font-semibold text-3 uppercase tracking-wider">Evidence Artifacts</p>
            <p className="text-sm font-bold text-1 group-hover:text-accent transition-colors">
              Inspect Evidence ({result.evidence_count})
            </p>
          </div>
          <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
        </Link>

        <Link
          to={`/assessments/${result.assessment_id}/audit`}
          className="card p-4 flex items-center justify-between hover:border-accent/50 transition-all duration-150 group"
        >
          <div className="space-y-0.5">
            <p className="text-[11px] font-mono font-semibold text-3 uppercase tracking-wider">Audit Chain (AT-01)</p>
            <p className="text-sm font-bold text-1 group-hover:text-accent transition-colors">
              {result.audit_chain_valid ? 'Chain Verified Valid' : 'Verify Append-Only Chain'}
            </p>
          </div>
          <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
        </Link>
      </section>

      {/* ── 11-Detector Assurance Battery Matrix ── */}
      <section aria-label="Detector Battery">
        <DetectorMatrix
          runs={result.detector_runs || []}
          assessmentId={result.assessment_id}
        />
      </section>

      {/* ── Coverage Gaps Section ── */}
      {hasCoverageGaps && (
        <section
          aria-label="Coverage Gaps"
          className="card p-5 border border-[var(--amber-border)] bg-[var(--amber-bg)]/20 rounded-xl space-y-4"
        >
          <div className="flex items-center gap-2 text-[var(--amber)]">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <h2 className="text-sm font-bold tracking-tight">
              Identified Coverage Gaps ({result.coverage_gaps.length})
            </h2>
          </div>
          <p className="text-xs text-2 leading-relaxed">
            Coverage gaps reflect unobserved properties or missing asset configurations. They reduce analytical confidence
            rather than flagging false defects.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
            {result.coverage_gaps.map((gap, idx) => (
              <div
                key={`${gap.detector_id}-${idx}`}
                className="p-3.5 rounded-lg border border-[var(--border)] bg-surface text-xs space-y-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono font-bold text-accent">{gap.detector_id}</span>
                  <span className="text-[11px] text-3 truncate">{gap.detector_name}</span>
                </div>
                <p className="font-semibold text-1">{gap.reason}</p>
                <div className="text-[11px] text-2 space-y-1 border-t border-[var(--border)] pt-2">
                  <div>
                    <span className="text-3 font-mono uppercase">Impact: </span>
                    <span>{gap.impact}</span>
                  </div>
                  <div>
                    <span className="text-3 font-mono uppercase">Action: </span>
                    <span className="text-accent">{gap.recommended_action}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Analytical Limitations ── */}
      {hasLimitations && (
        <section
          aria-label="Analytical Limitations"
          className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-3"
        >
          <div className="flex items-center gap-2">
            <Info className="w-4 h-4 text-3 flex-shrink-0" />
            <h2 className="text-xs font-mono font-bold text-2 uppercase tracking-wider">
              Analytical Scope & Limitations ({result.limitations.length})
            </h2>
          </div>

          <ul className="space-y-1.5 text-xs text-2 list-disc list-inside">
            {result.limitations.map((lim, idx) => (
              <li key={idx} className="leading-relaxed">
                {lim}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── Quick Jump Navigation to Inspection Workspaces ── */}
      <section aria-label="Deep-dive Navigation" className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Link
          to={`/assessments/${result.assessment_id}/findings`}
          className="card p-4 flex items-center justify-between hover:border-accent/50 transition-all duration-150 group"
        >
          <div className="space-y-0.5">
            <p className="text-[11px] font-mono font-semibold text-3 uppercase">Defect Registry</p>
            <p className="text-sm font-bold text-1 group-hover:text-accent transition-colors">
              Inspect Findings ({result.findings_count})
            </p>
          </div>
          <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
        </Link>

        <Link
          to={`/assessments/${result.assessment_id}/evidence`}
          className="card p-4 flex items-center justify-between hover:border-accent/50 transition-all duration-150 group"
        >
          <div className="space-y-0.5">
            <p className="text-[11px] font-mono font-semibold text-3 uppercase">Forensic Evidence</p>
            <p className="text-sm font-bold text-1 group-hover:text-accent transition-colors">
              Inspect Evidence ({result.evidence_count})
            </p>
          </div>
          <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
        </Link>

        <Link
          to={`/assessments/${result.assessment_id}/audit`}
          className="card p-4 flex items-center justify-between hover:border-accent/50 transition-all duration-150 group"
        >
          <div className="space-y-0.5">
            <p className="text-[11px] font-mono font-semibold text-3 uppercase">Cryptographic Chain</p>
            <p className="text-sm font-bold text-1 group-hover:text-accent transition-colors">
              Verify Audit Trail
            </p>
          </div>
          <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
        </Link>
      </section>
    </div>
  );
}
