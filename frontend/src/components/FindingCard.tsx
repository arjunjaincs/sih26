import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { FindingSchema } from '../types/api';
import { StatusBadge } from './StatusBadge';
import { MetricTooltip } from './MetricTooltip';
import { cn } from '../lib/cn';
import { formatDatetime } from '../lib/format';

interface FindingCardProps {
  finding: FindingSchema;
}

export function FindingCard({ finding }: FindingCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={cn(
        'rounded-xl border bg-surface transition-all duration-150 shadow-sm',
        'border-[var(--border)]',
        expanded ? 'border-accent ring-1 ring-accent/20' : 'hover:border-[var(--border-strong,var(--border))]',
      )}
    >
      {/* Header row */}
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-start gap-3 p-4 text-left hover:bg-surface-2/60 rounded-xl transition-colors duration-150 select-none"
        aria-expanded={expanded}
      >
        <span className="mt-0.5 text-3">
          {expanded ? <ChevronDown className="w-4 h-4 text-accent" /> : <ChevronRight className="w-4 h-4" />}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <StatusBadge value={finding.category} variant="category" />
            <div className="inline-flex items-center gap-1">
              <StatusBadge value={finding.severity} variant="severity" />
              <MetricTooltip metric="severity" align="left" triggerClassName="opacity-70 hover:opacity-100" />
            </div>
          </div>
          <p className="text-sm font-bold text-1 truncate">
            {finding.title}
          </p>
          <p className="text-xs text-3 mt-0.5 line-clamp-2 leading-relaxed">
            {finding.description}
          </p>
        </div>
        <div className="text-[11px] font-mono text-3 whitespace-nowrap flex-shrink-0 pt-0.5">
          {formatDatetime(finding.created_at)}
        </div>
      </button>

      {/* Expanded details */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 pt-0 border-t border-[var(--border)] mt-0 bg-surface-2/20">
              <dl className="mt-3.5 grid grid-cols-2 gap-x-6 gap-y-3 text-xs">
                <div>
                  <dt className="text-3 font-mono font-semibold uppercase tracking-wider text-[10px]">Subcategory</dt>
                  <dd className="mt-0.5 text-1 font-medium">{finding.subcategory || '—'}</dd>
                </div>
                <div>
                  <dt className="text-3 font-mono font-semibold uppercase tracking-wider text-[10px]">Detection Method</dt>
                  <dd className="mt-0.5 text-1 font-medium">{finding.detection_method || '—'}</dd>
                </div>
                <div>
                  <dt className="text-3 font-mono font-semibold uppercase tracking-wider text-[10px]">Detector</dt>
                  <dd className="mt-0.5 font-mono text-accent font-bold">{finding.detector_id}</dd>
                </div>
                <div>
                  <dt className="text-3 font-mono font-semibold uppercase tracking-wider text-[10px]">Asset</dt>
                  <dd className="mt-0.5 text-1 font-mono text-[11px] truncate">{finding.asset_id || '—'}</dd>
                </div>
              </dl>

              {finding.limitations.length > 0 && (
                <div className="mt-3.5 pt-3 border-t border-[var(--border)]">
                  <dt className="text-3 font-mono font-semibold uppercase tracking-wider text-[10px]">Limitations & Assumptions</dt>
                  <ul className="mt-1.5 space-y-1">
                    {finding.limitations.map((l, i) => (
                      <li key={i} className="text-xs text-2 pl-3 border-l-2 border-[var(--border-strong,var(--border))] leading-relaxed">
                        {l}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {finding.recommended_disposition && (
                <div className="mt-3.5 p-3 rounded-lg bg-[var(--accent-bg)] border border-accent/20">
                  <dt className="text-accent font-mono font-semibold uppercase tracking-wider text-[10px]">Recommended Disposition</dt>
                  <dd className="mt-0.5 text-xs text-1 leading-relaxed font-medium">{finding.recommended_disposition}</dd>
                </div>
              )}

              <p className="mt-3 text-[10px] text-3 font-mono">
                Finding ID: <span className="text-1 font-bold">{finding.finding_id}</span>
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
