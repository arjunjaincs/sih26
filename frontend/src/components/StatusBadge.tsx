import { cn } from '../lib/cn';

type Variant = 'risk' | 'confidence' | 'severity' | 'status' | 'category' | 'availability' | 'neutral';

interface StatusBadgeProps {
  value: string;
  variant?: Variant;
  className?: string;
}

const RISK: Record<string, string> = {
  critical: 'bg-[var(--risk-critical-bg)] text-[var(--risk-critical)] ring-1 ring-[var(--risk-critical)]/30',
  high:     'bg-[var(--risk-high-bg)] text-[var(--risk-high)] ring-1 ring-[var(--risk-high)]/30',
  medium:   'bg-[var(--risk-medium-bg)] text-[var(--risk-medium)] ring-1 ring-[var(--risk-medium)]/30',
  low:      'bg-[var(--risk-low-bg)] text-[var(--risk-low)] ring-1 ring-[var(--risk-low)]/30',
  none:     'bg-[var(--risk-none-bg)] text-[var(--risk-none)] ring-1 ring-[var(--risk-none)]/30',
};

const CONFIDENCE: Record<string, string> = {
  high:     'bg-[var(--conf-high-bg)] text-[var(--conf-high)] ring-1 ring-[var(--conf-high)]/30',
  moderate: 'bg-[var(--conf-moderate-bg)] text-[var(--conf-moderate)] ring-1 ring-[var(--conf-moderate)]/30',
  low:      'bg-[var(--conf-low-bg)] text-[var(--conf-low)] ring-1 ring-[var(--conf-low)]/30',
};

const STATUS: Record<string, string> = {
  complete:  'bg-[var(--risk-none-bg)] text-[var(--status-complete)] ring-1 ring-[var(--status-complete)]/30',
  failed:    'bg-[var(--risk-critical-bg)] text-[var(--status-failed)] ring-1 ring-[var(--status-failed)]/30',
  analyzing: 'bg-[var(--accent-bg)] text-accent ring-1 ring-accent/30',
  ingesting: 'bg-[var(--accent-bg)] text-accent ring-1 ring-accent/30',
  created:   'bg-surface-2 text-3 ring-1 ring-[var(--border)]',
};

const AVAILABILITY: Record<string, string> = {
  implemented:    'bg-[var(--risk-none-bg)] text-[var(--risk-none)] ring-1 ring-[var(--risk-none)]/30',
  available:      'bg-[var(--risk-none-bg)] text-[var(--risk-none)] ring-1 ring-[var(--risk-none)]/30',
  limited:        'bg-[var(--risk-medium-bg)] text-[var(--risk-medium)] ring-1 ring-[var(--risk-medium)]/30',
  unavailable:    'bg-surface-2 text-3 ring-1 ring-[var(--border)]',
  not_applicable: 'bg-surface-2 text-3 ring-1 ring-[var(--border)]',
};

const CATEGORY: Record<string, string> = {
  data_integrity:       'bg-blue-500/10 text-blue-400',
  model_integrity:      'bg-purple-500/10 text-purple-400',
  inference_provenance: 'bg-amber-500/10 text-amber-400',
  distribution_drift:   'bg-orange-500/10 text-orange-400',
  coverage:             'bg-gray-500/10 text-gray-400',
};

const LABELS: Record<string, string> = {
  data_integrity: 'Data Integrity', model_integrity: 'Model Integrity',
  inference_provenance: 'Inference Provenance', distribution_drift: 'Distribution Drift',
  coverage: 'Coverage Gap', none: 'None', low: 'Low', medium: 'Medium',
  moderate: 'Moderate', high: 'High', critical: 'Critical',
  complete: 'Complete', failed: 'Failed', analyzing: 'Analyzing',
  ingesting: 'Ingesting', created: 'Created', info: 'Info',
  implemented: 'Implemented', limited: 'Limited', unavailable: 'Unavailable',
  available: 'Available', not_applicable: 'Not Applicable',
};

export function StatusBadge({ value, variant = 'neutral', className }: StatusBadgeProps) {
  const key = value.toLowerCase().replace(/ /g, '_');
  const label = LABELS[key] ?? value.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  let cls = 'bg-surface-2 text-3 ring-1 ring-[var(--border)]';

  if (variant === 'risk' && RISK[key]) cls = RISK[key];
  else if (variant === 'confidence' && CONFIDENCE[key]) cls = CONFIDENCE[key];
  else if (variant === 'severity' && RISK[key]) cls = RISK[key];
  else if (variant === 'status' && STATUS[key]) cls = STATUS[key];
  else if (variant === 'category' && CATEGORY[key]) cls = CATEGORY[key];
  else if (variant === 'availability' && AVAILABILITY[key]) cls = AVAILABILITY[key];

  return (
    <span className={cn(
      'inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold tracking-[0.06em] uppercase',
      cls, className,
    )}>
      {label}
    </span>
  );
}
