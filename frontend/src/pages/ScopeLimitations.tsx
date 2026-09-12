import { useEffect, useState } from 'react';
import { useParams, useOutletContext } from 'react-router-dom';
import { 
  SlidersHorizontal, 
  AlertTriangle, 
  CheckCircle2, 
  Info, 
  ShieldCheck 
} from 'lucide-react';
import type { AssessmentResultSchema } from '../types/api';
import { getAssessment } from '../api/client';
import { ErrorState } from '../components/ErrorState';
import type { AssessmentWorkspaceContext } from '../layouts/AssessmentWorkspaceLayout';

export function ScopeLimitations() {
  const { id } = useParams<{ id: string }>();
  const outletCtx = useOutletContext<AssessmentWorkspaceContext | undefined>();

  const [result, setResult] = useState<AssessmentResultSchema | null>(outletCtx?.result || null);
  const [loading, setLoading] = useState(!outletCtx?.result);
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
          console.error('Failed to load scope & limitations:', err);
          setError(err instanceof Error ? err.message : 'Failed to load data.');
        })
        .finally(() => setLoading(false));
    }
  }, [id, outletCtx?.result]);

  if (loading && !result) {
    return (
      <div className="space-y-4">
        <div className="h-32 rounded-xl bg-surface-2 animate-pulse" />
        <div className="h-48 rounded-xl bg-surface-2 animate-pulse" />
      </div>
    );
  }

  if (error || !result) {
    return (
      <ErrorState
        title="Could not load limitations"
        message={error || 'No assessment data available.'}
        action={{ label: 'Back to Overview', to: `/assessments/${id}/result` }}
      />
    );
  }

  const gaps = result.coverage_gaps || [];
  const limits = result.limitations || [];

  return (
    <div className="space-y-6">
      {/* Header card */}
      <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-1">
        <div className="flex items-center gap-2 text-accent">
          <SlidersHorizontal className="w-4 h-4" />
          <h2 className="text-sm font-bold tracking-tight text-1">
            Scope of Assurance & Operational Limitations
          </h2>
        </div>
        <p className="text-xs text-3 leading-relaxed">
          High-assurance systems require explicit, transparent boundaries. PRAMAAN makes all methodological
          assumptions, unobserved properties, and test surface coverage gaps fully auditable.
        </p>
      </div>

      {/* Coverage Gaps (if any) */}
      <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-[var(--amber)]" />
            <h3 className="text-xs font-mono font-bold text-2 uppercase tracking-wider">
              Identified Coverage Gaps ({gaps.length})
            </h3>
          </div>
          <span className="text-[11px] font-mono text-3">
            {gaps.length === 0 ? 'Full Battery Executed' : 'Confidence Reduced'}
          </span>
        </div>

        {gaps.length === 0 ? (
          <div className="p-4 rounded-lg bg-[var(--green-bg)]/20 border border-[var(--green)]/20 text-xs text-[var(--green)] flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            <span>All applicable detectors executed with complete artifact bindings. Zero coverage gaps identified.</span>
          </div>
        ) : (
          <div className="space-y-3">
            {gaps.map((gap, i) => (
              <div
                key={i}
                className="p-4 rounded-lg border border-[var(--amber-border)] bg-[var(--amber-bg)]/10 space-y-2 text-xs"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-accent">{gap.detector_id}</span>
                    <span className="font-semibold text-1">{gap.detector_name}</span>
                  </div>
                  <span className="font-mono text-[10px] text-[var(--amber)] uppercase px-2 py-0.5 rounded bg-[var(--amber-bg)] border border-[var(--amber-border)]">
                    GAP IDENTIFIED
                  </span>
                </div>

                <p className="text-2 leading-relaxed">{gap.reason}</p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 border-t border-[var(--border)] text-[11px]">
                  <div>
                    <span className="font-mono text-3 uppercase">Required Capability: </span>
                    <span className="text-2">{gap.required_capability}</span>
                  </div>
                  <div>
                    <span className="font-mono text-3 uppercase">Observed Scope: </span>
                    <span className="text-2">{gap.observed_capability}</span>
                  </div>
                  <div>
                    <span className="font-mono text-3 uppercase">Assurance Impact: </span>
                    <span className="text-2">{gap.impact}</span>
                  </div>
                  <div>
                    <span className="font-mono text-3 uppercase">Recommended Action: </span>
                    <span className="text-accent">{gap.recommended_action}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Analytical Limitations */}
      <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-3">
        <div className="flex items-center gap-2">
          <Info className="w-4 h-4 text-3" />
          <h3 className="text-xs font-mono font-bold text-2 uppercase tracking-wider">
            Methodological & Analytical Boundaries ({limits.length})
          </h3>
        </div>

        {limits.length === 0 ? (
          <p className="text-xs text-3">No specific detector limitations recorded for this run.</p>
        ) : (
          <ul className="space-y-2 text-xs text-2 list-disc list-inside">
            {limits.map((l, i) => (
              <li key={i} className="leading-relaxed">
                {l}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Invariant Guarantees */}
      <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-mono font-bold text-2 uppercase tracking-wider">
            Systemic Architectural Invariants
          </h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs text-2">
          <div className="p-3 rounded-lg bg-surface-2/40 border border-[var(--border)] space-y-1">
            <p className="font-bold text-1">Evidence Before Trust</p>
            <p className="text-3 leading-relaxed">
              PRAMAAN never creates composite trust scores or artificial confidence ratings. Every metric is backed by reproducible evidence.
            </p>
          </div>
          <div className="p-3 rounded-lg bg-surface-2/40 border border-[var(--border)] space-y-1">
            <p className="font-bold text-1">Zero Cloud Telemetry</p>
            <p className="text-3 leading-relaxed">
              Execution is 100% offline and air-gapped. No models, datasets, or metadata ever leave the local deployment environment.
            </p>
          </div>
          <div className="p-3 rounded-lg bg-surface-2/40 border border-[var(--border)] space-y-1">
            <p className="font-bold text-1">Tamper-Evident SHA-256 Ledger</p>
            <p className="text-3 leading-relaxed">
              All events are immutably cryptographically chained from genesis block to finalization. Tampering is mathematically detectable.
            </p>
          </div>
          <div className="p-3 rounded-lg bg-surface-2/40 border border-[var(--border)] space-y-1">
            <p className="font-bold text-1">Independent Triad</p>
            <p className="text-3 leading-relaxed">
              Defect Risk, Methodological Confidence, and Stack Coverage are strictly orthogonal and separately reported.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
