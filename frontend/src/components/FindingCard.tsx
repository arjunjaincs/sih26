import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { FindingSchema } from '../types/api';
import { StatusBadge } from './StatusBadge';
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
        'rounded-lg border bg-[var(--surface-1)] transition-colors duration-150',
        'border-[var(--border)]',
        expanded && 'border-[var(--accent)]',
      )}
    >
      {/* Header row */}
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-start gap-3 p-4 text-left hover:bg-[var(--surface-2)] rounded-lg transition-colors duration-150"
        aria-expanded={expanded}
      >
        <span className="mt-0.5 text-[var(--text-muted)]">
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <StatusBadge value={finding.category} variant="category" />
            <StatusBadge value={finding.severity} variant="severity" />
          </div>
          <p className="text-sm font-medium text-[var(--text-primary)] truncate">
            {finding.title}
          </p>
          <p className="text-xs text-[var(--text-muted)] mt-0.5 line-clamp-2">
            {finding.description}
          </p>
        </div>
        <div className="text-xs text-[var(--text-muted)] whitespace-nowrap flex-shrink-0">
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
            <div className="px-4 pb-4 pt-0 border-t border-[var(--border)] mt-0">
              <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 text-xs">
                <div>
                  <dt className="text-[var(--text-muted)] font-semibold uppercase tracking-wide text-[10px]">Subcategory</dt>
                  <dd className="mt-0.5 text-[var(--text-primary)]">{finding.subcategory || '—'}</dd>
                </div>
                <div>
                  <dt className="text-[var(--text-muted)] font-semibold uppercase tracking-wide text-[10px]">Detection Method</dt>
                  <dd className="mt-0.5 text-[var(--text-primary)]">{finding.detection_method || '—'}</dd>
                </div>
                <div>
                  <dt className="text-[var(--text-muted)] font-semibold uppercase tracking-wide text-[10px]">Detector</dt>
                  <dd className="mt-0.5 font-mono text-[var(--accent)]">{finding.detector_id}</dd>
                </div>
                <div>
                  <dt className="text-[var(--text-muted)] font-semibold uppercase tracking-wide text-[10px]">Asset</dt>
                  <dd className="mt-0.5 text-[var(--text-primary)] truncate">{finding.asset_id || '—'}</dd>
                </div>
              </dl>

              {finding.limitations.length > 0 && (
                <div className="mt-3">
                  <dt className="text-[var(--text-muted)] font-semibold uppercase tracking-wide text-[10px]">Limitations</dt>
                  <ul className="mt-1 space-y-0.5">
                    {finding.limitations.map((l, i) => (
                      <li key={i} className="text-xs text-[var(--text-secondary)] pl-3 border-l-2 border-[var(--border)]">
                        {l}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {finding.recommended_disposition && (
                <div className="mt-3 p-3 rounded bg-[var(--accent-light)] border border-[var(--accent-border)]">
                  <dt className="text-[var(--accent)] font-semibold uppercase tracking-wide text-[10px]">Recommended Disposition</dt>
                  <dd className="mt-0.5 text-xs text-[var(--text-primary)]">{finding.recommended_disposition}</dd>
                </div>
              )}

              <p className="mt-3 text-[10px] text-[var(--text-muted)]">
                Finding ID: <span className="font-mono">{finding.finding_id}</span>
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
