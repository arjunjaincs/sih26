import { cn } from '../lib/cn';

type Variant = 'risk' | 'confidence' | 'severity' | 'status' | 'category' | 'neutral';

interface StatusBadgeProps {
  value: string;
  variant?: Variant;
  className?: string;
}

const RISK_CLASSES: Record<string, string> = {
  critical: 'bg-[var(--risk-critical-bg)] text-[var(--risk-critical)] border-[var(--risk-critical)]',
  high:     'bg-[var(--risk-high-bg)] text-[var(--risk-high)] border-[var(--risk-high)]',
  medium:   'bg-[var(--risk-medium-bg)] text-[var(--risk-medium)] border-[var(--risk-medium)]',
  low:      'bg-[var(--risk-low-bg)] text-[var(--risk-low)] border-[var(--risk-low)]',
  none:     'bg-[var(--risk-none-bg)] text-[var(--risk-none)] border-[var(--risk-none)]',
};

const CONFIDENCE_CLASSES: Record<string, string> = {
  high:     'bg-[var(--conf-high-bg)] text-[var(--conf-high)] border-[var(--conf-high)]',
  moderate: 'bg-[var(--conf-moderate-bg)] text-[var(--conf-moderate)] border-[var(--conf-moderate)]',
  low:      'bg-[var(--conf-low-bg)] text-[var(--conf-low)] border-[var(--conf-low)]',
};

const STATUS_CLASSES: Record<string, string> = {
  complete:  'bg-[var(--risk-none-bg)] text-[var(--status-complete)] border-[var(--status-complete)]',
  failed:    'bg-[var(--risk-critical-bg)] text-[var(--status-failed)] border-[var(--status-failed)]',
  analyzing: 'bg-[var(--accent-light)] text-[var(--accent)] border-[var(--accent)]',
  ingesting: 'bg-[var(--accent-light)] text-[var(--accent)] border-[var(--accent)]',
  created:   'bg-[var(--surface-2)] text-[var(--text-muted)] border-[var(--border)]',
};

const CATEGORY_CLASSES: Record<string, string> = {
  data_integrity:        'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800',
  model_integrity:       'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950 dark:text-purple-300 dark:border-purple-800',
  inference_provenance:  'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800',
  distribution_drift:    'bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950 dark:text-orange-300 dark:border-orange-800',
  coverage:              'bg-gray-50 text-gray-600 border-gray-200 dark:bg-gray-900 dark:text-gray-400 dark:border-gray-700',
};

const LABEL_MAP: Record<string, string> = {
  data_integrity: 'Data Integrity',
  model_integrity: 'Model Integrity',
  inference_provenance: 'Inference Provenance',
  distribution_drift: 'Distribution Drift',
  coverage: 'Coverage Gap',
  none: 'None',
  low: 'Low',
  medium: 'Medium',
  moderate: 'Moderate',
  high: 'High',
  critical: 'Critical',
  complete: 'Complete',
  failed: 'Failed',
  analyzing: 'Analyzing',
  ingesting: 'Ingesting',
  created: 'Created',
  info: 'Info',
};

export function StatusBadge({ value, variant = 'neutral', className }: StatusBadgeProps) {
  const key = value.toLowerCase();
  const label = LABEL_MAP[key] ?? value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  let classes = 'bg-[var(--surface-2)] text-[var(--text-secondary)] border-[var(--border)]';
  if (variant === 'risk' && RISK_CLASSES[key]) classes = RISK_CLASSES[key];
  else if (variant === 'confidence' && CONFIDENCE_CLASSES[key]) classes = CONFIDENCE_CLASSES[key];
  else if (variant === 'severity' && RISK_CLASSES[key]) classes = RISK_CLASSES[key];
  else if (variant === 'status' && STATUS_CLASSES[key]) classes = STATUS_CLASSES[key];
  else if (variant === 'category' && CATEGORY_CLASSES[key]) classes = CATEGORY_CLASSES[key];

  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded border text-xs font-semibold tracking-wide uppercase',
        classes,
        className,
      )}
    >
      {label}
    </span>
  );
}
