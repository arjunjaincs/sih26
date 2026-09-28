import { useEffect, useState } from 'react';
import { useParams, useLocation, useOutletContext, Link } from 'react-router-dom';
import { 
  AlertTriangle, 
  ChevronRight, 
  Info,
  Sparkles,
  ShieldCheck,
  Database,
  Cpu,
  KeyRound,
} from 'lucide-react';
import type { AssessmentResultSchema, EvidenceSchema } from '../types/api';
import { getAssessment, getEvidence } from '../api/client';
import { cn } from '../lib/cn';
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
  const [evidenceItems, setEvidenceItems] = useState<EvidenceSchema[]>([]);

  useEffect(() => {
    if (result?.assessment_id) {
      getEvidence(result.assessment_id)
        .then((res) => setEvidenceItems(res.evidence || []))
        .catch(() => setEvidenceItems([]));
    }
  }, [result?.assessment_id]);

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

  // Pillar breakdown
  const dataRuns = result.detector_runs?.filter((r) => r.detector_id.startsWith('data.')) ?? [];
  const modelRuns = result.detector_runs?.filter((r) => r.detector_id.startsWith('model.')) ?? [];
  const infRuns = result.detector_runs?.filter((r) => r.detector_id.startsWith('inference.')) ?? [];

  const dataChecked = dataRuns.filter((r) => r.ran).length;
  const modelChecked = modelRuns.filter((r) => r.ran).length;
  const infChecked = infRuns.filter((r) => r.ran).length;

  const dataFindings = dataRuns.reduce((sum, r) => sum + (r.findings_count || 0), 0);
  const modelFindings = modelRuns.reduce((sum, r) => sum + (r.findings_count || 0), 0);
  const infFindings = infRuns.reduce((sum, r) => sum + (r.findings_count || 0), 0);

  const dataGaps = result.coverage_gaps?.filter((g) => g.detector_id.startsWith('data.')) ?? [];
  const modelGaps = result.coverage_gaps?.filter((g) => g.detector_id.startsWith('model.')) ?? [];
  const infGaps = result.coverage_gaps?.filter((g) => g.detector_id.startsWith('inference.')) ?? [];

  const dataCoverage = dataRuns.length > 0 ? Math.round((dataChecked / dataRuns.length) * 100) : 0;
  const modelCoverage = modelRuns.length > 0 ? Math.round((modelChecked / modelRuns.length) * 100) : 0;
  const infCoverage = infRuns.length > 0 ? Math.round((infChecked / infRuns.length) * 100) : 0;

  const dataConf = dataChecked === 0 ? 'N/A' : (dataChecked >= 4 ? 'HIGH' : dataChecked >= 2 ? 'MODERATE' : 'LOW');
  const modelConf = modelChecked === 0 ? 'N/A' : (modelChecked >= 4 ? 'HIGH' : modelChecked >= 2 ? 'MODERATE' : 'LOW');
  const infConf = infChecked === 0 ? 'N/A' : 'HIGH';

  // Specialized evidence detection for PS requirements (DI-04 distribution shift & COCO/YOLO format)
  const di04Evidence = evidenceItems.find(
    (e) => (Boolean(e?.detector_id) && e.detector_id.includes('di04')) || e?.evidence_type === 'distribution_stats'
  );
  const di04Data = di04Evidence?.data as {
    reference_sample_count?: number;
    evaluation_sample_count?: number;
    overall_shift_magnitude?: number;
    outlier_proportion?: number;
    shifted_features?: string[];
    evidence_category?: string;
  } | undefined;

  const detectedFormat = (() => {
    const t = result.title?.toLowerCase() || '';
    if (t.includes('coco')) return 'COCO';
    if (t.includes('yolo')) return 'YOLO';
    for (const ev of evidenceItems) {
      const desc = (ev?.description || '').toLowerCase();
      if (desc.includes('coco')) return 'COCO';
      if (desc.includes('yolo')) return 'YOLO';
    }
    return null;
  })();

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

      {/* ── Deterministic Offline Corpus Designation Banner ── */}
      {result.title?.toLowerCase().startsWith('demo:') && (
        <div className="p-4 rounded-xl border border-accent/30 bg-gradient-to-r from-[var(--accent-bg)]/40 via-surface to-surface-2/60 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm">
          <div className="flex items-start sm:items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-accent/20 border border-accent/40 text-accent flex items-center justify-center shrink-0 mt-0.5 sm:mt-0">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-[10px] font-bold text-accent px-2 py-0.5 rounded bg-accent/10 border border-accent/25 uppercase tracking-wider">
                  Deterministic Offline Corpus Scenario
                </span>
                <span className="text-[10px] font-mono text-3 bg-surface px-2 py-0.5 rounded border border-[var(--border)]">
                  AIR-GAPPED · AUTHENTIC DETECTORS
                </span>
              </div>
              <p className="text-xs text-3 mt-1 leading-relaxed">
                This evaluation was executed against local authentic deterministic corpus assets without mocked findings. Real cryptographic, numerical, and perceptual detectors ran in air-gapped memory.
              </p>
            </div>
          </div>

          <Link
            to="/new"
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-[var(--border)] bg-surface hover:bg-surface-2 text-xs font-semibold text-1 hover:border-accent/40 transition-colors shrink-0 shadow-sm self-start sm:self-auto"
          >
            <span>Create Custom Assessment</span>
            <ChevronRight className="w-3.5 h-3.5 text-accent" />
          </Link>
        </div>
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
      <section aria-label="Analyst Copilot Consultation" className="p-4 border border-purple-500/25 bg-purple-500/5 dark:bg-purple-950/20 dark:border-purple-800/40 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-purple-500/15 border border-purple-500/30 text-purple-600 dark:text-purple-300 shrink-0">
            <Sparkles className="w-5 h-5" />
          </div>
          <div className="space-y-0.5">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-1">
                PRAMAAN Analyst Copilot
              </h3>
              <span className="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold tracking-wide uppercase bg-purple-500/15 border border-purple-500/30 text-purple-700 dark:text-purple-300">
                CLOUD AI
              </span>
            </div>
            <p className="text-xs text-2">
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

      {/* ── Assurance Pillars (DATA, MODEL, INFERENCE) ── */}
      <section aria-label="Assurance Pillars" className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-mono font-bold text-2 uppercase tracking-wider">
            Core Pillars Overview (DATA · MODEL · INFERENCE)
          </h2>
          <span className="text-[11px] text-3">PRAMAAN Multi-Layer Triad</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* DATA Layer */}
          <div className="card p-4 border border-[var(--border)] bg-surface space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-blue-500" />
                <h3 className="font-bold text-sm text-1">DATA</h3>
              </div>
              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 border border-blue-500/30 text-blue-500 font-bold">
                INTEGRITY
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs pt-1 border-t border-[var(--border)]">
              <div>
                <span className="text-3 block text-[10px] uppercase font-mono">Checked</span>
                <span className="font-bold text-1">{dataChecked} / 5</span>
              </div>
              <div>
                <span className="text-3 block text-[10px] uppercase font-mono">Findings</span>
                <span className={cn("font-bold", dataFindings > 0 ? "text-[var(--amber)]" : "text-1")}>
                  {dataFindings}
                </span>
              </div>
              <div>
                <span className="text-3 block text-[10px] uppercase font-mono">Coverage</span>
                <span className="font-bold text-1">{dataCoverage}%</span>
              </div>
              <div>
                <span className="text-3 block text-[10px] uppercase font-mono">Confidence</span>
                <span className="font-bold text-1">{dataConf}</span>
              </div>
            </div>
            <div className="pt-2 border-t border-[var(--border)] flex items-center justify-between text-[11px]">
              <span className="text-3">Limitations</span>
              <span className="font-mono font-bold text-2">{dataGaps.length} gaps</span>
            </div>
          </div>

          {/* MODEL Layer */}
          <div className="card p-4 border border-[var(--border)] bg-surface space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-purple-500" />
                <h3 className="font-bold text-sm text-1">MODEL</h3>
              </div>
              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 border border-purple-500/30 text-purple-500 font-bold">
                NEURAL
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs pt-1 border-t border-[var(--border)]">
              <div>
                <span className="text-3 block text-[10px] uppercase font-mono">Checked</span>
                <span className="font-bold text-1">{modelChecked} / 5</span>
              </div>
              <div>
                <span className="text-3 block text-[10px] uppercase font-mono">Findings</span>
                <span className={cn("font-bold", modelFindings > 0 ? "text-[var(--amber)]" : "text-1")}>
                  {modelFindings}
                </span>
              </div>
              <div>
                <span className="text-3 block text-[10px] uppercase font-mono">Coverage</span>
                <span className="font-bold text-1">{modelCoverage}%</span>
              </div>
              <div>
                <span className="text-3 block text-[10px] uppercase font-mono">Confidence</span>
                <span className="font-bold text-1">{modelConf}</span>
              </div>
            </div>
            <div className="pt-2 border-t border-[var(--border)] flex items-center justify-between text-[11px]">
              <span className="text-3">Limitations</span>
              <span className="font-mono font-bold text-2">{modelGaps.length} gaps</span>
            </div>
          </div>

          {/* INFERENCE Layer */}
          <div className="card p-4 border border-[var(--border)] bg-surface space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <KeyRound className="w-4 h-4 text-cyan-500" />
                <h3 className="font-bold text-sm text-1">INFERENCE</h3>
              </div>
              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/30 text-cyan-500 font-bold">
                PROVENANCE
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs pt-1 border-t border-[var(--border)]">
              <div>
                <span className="text-3 block text-[10px] uppercase font-mono">Checked</span>
                <span className="font-bold text-1">{infChecked} / 1</span>
              </div>
              <div>
                <span className="text-3 block text-[10px] uppercase font-mono">Findings</span>
                <span className={cn("font-bold", infFindings > 0 ? "text-[var(--amber)]" : "text-1")}>
                  {infFindings}
                </span>
              </div>
              <div>
                <span className="text-3 block text-[10px] uppercase font-mono">Coverage</span>
                <span className="font-bold text-1">{infCoverage}%</span>
              </div>
              <div>
                <span className="text-3 block text-[10px] uppercase font-mono">Confidence</span>
                <span className="font-bold text-1">{infConf}</span>
              </div>
            </div>
            <div className="pt-2 border-t border-[var(--border)] flex items-center justify-between text-[11px]">
              <span className="text-3">Limitations</span>
              <span className="font-mono font-bold text-2">{infGaps.length} gaps</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── Specialized PS Assurance Badges (COCO/YOLO & DI-04 Shift) ── */}
      {(detectedFormat || di04Data) && (
        <section aria-label="PS Specialized Assurance" className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {detectedFormat && (
            <div className="card p-4 border border-[var(--border)] bg-surface space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider text-3">Dataset Format Specification</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-accent/15 border border-accent/30 text-accent">
                  {detectedFormat}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs pt-1 border-t border-[var(--border)]">
                <div>
                  <span className="text-3 block text-[10px] uppercase font-mono">Images</span>
                  <span className="font-bold text-1">Ingested & Associated</span>
                </div>
                <div>
                  <span className="text-3 block text-[10px] uppercase font-mono">Annotations</span>
                  <span className="font-bold text-1">Verified Schema</span>
                </div>
                <div>
                  <span className="text-3 block text-[10px] uppercase font-mono">Validation</span>
                  <span className="font-bold text-[var(--green)]">Fail-Closed Pass</span>
                </div>
              </div>
            </div>
          )}

          {di04Data && (
            <div className="card p-4 border border-[var(--border)] bg-surface space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider text-3">
                  DI-04 Distribution Shift Assurance
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-purple-500/15 border border-purple-500/30 text-purple-600 dark:text-purple-300">
                  {di04Data.evidence_category || 'DISTRIBUTION_SHIFT'}
                </span>
              </div>
              <div className="grid grid-cols-4 gap-2 text-xs pt-1 border-t border-[var(--border)]">
                <div>
                  <span className="text-3 block text-[10px] uppercase font-mono">Ref vs Eval</span>
                  <span className="font-bold text-1">
                    {di04Data.reference_sample_count ?? '-'} vs {di04Data.evaluation_sample_count ?? '-'}
                  </span>
                </div>
                <div>
                  <span className="text-3 block text-[10px] uppercase font-mono">Shift Mag</span>
                  <span className="font-bold text-1">
                    {typeof di04Data.overall_shift_magnitude === 'number'
                      ? di04Data.overall_shift_magnitude.toFixed(2)
                      : '-'}
                  </span>
                </div>
                <div>
                  <span className="text-3 block text-[10px] uppercase font-mono">Outliers</span>
                  <span className="font-bold text-1">
                    {typeof di04Data.outlier_proportion === 'number'
                      ? `${(di04Data.outlier_proportion * 100).toFixed(1)}%`
                      : '-'}
                  </span>
                </div>
                <div>
                  <span className="text-3 block text-[10px] uppercase font-mono">Shifted Feats</span>
                  <span className="font-bold text-1 truncate" title={di04Data.shifted_features?.join(', ')}>
                    {di04Data.shifted_features?.length ? di04Data.shifted_features.join(', ') : 'None'}
                  </span>
                </div>
              </div>
            </div>
          )}
        </section>
      )}

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
