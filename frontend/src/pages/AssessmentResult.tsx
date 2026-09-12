import { useLocation, useParams, Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { 
  Copy, 
  Check, 
  ChevronRight, 
  ShieldCheck, 
  ShieldAlert, 
  AlertTriangle, 
  FileSearch, 
  Layers,
  Database,
  Cpu,
  GitBranch,
  Clock
} from 'lucide-react';
import type { 
  AssessmentResultSchema, 
  AssessmentSummarySchema, 
  FindingSchema, 
  AuditResponse 
} from '../types/api';
import { getAssessment, getFindings, getAudit } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { ErrorState } from '../components/ErrorState';
import { AssessmentSubNav } from '../components/AssessmentSubNav';
import { formatDatetime, formatPercent, formatDuration } from '../lib/format';
import { cn } from '../lib/cn';

/* ── Copy ID Button ── */
function CopyIdButton({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(id).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        });
      }}
      className="p-1 rounded text-3 hover:text-1 hover:bg-surface-2 transition-colors focus-visible:ring-1"
      title="Copy Assessment ID"
      aria-label="Copy Assessment ID"
    >
      {copied ? <Check className="w-3 h-3 text-[var(--green)]" /> : <Copy className="w-3 h-3" />}
    </button>
  );
}

/* ── Metric panel — Risk / Confidence / Coverage ── */
function MetricPanel({
  label,
  value,
  sub,
  accent,
  badge,
}: {
  label: string;
  value: string;
  sub: string;
  accent: string;
  badge?: string;
}) {
  return (
    <div className="card p-5 flex flex-col justify-between gap-3 border border-[var(--border)]">
      <div className="flex items-center justify-between">
        <p className="label text-3 uppercase tracking-wider font-mono">{label}</p>
        {badge && (
          <span className="font-mono text-[10px] text-3 px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
            {badge}
          </span>
        )}
      </div>
      <div>
        <span
          className="text-3xl font-bold leading-none tracking-tight"
          style={{ color: `var(${accent})` }}
        >
          {value}
        </span>
      </div>
      <p className="text-xs text-2 leading-relaxed border-t border-[var(--border)] pt-2 mt-1">
        {sub}
      </p>
    </div>
  );
}

/* ── Detector result row ── */
function DetectorRow({
  run,
  assessmentId,
}: {
  run: AssessmentResultSchema['detector_runs'][number];
  assessmentId: string;
}) {
  const hasFindings = (run.findings_count ?? 0) > 0;
  
  const getIcon = (id: string) => {
    if (id.includes('DI-01')) return Database;
    if (id.includes('MI-01')) return Cpu;
    if (id.includes('PI-01')) return GitBranch;
    return Layers;
  };
  const Icon = getIcon(run.detector_id);

  return (
    <tr className="border-b border-[var(--border)] last:border-0 hover:bg-surface-2/60 transition-colors group">
      <td className="py-3 px-5">
        <div className="flex items-center gap-2">
          <Icon className="w-3.5 h-3.5 text-accent flex-shrink-0" />
          <code className="text-xs font-mono font-bold text-accent">{run.detector_id}</code>
        </div>
      </td>
      <td className="py-3 pr-4">
        <span className="text-sm font-medium text-1">{run.detector_name}</span>
      </td>
      <td className="py-3 pr-4">
        {run.ran && run.risk_level ? (
          <StatusBadge value={run.risk_level} variant="risk" />
        ) : (
          <span className="text-xs text-3 font-mono">Not applicable</span>
        )}
      </td>
      <td className="py-3 pr-4 text-xs">
        {hasFindings ? (
          <span className="inline-flex items-center gap-1 font-mono font-semibold text-[var(--amber)] bg-[var(--amber-bg)] px-2 py-0.5 rounded border border-[var(--amber-border)]">
            <AlertTriangle className="w-3 h-3" />
            {run.findings_count} finding{run.findings_count === 1 ? '' : 's'}
          </span>
        ) : !run.applicable ? (
          <span className="text-3 text-xs">Asset not provided</span>
        ) : (
          <span className="text-[var(--green)] font-mono text-xs">0 findings (clean)</span>
        )}
      </td>
      <td className="py-3 pr-5 text-right">
        {hasFindings ? (
          <Link
            to={`/assessments/${assessmentId}/findings`}
            className="inline-flex items-center gap-1 text-xs text-accent hover:underline font-medium"
          >
            Inspect <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        ) : (
          <Link
            to={`/assessments/${assessmentId}/evidence`}
            className="inline-flex items-center gap-1 text-xs text-3 hover:text-1 transition-colors"
          >
            Evidence <ChevronRight className="w-3 h-3" />
          </Link>
        )}
      </td>
    </tr>
  );
}

/* ────────────────────────────────────────────────────────────
   Summary View (Direct URL / Browser Refresh / History Click)
──────────────────────────────────────────────────────────── */
function SummaryView({ summary }: { summary: AssessmentSummarySchema }) {
  const id = summary.assessment_id;
  const [findings, setFindings] = useState<FindingSchema[]>([]);
  const [audit, setAudit] = useState<AuditResponse | null>(null);

  useEffect(() => {
    let mounted = true;
    Promise.all([
      getFindings(id).catch(() => ({ findings: [], count: 0, assessment_id: id })),
      getAudit(id).catch(() => null),
    ]).then(([findingsRes, auditRes]) => {
      if (mounted) {
        setFindings(findingsRes.findings || []);
        setAudit(auditRes);
      }
    });
    return () => { mounted = false; };
  }, [id]);

  const criticalFindings = findings.filter(f => f.severity === 'critical' || f.severity === 'high');
  const chainValid = audit?.chain_valid ?? null;

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-8">
      {/* Unified Sub-navigation */}
      <AssessmentSubNav 
        assessmentId={id} 
        findingsCount={summary.findings_count} 
        evidenceCount={summary.evidence_count} 
        chainValid={chainValid} 
      />

      {/* Header */}
      <div className="border-b border-[var(--border)] pb-6">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="font-mono text-[11px] font-bold text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
            RECORD INSPECTOR
          </span>
          <span className="text-xs text-3 font-mono">PERSISTED ASSURANCE RUN</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold text-1 tracking-tight">{summary.title}</h1>
        <div className="mt-3 flex items-center flex-wrap gap-x-5 gap-y-2 text-xs text-3">
          <div className="flex items-center gap-1.5">
            <span className="text-3">ID:</span>
            <code className="font-mono text-1">{summary.assessment_id}</code>
            <CopyIdButton id={summary.assessment_id} />
          </div>
          {summary.started_at && (
            <span>Executed: {formatDatetime(summary.started_at)}</span>
          )}
          {summary.started_at && summary.completed_at && (
            <span className="flex items-center gap-1 text-3">
              <Clock className="w-3 h-3" />
              Duration: {formatDuration(summary.started_at, summary.completed_at)}
            </span>
          )}
          <StatusBadge value={summary.status} variant="status" />
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card p-5 flex flex-col justify-between gap-3 border border-[var(--border)]">
          <div className="flex items-center justify-between">
            <p className="label text-3 uppercase tracking-wider font-mono">Persisted Findings</p>
            <span className="font-mono text-[10px] text-3 px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
              DEFECTS
            </span>
          </div>
          <div>
            <span className={cn(
              'text-3xl font-bold leading-none tracking-tight',
              summary.findings_count > 0 ? 'text-[var(--amber)]' : 'text-[var(--green)]'
            )}>
              {summary.findings_count}
            </span>
          </div>
          <p className="text-xs text-2 border-t border-[var(--border)] pt-2 mt-1">
            {criticalFindings.length > 0 
              ? `${criticalFindings.length} critical/high findings requiring review` 
              : summary.findings_count > 0 
                ? 'Informational or moderate findings recorded' 
                : 'Zero integrity anomalies or byte corruptions detected'}
          </p>
        </div>

        <div className="card p-5 flex flex-col justify-between gap-3 border border-[var(--border)]">
          <div className="flex items-center justify-between">
            <p className="label text-3 uppercase tracking-wider font-mono">Evidence Artifacts</p>
            <span className="font-mono text-[10px] text-3 px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
              PROVENANCE
            </span>
          </div>
          <div>
            <span className="text-3xl font-bold leading-none tracking-tight text-accent">
              {summary.evidence_count}
            </span>
          </div>
          <p className="text-xs text-2 border-t border-[var(--border)] pt-2 mt-1">
            Cryptographic hashes, cluster manifests, and execution telemetry
          </p>
        </div>

        <div className="card p-5 flex flex-col justify-between gap-3 border border-[var(--border)]">
          <div className="flex items-center justify-between">
            <p className="label text-3 uppercase tracking-wider font-mono">Audit Chain (AT-01)</p>
            <span className="font-mono text-[10px] text-3 px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
              SHA-256
            </span>
          </div>
          <div>
            <span className={cn(
              'text-2xl font-bold leading-none tracking-tight',
              chainValid === true ? 'text-[var(--green)]' : chainValid === false ? 'text-[var(--red)]' : 'text-3'
            )}>
              {chainValid === true ? 'CHAIN VALID' : chainValid === false ? 'INVALID LINK' : 'HASH CHAIN ACTIVE'}
            </span>
          </div>
          <p className="text-xs text-2 border-t border-[var(--border)] pt-2 mt-1">
            Sequential append-only cryptographic event linkage
          </p>
        </div>
      </div>

      {/* 4 Assurance Layers Summary */}
      <div className="card p-6 space-y-4 border border-[var(--border)]">
        <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold text-1 uppercase tracking-wider font-mono">
              Assurance Layers (DI-01 / MI-01 / PI-01 / AT-01)
            </h2>
          </div>
          <span className="text-xs text-3 font-mono">Workstation Inspection</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          {[
            {
              code: 'DI-01',
              title: 'Dataset Integrity',
              desc: 'Duplicate & corruption check',
              count: findings.filter(f => f.detector_id === 'DI-01').length,
            },
            {
              code: 'MI-01',
              title: 'Model Integrity',
              desc: 'Topology & AST fingerprinting',
              count: findings.filter(f => f.detector_id === 'MI-01').length,
            },
            {
              code: 'PI-01',
              title: 'Output Provenance',
              desc: 'Ed25519 manifest signature',
              count: findings.filter(f => f.detector_id === 'PI-01').length,
            },
            {
              code: 'AT-01',
              title: 'Audit Trail',
              desc: 'Append-only SHA-256 chain',
              status: chainValid === true ? 'VALID' : 'ACTIVE',
            },
          ].map(layer => (
            <div key={layer.code} className="p-3 rounded-lg bg-surface-2/50 border border-[var(--border)] space-y-1.5">
              <div className="flex items-center justify-between">
                <code className="text-xs font-mono font-bold text-accent">{layer.code}</code>
                {layer.status ? (
                  <span className="text-[10px] font-mono font-bold text-[var(--green)]">
                    {layer.status}
                  </span>
                ) : (
                  <span className={cn(
                    'text-[10px] font-mono font-semibold',
                    (layer.count ?? 0) > 0 ? 'text-[var(--amber)]' : 'text-3'
                  )}>
                    {layer.count ?? 0} findings
                  </span>
                )}
              </div>
              <p className="text-xs font-semibold text-1">{layer.title}</p>
              <p className="text-[11px] text-3 leading-snug">{layer.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Findings Preview (if any) */}
      {findings.length > 0 && (
        <div className="card p-6 space-y-4 border border-[var(--border)]">
          <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-[var(--amber)]" />
              <h2 className="text-sm font-bold text-1 uppercase tracking-wider font-mono">
                Key Findings Requiring Attention ({findings.length})
              </h2>
            </div>
            <Link
              to={`/assessments/${id}/findings`}
              className="text-xs font-semibold text-accent hover:underline inline-flex items-center gap-1"
            >
              Inspect all findings <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="space-y-2">
            {findings.slice(0, 3).map(f => (
              <div
                key={f.finding_id}
                className="p-3 rounded-lg border border-[var(--border)] bg-surface-2/30 flex items-start justify-between gap-4"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <StatusBadge value={f.severity} variant="severity" />
                    <code className="text-[11px] font-mono text-accent">{f.detector_id}</code>
                    <span className="text-xs font-semibold text-1">{f.title}</span>
                  </div>
                  <p className="text-xs text-2 line-clamp-1">{f.description}</p>
                </div>
                <Link
                  to={`/assessments/${id}/findings`}
                  className="text-xs text-accent hover:underline flex-shrink-0"
                >
                  Details
                </Link>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick Navigation Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Link
          to={`/assessments/${id}/findings`}
          className="card p-4 flex items-center justify-between hover:border-accent/50 transition-all duration-150 group"
        >
          <div className="space-y-0.5">
            <p className="text-xs font-mono font-semibold text-3 uppercase">Defect Registry</p>
            <p className="text-sm font-bold text-1 group-hover:text-accent transition-colors">
              Inspect Findings ({summary.findings_count})
            </p>
          </div>
          <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
        </Link>

        <Link
          to={`/assessments/${id}/evidence`}
          className="card p-4 flex items-center justify-between hover:border-accent/50 transition-all duration-150 group"
        >
          <div className="space-y-0.5">
            <p className="text-xs font-mono font-semibold text-3 uppercase">Raw & Structured</p>
            <p className="text-sm font-bold text-1 group-hover:text-accent transition-colors">
              Inspect Evidence ({summary.evidence_count})
            </p>
          </div>
          <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
        </Link>

        <Link
          to={`/assessments/${id}/audit`}
          className="card p-4 flex items-center justify-between hover:border-accent/50 transition-all duration-150 group"
        >
          <div className="space-y-0.5">
            <p className="text-xs font-mono font-semibold text-3 uppercase">Cryptographic Ledger</p>
            <p className="text-sm font-bold text-1 group-hover:text-accent transition-colors">
              Verify Audit Trail
            </p>
          </div>
          <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
        </Link>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   Main AssessmentResult Page Component
──────────────────────────────────────────────────────────── */
export function AssessmentResult() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();

  const resultFromNav: AssessmentResultSchema | null = location.state?.result ?? null;

  const [result] = useState<AssessmentResultSchema | null>(resultFromNav);
  const [summary, setSummary] = useState<AssessmentSummarySchema | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!resultFromNav);

  useEffect(() => {
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
  }, [id, resultFromNav]);

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-10 space-y-6 animate-pulse">
        <div className="h-10 bg-surface-2 rounded-lg w-1/3" />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-32 bg-surface-2 rounded-xl" />
          ))}
        </div>
        <div className="h-64 bg-surface-2 rounded-xl" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-10">
        <ErrorState title="Could not load assessment result" message={error} />
      </div>
    );
  }

  // Direct URL visit or browser refresh fallback
  if (!result && summary) return <SummaryView summary={summary} />;

  if (!result) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-10">
        <ErrorState
          title="No Assessment Data Found"
          message="Navigate to this page via a completed assessment, or select a record from the Assessment History."
        />
      </div>
    );
  }

  /* ── Full Result View (Available Immediately Post-Run) ── */

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
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-8">
      {/* Unified Sub-navigation */}
      <AssessmentSubNav 
        assessmentId={result.assessment_id} 
        findingsCount={result.findings_count} 
        evidenceCount={result.evidence_count} 
        chainValid={result.audit_chain_valid} 
      />

      {/* ── Operational Assessment Header ── */}
      <div className="border-b border-[var(--border)] pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-[11px] font-bold text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
              OPERATIONAL REPORT
            </span>
            <span className="text-xs text-3 font-mono">PRAMAAN ASSURANCE SUITE</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-1 tracking-tight">{result.title}</h1>
          <div className="mt-3 flex items-center flex-wrap gap-x-5 gap-y-2 text-xs text-3">
            <div className="flex items-center gap-1.5">
              <span className="text-3">ID:</span>
              <code className="font-mono text-1">{result.assessment_id}</code>
              <CopyIdButton id={result.assessment_id} />
            </div>
            {hasStarted && (
              <span>Executed: {formatDatetime(result.started_at)}</span>
            )}
            {hasStarted && hasCompleted && (
              <span className="flex items-center gap-1 text-3">
                <Clock className="w-3 h-3" />
                Duration: {formatDuration(result.started_at, result.completed_at)}
              </span>
            )}
            <StatusBadge value={result.status} variant="status" />
          </div>
        </div>

        {/* Action jump buttons */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <Link
            to={`/assessments/${result.assessment_id}/findings`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)] text-xs font-semibold text-2 hover:text-1 hover:bg-surface-2 transition-colors"
          >
            <AlertTriangle className="w-3.5 h-3.5 text-[var(--amber)]" />
            <span>Findings ({result.findings_count})</span>
          </Link>
          <Link
            to={`/assessments/${result.assessment_id}/evidence`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)] text-xs font-semibold text-2 hover:text-1 hover:bg-surface-2 transition-colors"
          >
            <FileSearch className="w-3.5 h-3.5 text-accent" />
            <span>Evidence ({result.evidence_count})</span>
          </Link>
        </div>
      </div>

      {/* ── Visual Prominence: RISK, CONFIDENCE, COVERAGE (Strictly Separate) ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricPanel
          label="Overall Risk"
          value={result.overall_risk.toUpperCase()}
          sub={result.risk_qualitative ?? 'No anomalous safety drift detected across inspected artifacts.'}
          accent={riskAccent}
          badge="DEFECT SEVERITY"
        />
        <MetricPanel
          label="Confidence"
          value={result.overall_confidence.toUpperCase()}
          sub={result.confidence_qualifier ?? 'Evaluated through deterministic execution battery and exact byte fingerprints.'}
          accent={confAccent}
          badge="METHODOLOGY"
        />
        <MetricPanel
          label="Coverage"
          value={formatPercent(result.coverage_fraction)}
          sub={`${result.detectors_executed.length} of ${result.detectors_executed.length + result.detectors_skipped.length} assurance layers executed on provided assets.`}
          accent="--accent"
          badge="ASSURANCE STACK"
        />
      </div>

      {/* ── Assurance Layers & Detector Results (DI-01, MI-01, PI-01, AT-01) ── */}
      <div className="card overflow-hidden border border-[var(--border)]">
        <div className="px-5 py-3.5 border-b border-[var(--border)] bg-surface-2/60 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-accent" />
            <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-1">
              Assurance Layer Execution Matrix
            </h2>
          </div>
          <span className="text-xs text-3 font-mono">
            {result.detectors_executed.length} active detector{result.detectors_executed.length === 1 ? '' : 's'}
          </span>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] bg-surface-2/30 text-[10px] font-mono uppercase font-semibold text-3">
              <th className="py-2.5 px-5 text-left">Code</th>
              <th className="py-2.5 pr-4 text-left">Assurance Layer</th>
              <th className="py-2.5 pr-4 text-left">Risk Assessment</th>
              <th className="py-2.5 pr-4 text-left">Findings Count</th>
              <th className="py-2.5 pr-5 text-right">Inspect</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border)]">
            {result.detector_runs.map(run => (
              <DetectorRow 
                key={run.detector_id} 
                run={run} 
                assessmentId={result.assessment_id} 
              />
            ))}

            {/* AT-01 Audit Layer Status Row */}
            <tr className="border-b border-[var(--border)] last:border-0 hover:bg-surface-2/60 transition-colors">
              <td className="py-3 px-5">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                  <code className="text-xs font-mono font-bold text-accent">AT-01</code>
                </div>
              </td>
              <td className="py-3 pr-4">
                <span className="text-sm font-medium text-1">Tamper-Evident Audit Trail</span>
              </td>
              <td className="py-3 pr-4">
                {result.audit_chain_valid === true ? (
                  <span className="inline-flex items-center gap-1 font-mono text-xs text-[var(--green)] bg-[var(--green-bg)] px-2 py-0.5 rounded border border-[var(--green)]/20 font-semibold">
                    <ShieldCheck className="w-3 h-3" />
                    Chain Valid
                  </span>
                ) : result.audit_chain_valid === false ? (
                  <span className="inline-flex items-center gap-1 font-mono text-xs text-[var(--red)] bg-[var(--red-bg)] px-2 py-0.5 rounded border border-[var(--red)]/20 font-semibold">
                    <ShieldAlert className="w-3 h-3" />
                    Broken Linkage
                  </span>
                ) : (
                  <span className="text-xs text-3 font-mono">Append-Only Active</span>
                )}
              </td>
              <td className="py-3 pr-4 text-xs font-mono text-2">
                SHA-256 Hash Chain
              </td>
              <td className="py-3 pr-5 text-right">
                <Link
                  to={`/assessments/${result.assessment_id}/audit`}
                  className="inline-flex items-center gap-1 text-xs text-accent hover:underline font-medium"
                >
                  Verify <ChevronRight className="w-3.5 h-3.5" />
                </Link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* ── Skipped Detectors Notice (if any) ── */}
      {result.detectors_skipped.length > 0 && (
        <div className="card p-3.5 border border-[var(--border)] bg-surface-2/40 flex items-center justify-between text-xs text-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-3 font-semibold uppercase">Skipped Layers:</span>
            {result.detectors_skipped.map(did => (
              <span key={did} className="font-mono text-2 px-1.5 py-0.5 rounded bg-surface border border-[var(--border)]">
                {did}
              </span>
            ))}
            <span>(no applicable asset provided for these detectors)</span>
          </div>
        </div>
      )}

      {/* ── Coverage Gaps ── */}
      {result.coverage_gaps.length > 0 && (
        <div className="card p-5 rounded-xl border border-[var(--amber-border)] bg-[var(--amber-bg)] space-y-2">
          <p className="label text-amber flex items-center gap-1.5 font-semibold">
            <AlertTriangle className="w-3.5 h-3.5" />
            Observed Coverage Gaps
          </p>
          <ul className="space-y-1">
            {result.coverage_gaps.map((g, i) => (
              <li key={i} className="text-xs text-2 leading-relaxed">
                <strong className="text-1">{g.detector_name}:</strong> {g.reason} — {g.impact}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Operational Linkage to Evidence and Audit ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
        <Link
          to={`/assessments/${result.assessment_id}/findings`}
          className="card p-4 flex items-center justify-between hover:border-accent/50 transition-all duration-150 group"
        >
          <div className="space-y-0.5">
            <p className="text-xs font-mono font-semibold text-3 uppercase">Defect Registry</p>
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
            <p className="text-xs font-mono font-semibold text-3 uppercase">Raw & Structured</p>
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
            <p className="text-xs font-mono font-semibold text-3 uppercase">Cryptographic Ledger</p>
            <p className="text-sm font-bold text-1 group-hover:text-accent transition-colors">
              Verify Audit Chain
            </p>
          </div>
          <ChevronRight className="w-4 h-4 text-3 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
        </Link>
      </div>

      {/* ── Limitations Notice ── */}
      {result.limitations && result.limitations.length > 0 && (
        <details className="card p-4 border border-[var(--border)] group">
          <summary className="cursor-pointer label text-3 hover:text-2 transition-colors select-none font-mono flex items-center justify-between">
            <span>Assessment Operational Limitations ({result.limitations.length})</span>
            <ChevronRight className="w-3.5 h-3.5 group-open:rotate-90 transition-transform" />
          </summary>
          <ul className="mt-3 space-y-1.5 pt-2 border-t border-[var(--border)]">
            {result.limitations.map((l, i) => (
              <li key={i} className="text-xs text-3 pl-3 border-l-2 border-[var(--border)] leading-relaxed">
                {l}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
