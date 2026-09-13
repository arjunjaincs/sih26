import React, { useState, useRef, useEffect, useId } from 'react';
import { Info, AlertTriangle, ShieldAlert, CheckCircle, HelpCircle, X } from 'lucide-react';
import { cn } from '../lib/cn';

export type MetricType = 'risk' | 'confidence' | 'coverage' | 'severity';

export interface MetricSemantics {
  title: string;
  badge: string;
  badgeClass: string;
  summary: string;
  crucialRule: string;
  interpretation: string;
  pitfall: string;
}

export const METRIC_SEMANTICS: Record<MetricType, MetricSemantics> = {
  risk: {
    title: 'Overall Risk',
    badge: 'DEFECT LIKELIHOOD',
    badgeClass: 'text-[var(--risk-high)] border-[var(--risk-high)]/30 bg-[var(--risk-high-bg)]',
    summary: 'Estimated presence and severity of anomalies, corruption, or adversarial tampering given observed evidence.',
    crucialRule: 'Risk is NOT confidence. It measures what threat was found, not how thoroughly the system looked.',
    interpretation: 'Low risk + low confidence is INCONCLUSIVE — lack of detected defects reflects sparse evidence, NOT verified safety.',
    pitfall: 'Never treat low risk as proof of safety when confidence or coverage is low.',
  },
  confidence: {
    title: 'Confidence Level',
    badge: 'METHODOLOGY RIGOR (ADR-003)',
    badgeClass: 'text-[var(--conf-high)] border-[var(--conf-high)]/30 bg-[var(--conf-high-bg)]',
    summary: 'Degree of trust in the risk assessment based on evidence sufficiency, detector depth, and sample size.',
    crucialRule: 'Confidence is NOT risk. Low confidence means insufficient evidence was gathered; it NEVER indicates safety.',
    interpretation: 'High risk + low confidence means INVESTIGATION IS WARRANTED — an anomaly was signaled despite limited test probes.',
    pitfall: 'A clean result with low confidence must be re-tested with a larger sample or broader detector battery.',
  },
  coverage: {
    title: 'Coverage',
    badge: 'EXECUTION BATTERY',
    badgeClass: 'text-accent border-accent/30 bg-[var(--accent-bg)]',
    summary: 'Fraction of applicable detector battery successfully executed across inspected assets.',
    crucialRule: 'Coverage is NOT a trust score. Unrun detectors produce explicit gaps, never an implicit pass.',
    interpretation: 'Incomplete coverage (< 100%) directly reduces assurance by leaving uninspected blind spots.',
    pitfall: 'No single composite trust score exists — coverage, risk, and confidence remain orthogonal dimensions.',
  },
  severity: {
    title: 'Finding Severity',
    badge: 'DEFECT IMPACT',
    badgeClass: 'text-[var(--risk-critical)] border-[var(--risk-critical)]/30 bg-[var(--risk-critical-bg)]',
    summary: 'Potential consequence and operational impact if this specific defect is exploited or left unmitigated.',
    crucialRule: 'Severity is finding-specific and graded from Info to Critical independently of overall confidence.',
    interpretation: 'Critical or High severity findings require prompt remediation even when overall confidence is low.',
    pitfall: 'Do not downgrade finding severity merely because overall assessment coverage was incomplete.',
  },
};

interface MetricTooltipProps {
  metric: MetricType;
  children?: React.ReactNode;
  align?: 'left' | 'center' | 'right';
  className?: string;
  triggerClassName?: string;
  showIcon?: boolean;
  asSpan?: boolean;
}

export function MetricTooltip({
  metric,
  children,
  align = 'center',
  className,
  triggerClassName,
  showIcon = true,
  asSpan = true,
}: MetricTooltipProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement>(null);
  const tooltipId = useId();
  const semantics = METRIC_SEMANTICS[metric];

  // Close on outside click and escape
  useEffect(() => {
    if (!isOpen) return;

    function handlePointerDown(e: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    }

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const alignmentClass =
    align === 'left'
      ? 'left-0 sm:left-0'
      : align === 'right'
      ? 'right-0 sm:right-0'
      : 'left-1/2 -translate-x-1/2';

  const handleToggle = (e: React.SyntheticEvent) => {
    e.stopPropagation();
    setIsOpen((prev) => !prev);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleToggle(e);
    }
  };

  const commonProps = {
    ref: triggerRef as any,
    onClick: handleToggle,
    onKeyDown: handleKeyDown,
    'aria-expanded': isOpen,
    'aria-haspopup': 'dialog' as const,
    'aria-controls': tooltipId,
    'aria-label': `Semantics for ${semantics.title}: ${semantics.crucialRule}`,
    className: cn(
      'inline-flex items-center gap-1 rounded p-0.5 text-3 hover:text-1 transition-colors focus-visible:ring-1 focus-visible:ring-accent focus:outline-none cursor-pointer',
      isOpen && 'text-accent',
      triggerClassName
    ),
  };

  return (
    <div
      ref={containerRef}
      className={cn('relative inline-flex items-center', className)}
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
    >
      {asSpan ? (
        <span
          role="button"
          tabIndex={0}
          {...commonProps}
        >
          {children}
          {showIcon && (
            <Info className="w-3.5 h-3.5 opacity-70 hover:opacity-100 transition-opacity" aria-hidden="true" />
          )}
        </span>
      ) : (
        <button
          type="button"
          {...commonProps}
        >
          {children}
          {showIcon && (
            <Info className="w-3.5 h-3.5 opacity-70 hover:opacity-100 transition-opacity" aria-hidden="true" />
          )}
        </button>
      )}

      {isOpen && (
        <div
          id={tooltipId}
          role="dialog"
          aria-label={`${semantics.title} Semantics`}
          className={cn(
            'absolute top-full mt-2 z-50 w-72 sm:w-80 p-3.5 rounded-xl border border-[var(--border)] bg-surface shadow-xl text-left backdrop-blur-md animate-in fade-in zoom-in-95 duration-150 select-text',
            alignmentClass
          )}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-2 border-b border-[var(--border)] pb-2 mb-2.5">
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-bold text-1 font-mono tracking-tight">
                  {semantics.title}
                </span>
                <span
                  className={cn(
                    'font-mono text-[9px] font-bold px-1.5 py-0.2 rounded border uppercase tracking-wider',
                    semantics.badgeClass
                  )}
                >
                  {semantics.badge}
                </span>
              </div>
              <p className="text-[11px] text-2 mt-0.5 leading-snug">
                {semantics.summary}
              </p>
            </div>
            <span
              role="button"
              tabIndex={0}
              onClick={() => setIsOpen(false)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setIsOpen(false);
                }
              }}
              className="sm:hidden p-1 text-3 hover:text-1 rounded cursor-pointer inline-flex items-center justify-center focus-visible:ring-1 focus:outline-none"
              aria-label="Close tooltip"
            >
              <X className="w-3.5 h-3.5" />
            </span>
          </div>

          {/* Core ADR-003 Decoupled Semantics */}
          <div className="space-y-2 text-[11px] leading-relaxed">
            <div className="p-2 rounded bg-surface-2/60 border border-[var(--border)]">
              <span className="font-semibold text-1 block font-mono text-[10px] uppercase tracking-wider mb-0.5 text-accent">
                Core Semantics
              </span>
              <span className="text-2">{semantics.crucialRule}</span>
            </div>

            <div className="p-2 rounded bg-[var(--amber-bg)]/40 border border-[var(--amber-border)]/50">
              <span className="font-semibold text-[10px] font-mono uppercase tracking-wider mb-0.5 flex items-center gap-1 text-[var(--amber)]">
                <AlertTriangle className="w-3 h-3" />
                Interpretation Guide
              </span>
              <span className="text-2">{semantics.interpretation}</span>
            </div>

            <div className="text-[10px] text-3 pt-1 border-t border-[var(--border)]">
              <strong className="text-2 font-medium">Analyst Note: </strong>
              {semantics.pitfall}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Inline Analyst Assurance Semantics Guide Card
 * Articulates the decoupled matrix:
 * - low risk + low confidence = inconclusive
 * - high risk + low confidence = investigation warranted
 * - incomplete coverage reduces assurance
 * - no composite trust score
 */
export function AssuranceInterpretationGuide({ className }: { className?: string }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={cn(
        'rounded-xl border border-[var(--border)] bg-surface-2/30 p-3.5 text-xs space-y-2.5 transition-all',
        className
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <HelpCircle className="w-4 h-4 text-accent shrink-0" />
          <div>
            <span className="font-bold text-1 text-xs">Assurance Metric Semantics (ADR-003)</span>
            <span className="hidden sm:inline-block text-3 text-[11px] ml-2">
              Risk, Confidence, and Coverage are strictly decoupled
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="text-[11px] font-mono text-accent hover:underline font-medium shrink-0 cursor-pointer"
          aria-expanded={expanded}
        >
          {expanded ? 'Hide Matrix' : 'Explain Decoupled Matrix'}
        </button>
      </div>

      {expanded && (
        <div className="pt-2 border-t border-[var(--border)] space-y-2 animate-in fade-in duration-150">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 text-[11px]">
            {/* Rule 1 */}
            <div className="p-2.5 rounded-lg border border-[var(--border)] bg-surface">
              <div className="flex items-center gap-1.5 font-mono font-bold text-[10px] text-[var(--amber)] mb-1">
                <AlertTriangle className="w-3 h-3" />
                <span>LOW RISK + LOW CONFIDENCE</span>
              </div>
              <p className="text-2 leading-snug">
                <strong className="text-1">Inconclusive:</strong> Lack of detected defects stems from sparse evidence or limited sample size, NOT verified safety.
              </p>
            </div>

            {/* Rule 2 */}
            <div className="p-2.5 rounded-lg border border-[var(--border)] bg-surface">
              <div className="flex items-center gap-1.5 font-mono font-bold text-[10px] text-[var(--risk-high)] mb-1">
                <ShieldAlert className="w-3 h-3" />
                <span>HIGH RISK + LOW CONFIDENCE</span>
              </div>
              <p className="text-2 leading-snug">
                <strong className="text-1">Investigation Warranted:</strong> Suspicious defect detected despite shallow inspection depth. Prompt review is required.
              </p>
            </div>

            {/* Rule 3 */}
            <div className="p-2.5 rounded-lg border border-[var(--border)] bg-surface">
              <div className="flex items-center gap-1.5 font-mono font-bold text-[10px] text-accent mb-1">
                <CheckCircle className="w-3 h-3" />
                <span>INCOMPLETE COVERAGE</span>
              </div>
              <p className="text-2 leading-snug">
                <strong className="text-1">Reduces Assurance:</strong> Unrun detectors leave blind spots. PRAMAAN exposes explicit gaps and rejects composite trust scores.
              </p>
            </div>
          </div>

          <div className="text-[10px] text-3 pt-1 flex items-center justify-between">
            <span>PRAMAAN Non-Negotiable: Never collapse metrics into a single "trust score".</span>
            <span className="font-mono text-[9px] uppercase tracking-wider text-accent">AIR-GAPPED AUDIT LEDGER</span>
          </div>
        </div>
      )}
    </div>
  );
}
