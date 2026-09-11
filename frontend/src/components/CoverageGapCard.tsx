import type { CoverageGapSchema } from '../types/api';
import { AlertCircle } from 'lucide-react';

interface CoverageGapCardProps {
  gap: CoverageGapSchema;
}

export function CoverageGapCard({ gap }: CoverageGapCardProps) {
  return (
    <div className="rounded-lg border border-[var(--amber-border)] bg-[var(--amber-light)] p-4">
      <div className="flex items-start gap-3">
        <AlertCircle className="w-4 h-4 text-[var(--amber)] flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold text-[var(--amber)] uppercase tracking-wide">
              Coverage Gap
            </span>
            <code className="text-[10px] font-mono text-[var(--text-muted)]">{gap.detector_id}</code>
          </div>
          <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">{gap.detector_name}</p>
          <dl className="mt-2 space-y-1.5 text-xs">
            <div>
              <dt className="inline text-[var(--text-muted)] font-semibold">Reason: </dt>
              <dd className="inline text-[var(--text-secondary)]">{gap.reason}</dd>
            </div>
            <div>
              <dt className="inline text-[var(--text-muted)] font-semibold">Required: </dt>
              <dd className="inline text-[var(--text-secondary)]">{gap.required_capability}</dd>
            </div>
            <div>
              <dt className="inline text-[var(--text-muted)] font-semibold">Available: </dt>
              <dd className="inline text-[var(--text-secondary)]">{gap.observed_capability}</dd>
            </div>
            <div>
              <dt className="inline text-[var(--text-muted)] font-semibold">Impact: </dt>
              <dd className="inline text-[var(--text-secondary)]">{gap.impact}</dd>
            </div>
            {gap.recommended_action && (
              <div className="pt-1 border-t border-[var(--amber-border)]">
                <dt className="text-[var(--text-muted)] font-semibold">Recommended action:</dt>
                <dd className="mt-0.5 text-[var(--text-secondary)]">{gap.recommended_action}</dd>
              </div>
            )}
          </dl>
        </div>
      </div>
    </div>
  );
}
