import { formatPercent } from '../lib/format';
import { cn } from '../lib/cn';
import { MetricTooltip, AssuranceInterpretationGuide } from './MetricTooltip';

interface MetricTriadProps {
  overallRisk: string;
  riskQualitative?: string | null;
  overallConfidence: string;
  confidenceQualifier?: string | null;
  coverageFraction: number;
  detectorsExecutedCount?: number;
  totalDetectorsCount?: number;
  compact?: boolean;
  showGuide?: boolean;
  className?: string;
}

export function MetricTriad({
  overallRisk,
  riskQualitative,
  overallConfidence,
  confidenceQualifier,
  coverageFraction,
  detectorsExecutedCount,
  totalDetectorsCount,
  compact = false,
  showGuide = true,
  className,
}: MetricTriadProps) {
  const normRisk = overallRisk?.toLowerCase() || 'none';
  const normConf = overallConfidence?.toLowerCase() || 'high';

  const riskAccent =
    normRisk === 'critical' ? '--risk-critical' :
    normRisk === 'high' ? '--risk-high' :
    normRisk === 'medium' ? '--risk-medium' :
    normRisk === 'low' ? '--risk-low' :
    '--risk-none';

  const confAccent =
    normConf === 'high' ? '--conf-high' :
    normConf === 'moderate' ? '--conf-moderate' :
    '--conf-low';

  if (compact) {
    return (
      <div className={cn('flex items-center flex-wrap gap-2', className)}>
        {/* Risk Badge */}
        <div
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border font-mono text-xs font-bold"
          style={{
            borderColor: `var(${riskAccent})`,
            backgroundColor: `color-mix(in srgb, var(${riskAccent}) 12%, transparent)`,
            color: `var(${riskAccent})`,
          }}
        >
          <span className="text-[10px] opacity-75 font-normal">RISK:</span>
          <span>{normRisk.toUpperCase()}</span>
          <MetricTooltip metric="risk" align="left" triggerClassName="p-0 text-inherit opacity-70 hover:opacity-100" />
        </div>

        {/* Confidence Badge */}
        <div
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border font-mono text-xs font-bold"
          style={{
            borderColor: `var(${confAccent})`,
            backgroundColor: `color-mix(in srgb, var(${confAccent}) 12%, transparent)`,
            color: `var(${confAccent})`,
          }}
        >
          <span className="text-[10px] opacity-75 font-normal">CONFIDENCE:</span>
          <span>{normConf.toUpperCase()}</span>
          <MetricTooltip metric="confidence" align="center" triggerClassName="p-0 text-inherit opacity-70 hover:opacity-100" />
        </div>

        {/* Coverage Badge */}
        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-accent/40 bg-[var(--accent-bg)] text-accent font-mono text-xs font-bold">
          <span className="text-[10px] opacity-75 font-normal">COVERAGE:</span>
          <span>{formatPercent(coverageFraction)}</span>
          <MetricTooltip metric="coverage" align="right" triggerClassName="p-0 text-inherit opacity-70 hover:opacity-100" />
        </div>
      </div>
    );
  }

  return (
    <div className={cn('space-y-4', className)}>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Risk Panel */}
        <div className="card p-5 flex flex-col justify-between gap-3 border border-[var(--border)] bg-surface relative">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <p className="label text-3 uppercase tracking-wider font-mono text-xs">Overall Risk</p>
              <MetricTooltip metric="risk" align="left" />
            </div>
            <span className="font-mono text-[10px] text-3 px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
              DEFECT SEVERITY
            </span>
          </div>
          <div>
            <span
              className="text-3xl font-extrabold leading-none tracking-tight"
              style={{ color: `var(${riskAccent})` }}
            >
              {normRisk.toUpperCase()}
            </span>
          </div>
          <p className="text-xs text-2 leading-relaxed border-t border-[var(--border)] pt-2 mt-1">
            {riskQualitative || 'No anomalous safety drift detected across inspected artifacts.'}
          </p>
        </div>

        {/* Confidence Panel */}
        <div className="card p-5 flex flex-col justify-between gap-3 border border-[var(--border)] bg-surface relative">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <p className="label text-3 uppercase tracking-wider font-mono text-xs">Confidence</p>
              <MetricTooltip metric="confidence" align="center" />
            </div>
            <span className="font-mono text-[10px] text-3 px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
              METHODOLOGY
            </span>
          </div>
          <div>
            <span
              className="text-3xl font-extrabold leading-none tracking-tight"
              style={{ color: `var(${confAccent})` }}
            >
              {normConf.toUpperCase()}
            </span>
          </div>
          <p className="text-xs text-2 leading-relaxed border-t border-[var(--border)] pt-2 mt-1">
            {confidenceQualifier || 'Evaluated through deterministic execution battery and exact byte fingerprints.'}
          </p>
        </div>

        {/* Coverage Panel */}
        <div className="card p-5 flex flex-col justify-between gap-3 border border-[var(--border)] bg-surface relative">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <p className="label text-3 uppercase tracking-wider font-mono text-xs">Coverage</p>
              <MetricTooltip metric="coverage" align="right" />
            </div>
            <span className="font-mono text-[10px] text-3 px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
              ASSURANCE STACK
            </span>
          </div>
          <div>
            <span className="text-3xl font-extrabold leading-none tracking-tight text-accent">
              {formatPercent(coverageFraction)}
            </span>
          </div>
          <p className="text-xs text-2 leading-relaxed border-t border-[var(--border)] pt-2 mt-1">
            {detectorsExecutedCount !== undefined && totalDetectorsCount !== undefined
              ? `${detectorsExecutedCount} of ${totalDetectorsCount} detector checks executed on provided assets.`
              : 'Execution coverage of applicable detector battery across inspected assets.'}
          </p>
        </div>
      </div>

      {/* Decoupled Assurance Semantics Guide */}
      {showGuide && <AssuranceInterpretationGuide />}
    </div>
  );
}
